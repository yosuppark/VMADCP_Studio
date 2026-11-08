"""
Reader for Nortek Signature VM (.SigVM / .AD2CP / .anpp) files.
"""
import zipfile
import struct
import math
import datetime
import os
import re
import numpy as np
from typing import Optional, Tuple, Dict, Any, List

from .data_structures import VMADCPDataset

class SigVMReader:
    """Parses Nortek .SigVM containers containing .AD2CP, .anpp, and .xml."""
    
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.ad2cp_bytes: Optional[bytes] = None
        self.anpp_bytes: Optional[bytes] = None
        self.xml_text: Optional[str] = None
        self.config: Dict[str, Any] = {
            'frequency_khz': 500.0,
            'num_beams': 4,
            'num_cells': 139,
            'cell_size_m': 0.5,
            'blanking_m': 0.5,
            'transform_matrix': np.eye(4),
            'beam_angle_deg': 25.0,
        }
        
    def load(self) -> VMADCPDataset:
        """Loads and decodes the SigVM archive into a VMADCPDataset."""
        if not os.path.exists(self.filepath):
            raise FileNotFoundError(f"File not found: {self.filepath}")
            
        ext = os.path.splitext(self.filepath)[1].lower()
        if ext == '.sigvm':
            with zipfile.ZipFile(self.filepath, 'r') as z:
                for name in z.namelist():
                    if name.lower().endswith('.ad2cp'):
                        self.ad2cp_bytes = z.read(name)
                    elif name.lower().endswith('.anpp'):
                        self.anpp_bytes = z.read(name)
                    elif name.lower().endswith('.xml'):
                        self.xml_text = z.read(name).decode('utf-8-sig', errors='ignore')
        elif ext == '.ad2cp':
            with open(self.filepath, 'rb') as f:
                self.ad2cp_bytes = f.read()
            # Try to find companion .anpp
            base = os.path.splitext(self.filepath)[0]
            anpp_path = base + '.anpp'
            if os.path.exists(anpp_path):
                with open(anpp_path, 'rb') as f:
                    self.anpp_bytes = f.read()
        else:
            raise ValueError(f"Unsupported file format: {ext}")
            
        if self.ad2cp_bytes is None:
            raise ValueError("No AD2CP data stream found in file.")
            
        # 1. Parse AD2CP config and records
        self._parse_config_strings()
        burst_data, bt_data = self._parse_ad2cp_records()
        
        # 2. Parse ANPP high-rate navigation if available
        anpp_nav = self._parse_anpp_packets() if self.anpp_bytes else None
        
        # 3. Synchronize and construct dataset
        dataset = self._assemble_dataset(burst_data, bt_data, anpp_nav)
        return dataset

    def _parse_config_strings(self):
        """Scans AD2CP for 0xA0 configuration records and updates self.config."""
        raw = self.ad2cp_bytes
        pos = 0
        while pos + 10 <= len(raw):
            if raw[pos] != 0xA5:
                idx = raw.find(b'\xa5', pos + 1)
                if idx == -1: break
                pos = idx
            hsize = raw[pos+1]
            rid = raw[pos+2]
            dsize = struct.unpack('<H', raw[pos+4:pos+6])[0]
            if rid == 0xA0: # String config
                payload = raw[pos+hsize : pos+hsize+dsize]
                text = payload.decode('latin1', errors='ignore')
                self._extract_config_from_text(text)
                break
            pos += hsize + dsize

    def _extract_config_from_text(self, text: str):
        """Extracts parameters from GETBURST, GETXFBURST, BEAMCFGLIST, etc."""
        # Frequency
        m_freq = re.search(r'FREQ=(\d+)', text)
        if m_freq:
            self.config['frequency_khz'] = float(m_freq.group(1))
            
        # Burst config: NC, NB, CS, BD
        m_burst = re.search(r'GETBURST,NC=(\d+),NB=(\d+),CS=([\d\.]+),BD=([\d\.]+)', text)
        if m_burst:
            self.config['num_cells'] = int(m_burst.group(1))
            self.config['num_beams'] = int(m_burst.group(2))
            self.config['cell_size_m'] = float(m_burst.group(3))
            self.config['blanking_m'] = float(m_burst.group(4))
            
        # Beam angle
        m_beam = re.search(r'BEAMCFGLIST,BEAM=1,THETA=([\d\.]+)', text)
        if m_beam:
            self.config['beam_angle_deg'] = float(m_beam.group(1))
            
        # Transform matrix (Beam to Instrument/XYZ)
        m_xf = re.search(
            r'GETXFBURST,ROWS=4,COLS=4,M11=([-\d\.]+),M12=([-\d\.]+),M13=([-\d\.]+),M14=([-\d\.]+),'
            r'M21=([-\d\.]+),M22=([-\d\.]+),M23=([-\d\.]+),M24=([-\d\.]+),'
            r'M31=([-\d\.]+),M32=([-\d\.]+),M33=([-\d\.]+),M34=([-\d\.]+),'
            r'M41=([-\d\.]+),M42=([-\d\.]+),M43=([-\d\.]+),M44=([-\d\.]+)',
            text
        )
        if m_xf:
            vals = [float(m_xf.group(i)) for i in range(1, 17)]
            self.config['transform_matrix'] = np.array(vals).reshape((4, 4))
        else:
            # Default standard convex 4-beam matrix for 25 deg
            th = math.radians(self.config['beam_angle_deg'])
            c = 1.0 / (2.0 * math.sin(th))
            d = 1.0 / (4.0 * math.cos(th))
            self.config['transform_matrix'] = np.array([
                [ c,  0, -c,  0],
                [ 0, -c,  0,  c],
                [ d,  d,  d,  d],
                [ d, -d,  d, -d]
            ])

    def _parse_ad2cp_records(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Parses Burst (0x15) and Bottom Track (0x17) records."""
        raw = self.ad2cp_bytes
        pos = 0
        bursts = []
        bt_records = []
        nc = self.config['num_cells']
        nb = self.config['num_beams']
        
        vel_bytes = nc * nb * 2
        amp_bytes = nc * nb * 1
        cor_bytes = nc * nb * 1
        
        while pos + 10 <= len(raw):
            if raw[pos] != 0xA5:
                idx = raw.find(b'\xa5', pos + 1)
                if idx == -1: break
                pos = idx
            hsize = raw[pos+1]
            rid = raw[pos+2]
            dsize = struct.unpack('<H', raw[pos+4:pos+6])[0]
            rec_end = pos + hsize + dsize
            if rec_end > len(raw):
                break
                
            payload = raw[pos+hsize : rec_end]
            pos = rec_end
            
            if rid == 0x15: # Burst Profiling
                try:
                    offset = payload[1]
                    yr = payload[8] + 1900
                    mo = payload[9] + 1
                    da = payload[10]
                    hr = payload[11]
                    mi = payload[12]
                    sc = payload[13]
                    us = struct.unpack('<H', payload[14:16])[0]
                    dt = datetime.datetime(yr, mo, da, hr, mi, sc, us*100, tzinfo=datetime.timezone.utc)
                    
                    sos = struct.unpack('<H', payload[16:18])[0] * 0.1
                    temp = struct.unpack('<h', payload[18:20])[0] * 0.01
                    press = struct.unpack('<I', payload[20:24])[0] * 0.001
                    heading = struct.unpack('<H', payload[24:26])[0] * 0.01
                    pitch = struct.unpack('<h', payload[26:28])[0] * 0.01
                    roll = struct.unpack('<h', payload[28:30])[0] * 0.01
                    
                    pdata = payload[offset:]
                    if len(pdata) >= vel_bytes + amp_bytes + cor_bytes:
                        vel_raw = np.frombuffer(pdata[:vel_bytes], dtype=np.int16).reshape((nc, nb)).astype(float) * 0.001 # m/s
                        # Filter invalid vel (-32768)
                        vel_raw[vel_raw <= -32.0] = np.nan
                        
                        amp_raw = np.frombuffer(pdata[vel_bytes:vel_bytes+amp_bytes], dtype=np.uint8).reshape((nc, nb)).astype(float)
                        cor_raw = np.frombuffer(pdata[vel_bytes+amp_bytes:vel_bytes+amp_bytes+cor_bytes], dtype=np.uint8).reshape((nc, nb)).astype(float)
                        
                        bursts.append({
                            'time': dt,
                            'epoch': dt.timestamp(),
                            'sound_speed': sos,
                            'temperature': temp,
                            'pressure': press,
                            'heading': heading,
                            'pitch': pitch,
                            'roll': roll,
                            'velocity': vel_raw,
                            'amplitude': amp_raw,
                            'correlation': cor_raw
                        })
                except Exception:
                    pass
                    
            elif rid == 0x17: # Bottom Track
                try:
                    offset = payload[1]
                    yr = payload[8] + 1900
                    mo = payload[9] + 1
                    da = payload[10]
                    hr = payload[11]
                    mi = payload[12]
                    sc = payload[13]
                    us = struct.unpack('<H', payload[14:16])[0]
                    dt = datetime.datetime(yr, mo, da, hr, mi, sc, us*100, tzinfo=datetime.timezone.utc)
                    
                    pl = payload[offset:]
                    if len(pl) >= 40:
                        fom = struct.unpack('<HHHH', pl[0:8])
                        vel = struct.unpack('<iiii', pl[8:24])
                        rng = struct.unpack('<iiii', pl[24:40])
                        
                        # Validate ranges and vel
                        ranges_m = np.array([r * 0.001 if r > 0 and r < 500000 else np.nan for r in rng])
                        vels_m_s = np.array([v * 0.001 if abs(v) < 30000 else np.nan for v in vel])
                        
                        bt_records.append({
                            'time': dt,
                            'epoch': dt.timestamp(),
                            'ranges': ranges_m,
                            'vels': vels_m_s,
                            'fom': fom
                        })
                except Exception:
                    pass
                    
        return bursts, bt_records

    def _parse_anpp_packets(self) -> Dict[str, np.ndarray]:
        """Parses Advanced Navigation Packet 20 (System State)."""
        raw = self.anpp_bytes
        pos = 0
        epochs, lats, lons, vns, ves, rolls, pitchs, hdgs, heaves = [], [], [], [], [], [], [], [], []
        
        while pos + 5 <= len(raw):
            pid = raw[pos+1]
            plen = raw[pos+2]
            if pid == 20 and plen == 100:
                pld = raw[pos+5 : pos+5+100]
                sec, usec = struct.unpack('<II', pld[4:12])
                lat_rad, lon_rad, height = struct.unpack('<ddd', pld[12:36])
                vn, ve, vd = struct.unpack('<fff', pld[36:48])
                roll_rad, pitch_rad, hdg_rad = struct.unpack('<fff', pld[64:76])
                
                # Check valid coordinates
                if abs(lat_rad) <= math.pi/2 and abs(lon_rad) <= math.pi and sec > 1000000000:
                    t_epoch = sec + usec * 1e-6
                    epochs.append(t_epoch)
                    lats.append(math.degrees(lat_rad))
                    lons.append(math.degrees(lon_rad))
                    vns.append(vn)
                    ves.append(ve)
                    rolls.append(math.degrees(roll_rad))
                    pitchs.append(math.degrees(pitch_rad))
                    hdgs.append(math.degrees(hdg_rad) % 360.0)
                    heaves.append(-vd) # vertical heave approx
                pos += 5 + plen
            else:
                pos += 1
                
        if not epochs:
            return None
            
        sort_idx = np.argsort(epochs)
        return {
            'epoch': np.array(epochs)[sort_idx],
            'lat': np.array(lats)[sort_idx],
            'lon': np.array(lons)[sort_idx],
            'vn': np.array(vns)[sort_idx],
            've': np.array(ves)[sort_idx],
            'roll': np.array(rolls)[sort_idx],
            'pitch': np.array(pitchs)[sort_idx],
            'heading': np.array(hdgs)[sort_idx],
            'heave': np.array(heaves)[sort_idx],
        }

    def _assemble_dataset(self, bursts: List[Dict], bt_records: List[Dict], anpp_nav: Optional[Dict]) -> VMADCPDataset:
        """Assembles and time-synchronizes the dataset."""
        N = len(bursts)
        nc = self.config['num_cells']
        nb = self.config['num_beams']
        cs = self.config['cell_size_m']
        bd = self.config['blanking_m']
        
        # Depth cell center distances along vertical (m)
        # Cell 0 center is bd + cs/2, or bd + cs
        depth_bins = bd + np.arange(nc) * cs + (cs * 0.5)
        
        times = np.array([b['epoch'] for b in bursts])
        sound_speed = np.array([b['sound_speed'] for b in bursts])
        temperature = np.array([b['temperature'] for b in bursts])
        pressure = np.array([b['pressure'] for b in bursts])
        inst_heading = np.array([b['heading'] for b in bursts])
        inst_pitch = np.array([b['pitch'] for b in bursts])
        inst_roll = np.array([b['roll'] for b in bursts])
        
        raw_beam_vel = np.array([b['velocity'] for b in bursts]) # (N, nc, nb)
        raw_amp = np.array([b['amplitude'] for b in bursts])      # (N, nc, nb)
        raw_cor = np.array([b['correlation'] for b in bursts])    # (N, nc, nb)
        
        # Navigation interpolation
        if anpp_nav is not None and len(anpp_nav['epoch']) > 1:
            nav_t = anpp_nav['epoch']
            lat = np.interp(times, nav_t, anpp_nav['lat'])
            lon = np.interp(times, nav_t, anpp_nav['lon'])
            ship_ve = np.interp(times, nav_t, anpp_nav['ve'])
            ship_vn = np.interp(times, nav_t, anpp_nav['vn'])
            ship_pitch = np.interp(times, nav_t, anpp_nav['pitch'])
            ship_roll = np.interp(times, nav_t, anpp_nav['roll'])
            ship_heave = np.interp(times, nav_t, anpp_nav['heave'])
            
            # Heading unwrap for interpolation
            hdg_rad = np.unwrap(np.radians(anpp_nav['heading']))
            ship_hdg = np.degrees(np.interp(times, nav_t, hdg_rad)) % 360.0
        else:
            # Fallback to internal sensors or zero
            lat = np.zeros(N)
            lon = np.zeros(N)
            ship_ve = np.zeros(N)
            ship_vn = np.zeros(N)
            ship_hdg = inst_heading
            ship_pitch = inst_pitch
            ship_roll = inst_roll
            ship_heave = np.zeros(N)
            
        # Bottom Track matching
        bt_range_beam = np.full((N, nb), np.nan)
        bt_depth = np.full(N, np.nan)
        bt_ve = np.full(N, np.nan)
        bt_vn = np.full(N, np.nan)
        bt_valid = np.zeros(N, dtype=bool)
        
        if bt_records:
            bt_t = np.array([r['epoch'] for r in bt_records])
            # For each burst find nearest BT within 2.0s
            for i, t in enumerate(times):
                dt_arr = np.abs(bt_t - t)
                nearest_idx = np.argmin(dt_arr)
                if dt_arr[nearest_idx] < 2.0:
                    rec = bt_records[nearest_idx]
                    rngs = rec['ranges']
                    bt_range_beam[i] = rngs
                    valid_rngs = rngs[~np.isnan(rngs)]
                    if len(valid_rngs) >= 2:
                        # Mean vertical depth: slant_range * cos(theta)
                        th = math.radians(self.config['beam_angle_deg'])
                        bt_depth[i] = np.mean(valid_rngs) * math.cos(th)
                        bt_valid[i] = True
                        
                    # BT velocities
                    b_vel = rec['vels']
                    if len(b_vel) >= 2 and not np.all(np.isnan(b_vel)):
                        # In AD2CP, BT vel can be beam or instrument XYZ
                        # Convert beam to instrument via transform matrix
                        if not np.any(np.isnan(b_vel)):
                            inst_bt = np.dot(self.config['transform_matrix'], b_vel)
                            # Rotate by ship heading to ENU
                            psi = math.radians(ship_hdg[i])
                            # East / North
                            bt_ve[i] = -(inst_bt[0] * math.cos(psi) + inst_bt[1] * math.sin(psi))
                            bt_vn[i] = -(-inst_bt[0] * math.sin(psi) + inst_bt[1] * math.cos(psi))
                            
        # Initialize Dataset
        ds = VMADCPDataset(
            instrument_name="Nortek Signature500",
            frequency_khz=self.config['frequency_khz'],
            beam_angle_deg=self.config['beam_angle_deg'],
            num_beams=nb,
            num_cells=nc,
            cell_size_m=cs,
            blanking_distance_m=bd,
            depth_bins=depth_bins,
            times=times,
            raw_lat=lat.copy(),
            raw_lon=lon.copy(),
            raw_ship_ve=ship_ve.copy(),
            raw_ship_vn=ship_vn.copy(),
            raw_heading=ship_hdg.copy(),
            raw_pitch=ship_pitch.copy(),
            raw_roll=ship_roll.copy(),
            lat=lat,
            lon=lon,
            ship_vel_east=ship_ve,
            ship_vel_north=ship_vn,
            ship_heading=ship_hdg,
            ship_pitch=ship_pitch,
            ship_roll=ship_roll,
            ship_heave=ship_heave,
            sound_speed=sound_speed,
            temperature=temperature,
            pressure=pressure,
            raw_beam_vel=raw_beam_vel,
            raw_amplitude=raw_amp,
            raw_correlation=raw_cor,
            transform_matrix=self.config['transform_matrix'],
            bt_range_beam=bt_range_beam,
            bt_depth=bt_depth,
            bt_vel_east=bt_ve,
            bt_vel_north=bt_vn,
            bt_valid=bt_valid,
        )
        return ds
