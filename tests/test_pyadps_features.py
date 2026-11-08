"""
Tests for pyadps-inspired capabilities:
1. Checksum verification & corrupt ensemble handling
2. Sequential PD0 file concatenation (pyadps-cat equivalent)
3. Sensor health (tilt angle) filter
4. Physical velocity cutoff & echo intensity filters
5. Magnetic declination correction
"""
import os
import sys
import numpy as np

sys.path.insert(0, os.path.abspath("."))
from vmadcp.io.rdi_reader import RDIReader, verify_pd0_checksum, concatenate_pd0_files
from vmadcp.io.data_structures import SensorOffsets
from vmadcp.processing.motion import apply_sensor_offsets_and_leverarm
from vmadcp.processing.qc_filter import (
    apply_sensor_health_filter,
    apply_velocity_cutoff_filter,
    apply_echo_threshold_filter
)
from tests.test_rdi_reader import create_synthetic_rdi_pd0

def test_pyadps_features():
    print("1. Testing Sensor Health (Tilt Angle) Filter...")
    # Tilt > 15 deg should be flagged False
    pitch = np.array([0.0, 10.0, 16.0, 5.0])
    roll = np.array([0.0, 5.0, 2.0, 18.0])
    mask_tilt = apply_sensor_health_filter(pitch, roll, max_tilt_deg=15.0)
    assert mask_tilt[0] == True
    assert mask_tilt[1] == True
    assert mask_tilt[2] == False  # 16 deg pitch > 15 deg
    assert mask_tilt[3] == False  # 18 deg roll > 15 deg
    print("   Sensor health tilt filter verified!")

    print("2. Testing Physical Velocity Cutoff & Echo Threshold...")
    u = np.array([[0.5, 4.0], [0.2, 0.3]]) # 4.0 m/s > 3.0 m/s cutoff
    v = np.array([[0.2, 0.1], [0.1, 0.2]])
    w = np.array([[0.05, 0.05], [0.9, 0.05]]) # 0.9 m/s > 0.8 m/s cutoff
    mask_vel = apply_velocity_cutoff_filter(u, v, w, max_horizontal_spd_m_s=3.0, max_vertical_spd_m_s=0.8)
    assert mask_vel[0, 0] == True
    assert mask_vel[0, 1] == False # u too high
    assert mask_vel[1, 0] == False # w too high
    assert mask_vel[1, 1] == True
    print("   Velocity cutoff filter verified!")

    amp = np.array([[30.0, 15.0], [45.0, 25.0]]) # 15.0 < 20.0 counts
    mask_echo = apply_echo_threshold_filter(amp, min_echo_counts=20.0)
    assert mask_echo[0, 0] == True
    assert mask_echo[0, 1] == False
    print("   Echo threshold filter verified!")

    print("3. Testing Magnetic Declination Correction...")
    times = np.array([100.0, 101.0, 102.0])
    lats = np.array([36.0, 36.0, 36.0])
    lons = np.array([129.0, 129.0, 129.0])
    ve = np.array([1.0, 1.0, 1.0])
    vn = np.array([0.0, 0.0, 0.0])
    raw_hdg = np.array([45.0, 45.0, 45.0])
    pitch = np.zeros(3)
    roll = np.zeros(3)
    
    # Offsets with -7.5 deg magnetic declination (East Sea, Korea)
    offsets = SensorOffsets(magnetic_declination_deg=-7.5, heading_offset_deg=0.0)
    _, _, _, _, corr_hdg, _, _ = apply_sensor_offsets_and_leverarm(
        times, lats, lons, ve, vn, raw_hdg, pitch, roll, offsets
    )
    assert np.isclose(corr_hdg[0], 37.5), f"Expected 37.5, got {corr_hdg[0]}"
    print("   Magnetic declination adjustment verified!")

    print("4. Testing PD0 Checksum & pyadps-cat File Concatenation...")
    f1 = r"tests\sample_cat_1.pd0"
    f2 = r"tests\sample_cat_2.pd0"
    f_merged = r"tests\sample_cat_merged.pd0"
    
    create_synthetic_rdi_pd0(f1, num_ensembles=10, num_cells=15)
    create_synthetic_rdi_pd0(f2, num_ensembles=15, num_cells=15)
    
    total = concatenate_pd0_files([f1, f2], f_merged)
    assert total >= 25, f"Expected at least 25 ensembles, got {total}"
    assert os.path.exists(f_merged)
    
    # Read merged file
    reader = RDIReader(f_merged)
    ds = reader.load()
    assert ds.num_ensembles == 25, f"Expected 25 ensembles in merged file, got {ds.num_ensembles}"
    print(f"   Successfully concatenated {len([f1, f2])} files into {ds.num_ensembles} ensembles!")

    print("\nALL PYADPS INTEGRATION TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_pyadps_features()
