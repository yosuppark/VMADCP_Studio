"""
Teledyne RDI (TRDI) VM-ADCP PD0 binary reader.
Supports Workhorse, Ocean Surveyor, Sentinel, and VMDAS files (.pd0, .enr, .sta, .lta).
Decodes Fixed Leader, Variable Leader, Velocity, Correlation, Echo Intensity,
Bottom Track, and VMDAS Navigation / NMEA data blocks.
"""
import os
import struct
import math
import datetime
import numpy as np
from typing import Dict, Any, List, Optional, Tuple

from .data_structures import VMADCPDataset, SensorOffsets

def verify_pd0_checksum(data: bytes) -> bool:
    """Verifies standard RDI PD0 16-bit modulo checksum (pyadps standard)."""
    if len(data) < 4:
        return False
    chk = struct.unpack('<H', data[-2:])[0]
    calc_chk = sum(data[:-2]) & 0xFFFF
    return chk == calc_chk

def concatenate_pd0_files(file_list: List[str], output_path: str) -> int:
    """
    Concatenates multiple sequential PD0 deployment files into a single unified file.
    Equivalent to pyadps-cat utility.
    Returns total number of ensembles concatenated.
    """
    total_ensembles = 0
    with open(output_path, 'wb') as fout:
        for fpath in file_list:
            if not os.path.exists(fpath):
                continue
            with open(fpath, 'rb') as fin:
                data = fin.read()
                fout.write(data)
                # Count 0x7F 0x7F sync headers
                pos = 0
                while pos + 4 < len(data):
                    idx = data.find(b'\x7f\x7f', pos)
                    if idx == -1:
                        break
                    total_ensembles += 1
                    pos = idx + 2
    return total_ensembles
RDI_FREQUENCIES = {
    0: 75.0,
    1: 150.0,
    2: 300.0,
    3: 600.0,
    4: 1200.0,
    5: 2400.0,
}

