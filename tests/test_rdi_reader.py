"""
Comprehensive unit & integration test for Teledyne RDI PD0 reader and processing.
Generates a compliant TRDI PD0 binary file with Fixed/Variable Leader, Velocity,
Correlation, Echo Intensity, Bottom Track, and VMDAS Navigation blocks.
"""
import os
import sys
import struct
import math
import datetime
import numpy as np

sys.path.insert(0, os.path.abspath("."))
from vmadcp.io.rdi_reader import RDIReader
from vmadcp.io import load_adcp_dataset
from vmadcp.processing.pipeline import ProcessingPipeline
from vmadcp.export.gmt_exporter import GMTExporter
from vmadcp.gui.app import VMADCPApplication

def create_synthetic_rdi_pd0(filepath: str, num_ensembles: int = 40, num_cells: int = 25):
    """Creates a binary TRDI PD0 file following standard Teledyne RDI specifications."""
    num_beams = 4
    cell_size_cm = 100 # 1.0m
    blank_cm = 150     # 1.5m
    bin1_cm = 250      # 2.5m
    
    with open(filepath, 'wb') as f:
        base_time = datetime.datetime(2026, 4, 15, 8, 30, 0, tzinfo=datetime.timezone.utc)
        
        for ens_idx in range(num_ensembles):
            ens_time = base_time + datetime.timedelta(seconds=ens_idx * 2)
            
            num_data_types = 8
            header_len = 6 + num_data_types * 2
            
            # --- Fixed Leader (0x0000) - 59 bytes ---
            # System config: 300kHz (freq=2), 20 deg (beam_angle=0)
            sys_cfg = 2 | (0 << 4)
            fl_bytes = bytearray(59)
            struct.pack_into('<H', fl_bytes, 0, 0x0000) # ID
            fl_bytes[2] = 16 # CPU ver
            fl_bytes[3] = 20 # CPU rev
            fl_bytes[4] = sys_cfg # System Config LSB
            fl_bytes[5] = 0       # System Config MSB
            fl_bytes[8] = num_beams
            fl_bytes[9] = num_cells
            struct.pack_into('<H', fl_bytes, 12, cell_size_cm)
            struct.pack_into('<H', fl_bytes, 14, blank_cm)
            fl_bytes[25] = 0 # Beam coordinates
            struct.pack_into('<H', fl_bytes, 32, bin1_cm)
            fixed_leader = bytes(fl_bytes)
            
            # --- Variable Leader (0x0080) - 65 bytes ---
            vl_bytes = bytearray(65)
            struct.pack_into('<H', vl_bytes, 0, 0x0080) # ID
            struct.pack_into('<H', vl_bytes, 2, ens_idx + 1) # Ensemble number
            yr_2digit = ens_time.year % 100
            vl_bytes[4] = yr_2digit
            vl_bytes[5] = ens_time.month
            vl_bytes[6] = ens_time.day
            vl_bytes[7] = ens_time.hour
            vl_bytes[8] = ens_time.minute
            vl_bytes[9] = ens_time.second
            vl_bytes[10] = int(ens_time.microsecond / 10000)
            struct.pack_into('<H', vl_bytes, 14, 1500) # Sound speed
            struct.pack_into('<H', vl_bytes, 16, 45)   # Depth 4.5m (45 dm)
            struct.pack_into('<H', vl_bytes, 18, int((45.0 + ens_idx * 0.5) * 100)) # Heading
            struct.pack_into('<h', vl_bytes, 20, int(1.2 * 100))  # Pitch
            struct.pack_into('<h', vl_bytes, 22, int(-0.8 * 100)) # Roll
            struct.pack_into('<H', vl_bytes, 24, 35)              # Salinity ppt
            struct.pack_into('<h', vl_bytes, 26, int(16.5 * 100)) # Temperature
            var_leader = bytes(vl_bytes)
            
            # --- Velocity (0x0100) ---
            vel_bytes = bytearray(struct.pack('<H', 0x0100))
            for c in range(num_cells):
                # Synthetic current: ~0.35 m/s (350 mm/s)
                v1 = int(250 + math.sin(c*0.2) * 50)
                v2 = int(-180 + math.cos(c*0.2) * 40)
                v3 = int(10)
                v4 = int(5)
                vel_bytes.extend(struct.pack('<hhhh', v1, v2, v3, v4))
                
            # --- Correlation (0x0200) ---
            cor_bytes = bytearray(struct.pack('<H', 0x0200))
            for c in range(num_cells):
                cor_bytes.extend(bytes([180, 175, 185, 178]))
                
            # --- Echo Intensity (0x0300) ---
            echo_bytes = bytearray(struct.pack('<H', 0x0300))
            for c in range(num_cells):
                val = max(180 - c * 4, 40)
                echo_bytes.extend(bytes([val, val, val, val]))
                
            # --- Percent Good (0x0400) ---
            pg_bytes = bytearray(struct.pack('<H', 0x0400))
            for c in range(num_cells):
                pg_bytes.extend(bytes([98, 99, 97, 100]))
                
            # --- Bottom Track (0x0600) ---
            bt_bytes = bytearray(struct.pack('<H', 0x0600))
            bt_bytes.extend(b'\x00' * 14) # padding to byte 16
            # Range: 25.0 meters (2500 cm)
            bt_bytes.extend(struct.pack('<HHHH', 2500, 2520, 2490, 2510))
            # Velocity: ship speed ~ 2.0 m/s (2000 mm/s)
            bt_bytes.extend(struct.pack('<hhhh', -1400, 1200, 20, 10))
            bt_bytes.extend(bytes([200, 200, 200, 200])) # corr
            bt_bytes.extend(bytes([150, 150, 150, 150])) # eval amp
            bt_bytes.extend(bytes([100, 100, 100, 100])) # pct good
            
            # --- VMDAS Navigation (0x2000) ---
            nav_bytes = bytearray(struct.pack('<H', 0x2000))
            nav_bytes.extend(b'\x00' * 12)
            # Simulated GPS Lat/Lon (East Sea, Korea)
            lat_f = 36.250 + ens_idx * 0.0001
            lon_f = 129.440 + ens_idx * 0.0001
            sog_f = 2.1 # m/s
            cog_f = 45.0 # deg
            nav_bytes.extend(struct.pack('<ffff', lat_f, lon_f, sog_f, cog_f))
            nav_bytes.extend(b'\x00' * 20)
            
            # Assemble ensemble
            data_blocks = [
                fixed_leader,
                var_leader,
                vel_bytes,
                cor_bytes,
                echo_bytes,
                pg_bytes,
                bt_bytes,
                nav_bytes
            ]
            
            offsets = []
            curr_off = header_len
            for blk in data_blocks:
                offsets.append(curr_off)
                curr_off += len(blk)
                
            total_ens_len = curr_off + 2 # +2 for checksum
            
            header = bytearray()
            header.extend(b'\x7f\x7f')
            header.extend(struct.pack('<H', total_ens_len))
            header.append(0) # spare
            header.append(num_data_types)
            for off in offsets:
                header.extend(struct.pack('<H', off))
                
            f.write(header)
            for blk in data_blocks:
                f.write(blk)
            f.write(b'\x12\x34') # Checksum