class RDIReader:
    """Parses Teledyne RDI PD0 binary files into VMADCPDataset."""
    
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.raw_bytes: bytes = b""
        self.config: Dict[str, Any] = {
            'frequency_khz': 300.0,
            'beam_angle_deg': 20.0,
            'num_beams': 4,
            'num_cells': 30,
            'cell_size_m': 1.0,
            'blanking_m': 1.0,
            'bin1_dist_m': 2.0,
            'is_convex': True,
            'is_upward': False,
            'coord_sys': 'BEAM', # BEAM, INST, or EARTH
        }
        
    def load(self) -> VMADCPDataset:
        """Reads and parses the PD0 file."""
        if not os.path.exists(self.filepath):
            raise FileNotFoundError(f"File not found: {self.filepath}")
            
        with open(self.filepath, 'rb') as f:
            self.raw_bytes = f.read()
            
        if len(self.raw_bytes) < 32:
            raise ValueError("File is too small to be a valid RDI PD0 file.")
            
        # Parse ensembles
        ensembles = self._parse_ensembles()
        if not ensembles:
            raise ValueError("No valid PD0 ensembles found in file.")
            
        # Also check for companion VMDAS NMEA navigation files (.N1R, .N2R, .nav)
        nav_data = self._try_load_companion_navigation()
        
        return self._assemble_dataset(ensembles, nav_data)

    def _parse_ensembles(self) -> List[Dict[str, Any]]:
        raw = self.raw_bytes
        pos = 0
        total_len = len(raw)
        ensembles = []
        
        while pos + 4 < total_len:
            # Search for sync bytes 0x7F 0x7F
            if raw[pos] != 0x7F or raw[pos+1] != 0x7F:
                idx = raw.find(b'\x7f\x7f', pos + 1)
                if idx == -1:
                    break
                pos = idx
                
            ens_bytes = struct.unpack('<H', raw[pos+2:pos+4])[0]
            if ens_bytes < 10 or pos + ens_bytes > total_len:
                pos += 2
                continue
                
            ens_data = raw[pos : pos + ens_bytes]
            parsed = self._decode_single_ensemble(ens_data)
            if parsed is not None:
                ensembles.append(parsed)
                pos += ens_bytes
            else:
                pos += 2
                
        return ensembles

    def _decode_single_ensemble(self, data: bytes) -> Optional[Dict[str, Any]]:
        try:
            num_data_types = data[5]
            offsets = []
            for i in range(num_data_types):
                off = struct.unpack('<H', data[6 + i*2 : 8 + i*2])[0]
                offsets.append(off)
                
            record = {}
            for off in offsets:
                if off + 2 > len(data):
                    continue
                header_id = struct.unpack('<H', data[off:off+2])[0]
                
                # 1. Fixed Leader (0x0000)
                if header_id == 0x0000 and off + 59 <= len(data):
                    self._decode_fixed_leader(data[off:], record)
                    
                # 2. Variable Leader (0x0080)
                elif header_id == 0x0080 and off + 65 <= len(data):
                    self._decode_variable_leader(data[off:], record)
                    
                # 3. Velocity (0x0100)
                elif header_id == 0x0100:
                    self._decode_velocity(data[off:], record)
                    
                # 4. Correlation Magnitude (0x0200)
                elif header_id == 0x0200:
                    self._decode_correlation(data[off:], record)
                    
                # 5. Echo Intensity (0x0300)
                elif header_id == 0x0300:
                    self._decode_echo_intensity(data[off:], record)
                    
                # 5.1 Percent Good (0x0400)
                elif header_id == 0x0400:
                    self._decode_percent_good(data[off:], record)
                    
                # 6. Bottom Track (0x0600)
                elif header_id == 0x0600:
                    self._decode_bottom_track(data[off:], record)
                    
                # 7. VMDAS Navigation (0x2000 / 0x2001)
                elif header_id in (0x2000, 0x2001):
                    self._decode_vmdas_navigation(data[off:], record)
                    
            if 'time' in record and 'velocity' in record:
                return record
            return None
        except Exception:
            return None

    def _decode_fixed_leader(self, data: bytes, record: Dict[str, Any]):
        num_beams = data[8]
        num_cells = data[9]
        cell_size_cm = struct.unpack('<H', data[12:14])[0]
        blank_cm = struct.unpack('<H', data[14:16])[0]
        bin1_cm = struct.unpack('<H', data[32:34])[0]
        
        sys_cfg_lsb = data[4]
        sys_cfg_msb = data[5]
        freq_idx = sys_cfg_lsb & 0x07
        freq_khz = RDI_FREQUENCIES.get(freq_idx, 300.0)
        
        # smerckel/adcpreader convention:
        # Bit 7: 0 = Downward-facing (vessel), 1 = Upward-facing
        is_upward = bool((sys_cfg_msb >> 7) & 0x01)
        # Bit 6: 0 = Concave, 1 = Convex (or standard RDI convex bit 6)
        is_convex = bool((sys_cfg_msb & 0x40) == 0)
        beam_angle_code = (sys_cfg_msb >> 4) & 0x03
        beam_angle = 30.0 if beam_angle_code == 1 else (15.0 if beam_angle_code == 2 else 20.0)
        
        # Coordinate transform code (byte 25)
        # bits 4-3: 0=BEAM, 1=INST, 2=SHIP, 3=EARTH
        coord_code = (data[25] >> 3) & 0x03
        coord_map = {0: 'BEAM', 1: 'INST', 2: 'SHIP', 3: 'EARTH'}
        coord_sys = coord_map.get(coord_code, 'BEAM')
        use_tilts = bool((data[25] >> 2) & 0x01)
        use_3beam = bool((data[25] >> 1) & 0x01)
        bin_mapping = bool(data[25] & 0x01)
        
        self.config['num_beams'] = num_beams
        self.config['num_cells'] = num_cells
        self.config['cell_size_m'] = cell_size_cm * 0.01
        self.config['blanking_m'] = blank_cm * 0.01
        self.config['bin1_dist_m'] = bin1_cm * 0.01
        self.config['frequency_khz'] = freq_khz
        self.config['beam_angle_deg'] = beam_angle
        self.config['coord_sys'] = coord_sys
        self.config['is_upward'] = is_upward
        self.config['is_convex'] = is_convex
        self.config['use_tilts'] = use_tilts
        self.config['use_3beam'] = use_3beam

    def _decode_variable_leader(self, data: bytes, record: Dict[str, Any]):
        ens_num = struct.unpack('<H', data[2:4])[0]
        # Real-time clock: YY MM DD HH MM SS hundredths
        # Year: century offset + year (e.g. 25 -> 2025)
        yr = data[4]
        yr = 2000 + yr if yr < 90 else 1900 + yr
        mo = data[5]
        da = data[6]
        hr = data[7]
        mi = data[8]
        sc = data[9]
        hun = data[10]
        dt = datetime.datetime(yr, mo, da, hr, mi, sc, hun * 10000, tzinfo=datetime.timezone.utc)
        
        sos = struct.unpack('<H', data[14:16])[0] # sound speed m/s
        depth_dm = struct.unpack('<H', data[16:18])[0] # dm
        hdg = struct.unpack('<H', data[18:20])[0] * 0.01 # deg
        pitch = struct.unpack('<h', data[20:22])[0] * 0.01 # deg
        roll = struct.unpack('<h', data[22:24])[0] * 0.01 # deg
        salinity = struct.unpack('<H', data[24:26])[0] # ppt
        temp = struct.unpack('<h', data[26:28])[0] * 0.01 # deg C
        pressure = struct.unpack('<I', data[48:52])[0] * 0.001 if len(data) >= 52 else 0.0 # dbar
        
        record['time'] = dt
        record['epoch'] = dt.timestamp()
        record['sound_speed'] = sos
        record['transducer_depth'] = depth_dm * 0.1
        record['heading'] = hdg
        record['pitch'] = pitch
        record['roll'] = roll
        record['temperature'] = temp
        record['salinity'] = salinity
        record['pressure'] = pressure

    def _decode_velocity(self, data: bytes, record: Dict[str, Any]):
        nc = self.config['num_cells']
        nb = self.config['num_beams']
        expected_bytes = 2 + nc * nb * 2
        if len(data) >= expected_bytes:
            flat = np.frombuffer(data[2:2 + nc * nb * 2], dtype=np.int16).reshape((nc, nb)).astype(float)
            # RDI bad velocity value is -32768
            flat[flat <= -32000] = np.nan
            record['velocity'] = flat * 0.001 # mm/s -> m/s

    def _decode_correlation(self, data: bytes, record: Dict[str, Any]):
        nc = self.config['num_cells']
        nb = self.config['num_beams']
        expected_bytes = 2 + nc * nb
        if len(data) >= expected_bytes:
            raw_cor = np.frombuffer(data[2:2 + nc * nb], dtype=np.uint8).reshape((nc, nb)).astype(float)
            # RDI correlation is 0..255, convert to percentage (0..100%)
            record['correlation'] = (raw_cor / 255.0) * 100.0

    def _decode_echo_intensity(self, data: bytes, record: Dict[str, Any]):
        nc = self.config['num_cells']
        nb = self.config['num_beams']
        expected_bytes = 2 + nc * nb
        if len(data) >= expected_bytes:
            raw_echo = np.frombuffer(data[2:2 + nc * nb], dtype=np.uint8).reshape((nc, nb)).astype(float)
            record['amplitude'] = raw_echo # counts

    def _decode_percent_good(self, data: bytes, record: Dict[str, Any]):
        nc = self.config['num_cells']
        nb = self.config['num_beams']
        expected_bytes = 2 + nc * nb
        if len(data) >= expected_bytes:
            raw_pg = np.frombuffer(data[2:2 + nc * nb], dtype=np.uint8).reshape((nc, nb)).astype(float)
            record['percent_good'] = raw_pg # percentage 0..100%

    def _decode_bottom_track(self, data: bytes, record: Dict[str, Any]):
        # Header size 2, range starts at byte 16
        if len(data) >= 32:
            # 4 beams range in cm
            r_cm = struct.unpack('<HHHH', data[16:24])
            # 4 beams velocity in mm/s
            v_mm = struct.unpack('<hhhh', data[24:32])
            
            ranges_m = np.array([r * 0.01 if 0 < r < 60000 else np.nan for r in r_cm])
            vels_m = np.array([v * 0.001 if abs(v) < 30000 else np.nan for v in v_mm])
            
            record['bt_ranges'] = ranges_m
            record['bt_vels'] = vels_m

    def _decode_vmdas_navigation(self, data: bytes, record: Dict[str, Any]):
        # VMDAS NMEA Navigation block format
        if len(data) >= 46:
            # UTC time (hour, min, sec, day, month, year)
            # Latitude, Longitude as 32-bit floats or 64-bit doubles
            lat = struct.unpack('<f', data[14:18])[0] if len(data) >= 18 else np.nan
            lon = struct.unpack('<f', data[18:22])[0] if len(data) >= 22 else np.nan
            sog = struct.unpack('<f', data[22:26])[0] if len(data) >= 26 else np.nan # Speed over ground m/s
            cog = struct.unpack('<f', data[26:30])[0] if len(data) >= 30 else np.nan # Course deg
            
            if not (math.isnan(lat) or math.isnan(lon) or abs(lat) > 90.0 or abs(lon) > 180.0):
                record['lat'] = float(lat)
                record['lon'] = float(lon)
                if not math.isnan(sog) and not math.isnan(cog):
                    cog_rad = math.radians(cog)
                    record['ship_ve'] = float(sog * math.sin(cog_rad))
                    record['ship_vn'] = float(sog * math.cos(cog_rad))

    def _try_load_companion_navigation(self) -> Optional[Dict[str, np.ndarray]]:
        """Searches for companion VMDAS N1R/N2R/NAV text files for GPS positions."""
        base, _ = os.path.splitext(self.filepath)
        for cand in [base + '.N1R', base + '.N2R', base + '.nav', base + '.csv']:
            if os.path.exists(cand):
                try:
                    return self._parse_nmea_text_file(cand)
                except Exception:
                    pass
        return None

    def _parse_nmea_text_file(self, path: str) -> Dict[str, np.ndarray]:
        times, lats, lons, sog_arr, cog_arr = [], [], [], [], []
        with open(path, 'r', encoding='latin1', errors='ignore') as f:
            for line in f:
                parts = line.strip().split(',')
                # Check for standard $GPGGA or $GPRMC
                if len(parts) > 6 and ('GGA' in parts[0] or 'RMC' in parts[0]):
                    try:
                        # Extract lat/lon
                        lat_raw = float(parts[2]) if 'GGA' in parts[0] else float(parts[3])
                        lat_deg = int(lat_raw / 100) + (lat_raw % 100) / 60.0
                        lon_raw = float(parts[4]) if 'GGA' in parts[0] else float(parts[5])
                        lon_deg = int(lon_raw / 100) + (lon_raw % 100) / 60.0
                        lats.append(lat_deg)
                        lons.append(lon_deg)
                    except Exception:
                        pass
        return {'lat': np.array(lats), 'lon': np.array(lons)} if lats else None

    def _assemble_dataset(self, ensembles: List[Dict[str, Any]], nav_data: Optional[Dict]) -> VMADCPDataset:
        N = len(ensembles)
        nc = self.config['num_cells']
        nb = self.config['num_beams']
        cs = self.config['cell_size_m']
        bin1 = self.config['bin1_dist_m']
        
        # Depth cell centers: bin1 + i * cs
        depth_bins = bin1 + np.arange(nc) * cs
        
        times = np.array([e['epoch'] for e in ensembles])
        sound_speed = np.array([e.get('sound_speed', 1500.0) for e in ensembles])
        temperature = np.array([e.get('temperature', 15.0) for e in ensembles])
        pressure = np.array([e.get('pressure', 0.0) for e in ensembles])
        
        heading = np.array([e.get('heading', 0.0) for e in ensembles])
        pitch = np.array([e.get('pitch', 0.0) for e in ensembles])
        roll = np.array([e.get('roll', 0.0) for e in ensembles])
        
        # 3D arrays: (N, nc, nb)
        raw_vel = np.array([e['velocity'] for e in ensembles])
        raw_amp = np.array([e.get('amplitude', np.zeros((nc, nb))) for e in ensembles])
        raw_cor = np.array([e.get('correlation', np.full((nc, nb), 100.0)) for e in ensembles])
        raw_pg = np.array([e.get('percent_good', np.full((nc, nb), 100.0)) for e in ensembles])
        
        # Summary 2D percent good:
        # If EARTH coordinates: field 0 is 3-beam good, field 3 is 4-beam good
        if self.config.get('coord_sys') == 'EARTH':
            pg_summary = np.clip(raw_pg[:, :, 0] + raw_pg[:, :, 3], 0.0, 100.0)
        else:
            pg_summary = np.nanmean(raw_pg, axis=2)
        
        # Navigation
        lat = np.array([e.get('lat', np.nan) for e in ensembles])
        lon = np.array([e.get('lon', np.nan) for e in ensembles])
        ship_ve = np.array([e.get('ship_ve', np.nan) for e in ensembles])
        ship_vn = np.array([e.get('ship_vn', np.nan) for e in ensembles])
        
        # Bottom Track
        bt_range_beam = np.full((N, nb), np.nan)
        bt_depth = np.full(N, np.nan)
        bt_ve = np.full(N, np.nan)
        bt_vn = np.full(N, np.nan)
        bt_valid = np.zeros(N, dtype=bool)
        
        cos_th = math.cos(math.radians(self.config['beam_angle_deg']))
        for i, e in enumerate(ensembles):
            if 'bt_ranges' in e:
                rng = e['bt_ranges']
                bt_range_beam[i] = rng
                val_r = rng[~np.isnan(rng)]
                if len(val_r) >= 2:
                    bt_depth[i] = np.mean(val_r) * cos_th
                    bt_valid[i] = True
            if 'bt_vels' in e:
                b_vel = e['bt_vels']
                if not np.all(np.isnan(b_vel)):
                    # If BT vel is in instrument coordinates, rotate to ENU
                    psi = math.radians(heading[i])
                    # Beam/Inst to ENU
                    vx = b_vel[0] if len(b_vel) > 0 else 0.0
                    vy = b_vel[1] if len(b_vel) > 1 else 0.0
                    bt_ve[i] = -(vx * math.cos(psi) + vy * math.sin(psi))
                    bt_vn[i] = -(-vx * math.sin(psi) + vy * math.cos(psi))
                    
        # If GNSS is missing but BT is valid, SOG can fallback to BT
        if np.all(np.isnan(ship_ve)) and np.any(bt_valid):
            ship_ve = np.where(bt_valid, -bt_ve, 0.0)
            ship_vn = np.where(bt_valid, -bt_vn, 0.0)
            
        # RDI Transform Matrix (Convex 20/30 deg standard Janus array)
        th = math.radians(self.config['beam_angle_deg'])
        c = 1.0 / (2.0 * math.sin(th))
        d = 1.0 / (4.0 * math.cos(th))
        if not self.config.get('is_convex', True):
            c = -c
            
        # [u, v, w, err]
        transform_matrix = np.array([
            [ c, -c,  0,  0],
            [ 0,  0, -c,  c],
            [ d,  d,  d,  d],
            [ d,  d, -d, -d]
        ])
        
        # Transducer draft
        draft = np.nanmean([e.get('transducer_depth', 0.0) for e in ensembles])
        offsets = SensorOffsets(transducer_draft_m=float(draft) if not np.isnan(draft) else 0.0)
        
        inst_name = f"Teledyne RDI Workhorse/OceanSurveyor {int(self.config['frequency_khz'])}kHz"
        orientation = "up" if self.config.get('is_upward', False) else "down"
        
        return VMADCPDataset(
            instrument_name=inst_name,
            frequency_khz=self.config['frequency_khz'],
            beam_angle_deg=self.config['beam_angle_deg'],
            num_beams=nb,
            num_cells=nc,
            cell_size_m=cs,
            blanking_distance_m=self.config['blanking_m'],
            coord_sys=self.config.get('coord_sys', 'BEAM'),
            orientation=orientation,
            is_convex=self.config.get('is_convex', True),
            offsets=offsets,
            depth_bins=depth_bins,
            times=times,
            raw_lat=lat.copy(),
            raw_lon=lon.copy(),
            raw_ship_ve=ship_ve.copy(),
            raw_ship_vn=ship_vn.copy(),
            raw_heading=heading.copy(),
            raw_pitch=pitch.copy(),
            raw_roll=roll.copy(),
            lat=lat,
            lon=lon,
            ship_vel_east=ship_ve,
            ship_vel_north=ship_vn,
            ship_heading=heading,
            ship_pitch=pitch,
            ship_roll=roll,
            ship_heave=np.zeros(N),
            sound_speed=sound_speed,
            temperature=temperature,
            pressure=pressure,
            raw_beam_vel=raw_vel,
            raw_amplitude=raw_amp,
            raw_correlation=raw_cor,
            raw_percent_good=raw_pg,
            percent_good=pg_summary,
            transform_matrix=transform_matrix,
            bt_range_beam=bt_range_beam,
            bt_depth=bt_depth,
            bt_vel_east=bt_ve,
            bt_vel_north=bt_vn,
            bt_valid=bt_valid,
        )

    @classmethod
    def iter_ensembles(cls, filepath: str):
        """
        Generator yielding decoded ensembles one by one from PD0 stream.
        Memory-efficient pipeline processing matching smerckel/adcpreader design.
        """
        reader = cls(filepath)
        with open(filepath, 'rb') as f:
            buf = bytearray()
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                buf.extend(chunk)
                while len(buf) >= 4:
                    pos = buf.find(b'\x7f\x7f')
                    if pos == -1:
                        del buf[:-1]
                        break
                    if pos + 4 > len(buf):
                        del buf[:pos]
                        break
                    ens_bytes = struct.unpack('<H', buf[pos+2:pos+4])[0]
                    if ens_bytes < 10 or ens_bytes > 65535:
                        del buf[:pos+2]
                        continue
                    if pos + ens_bytes > len(buf):
                        del buf[:pos]
                        break
                    ens_data = bytes(buf[pos : pos + ens_bytes])
                    del buf[:pos + ens_bytes]
                    parsed = reader._decode_single_ensemble(ens_data)
                    if parsed is not None:
                        yield parsed