def test_rdi_loading_and_processing():
    test_pd0 = r"tests\sample_synthetic.pd0"
    print("1. Creating compliant synthetic Teledyne RDI PD0 file:", test_pd0)
    create_synthetic_rdi_pd0(test_pd0, num_ensembles=40, num_cells=25)
    assert os.path.exists(test_pd0)
    
    print("2. Testing RDIReader & auto-detection load_adcp_dataset()...")
    ds = load_adcp_dataset(test_pd0)
    
    print(f"   Loaded: {ds.instrument_name}")
    print(f"   Ensembles: {ds.num_ensembles}, Cells: {ds.num_cells}, Beams: {ds.num_beams}")
    print(f"   Frequency: {ds.frequency_khz:.1f} kHz, Cell Size: {ds.cell_size_m:.2f} m")
    print(f"   Ship speed mean: {np.nanmean(np.sqrt(ds.ship_vel_east**2 + ds.ship_vel_north**2)):.2f} m/s")
    print(f"   BT Depth mean: {np.nanmean(ds.bt_depth):.2f} m")
    
    assert ds.num_ensembles == 40
    assert ds.num_cells == 25
    assert ds.frequency_khz == 300.0
    assert ds.cell_size_m == 1.0
    assert ds.bt_valid.sum() == 40
    assert not np.isnan(ds.lat[0])
    assert ds.percent_good.shape == (40, 25)
    assert np.nanmean(ds.percent_good) > 90.0
    
    print("2.1 Testing iter_ensembles generator stream (adcpreader pipeline style)...")
    ens_count = 0
    for ens in RDIReader.iter_ensembles(test_pd0):
        ens_count += 1
        assert 'velocity' in ens
        assert 'time' in ens
    assert ens_count == 40
    print(f"   Streamed {ens_count} ensembles successfully!")
    
    print("2.2 Testing 3-beam solution recovery in beam_to_instrument...")
    from vmadcp.processing.motion import beam_to_instrument
    test_beams = np.array([0.5, -0.4, 0.2, 0.1])
    res_4b = beam_to_instrument(test_beams, ds.transform_matrix, allow_3beam=True)
    assert not np.isnan(res_4b[:3]).any()
    # Now simulate beam 1 NaN:
    test_beams_3b = np.array([np.nan, -0.4, 0.2, 0.1])
    res_3b = beam_to_instrument(test_beams_3b, ds.transform_matrix, allow_3beam=True)
    assert not np.isnan(res_3b[:3]).any(), "3-beam solution should successfully recover u, v, w!"
    assert np.isnan(res_3b[3]), "Error velocity must be NaN for 3-beam solution!"
    print("   3-beam solution successfully recovered instrument velocities!")
    
    print("3. Testing ProcessingPipeline with RDI dataset...")
    pipeline = ProcessingPipeline(
        misalignment_deg=0.5,
        amplitude_scale=1.01,
        velocity_reference="GNSS",
        enable_sidelobe_mask=True,
        min_correlation_pct=50.0
    )
    ds_proc = pipeline.process(ds)
    
    assert ds_proc.u_abs.shape == (40, 25)
    assert ds_proc.current_speed.shape == (40, 25)
    assert ds_proc.volume_backscatter_sv.shape == (40, 25)
    print("   Post-processing pipeline succeeded on RDI data!")
    print(f"   Mean ocean current speed: {np.nanmean(ds_proc.current_speed):.3f} m/s")
    
    print("4. Testing GMT Exporter with RDI dataset...")
    gmt_exp = GMTExporter(ds_proc)
    out_dir = r"tests\output_rdi_gmt"
    files = gmt_exp.export(out_dir, depth_layer_min_m=2.0, depth_layer_max_m=15.0)
    assert os.path.exists(files["bat_script"])
    assert os.path.exists(files["vectors"])
    print("   GMT export succeeded!")
    
    print("5. Testing GUI application with RDI dataset...")
    app = VMADCPApplication()
    app.dataset = ds_proc
    app._update_all_views()
    app._generate_qc_report()
    app.update_idletasks()
    app.update()
    app.destroy()
    print("   GUI rendered RDI profiles and track map smoothly!")
    
    print("\nALL TELEDYNE RDI PD0 TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_rdi_loading_and_processing()
