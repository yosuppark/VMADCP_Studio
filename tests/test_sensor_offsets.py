import os
import sys
import numpy as np

sys.path.insert(0, os.path.abspath("."))
from vmadcp.io.data_structures import SensorOffsets
from vmadcp.io.sigvm_reader import SigVMReader
from vmadcp.processing.motion import apply_sensor_offsets_and_leverarm
from vmadcp.processing.pipeline import ProcessingPipeline
from vmadcp.gui.app import VMADCPApplication
from vmadcp.gui.widgets.offset_dialog import SensorOffsetDialog

def test_leverarm_and_offsets():
    print("1. Testing Lever-Arm and Attitude Offset mathematical functions...")
    times = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    raw_lat = np.array([36.0, 36.0, 36.0, 36.0, 36.0])
    raw_lon = np.array([129.0, 129.0, 129.0, 129.0, 129.0])
    raw_ve = np.array([2.0, 2.0, 2.0, 2.0, 2.0])
    raw_vn = np.array([0.0, 0.0, 0.0, 0.0, 0.0])
    raw_heading = np.array([90.0, 95.0, 100.0, 105.0, 110.0]) # turning ship
    raw_pitch = np.zeros(5)
    raw_roll = np.zeros(5)
    
    offsets = SensorOffsets(
        lever_arm_x_m=10.0, # ADCP is 10m forward of GNSS
        lever_arm_y_m=2.0,  # ADCP is 2m starboard of GNSS
        lever_arm_z_m=3.0,  # ADCP is 3m below GNSS
        transducer_draft_m=4.5,
        heading_offset_deg=2.5, # Heading bias
        pitch_offset_deg=-0.5,
        roll_offset_deg=1.0,
        enable_lever_arm_vel=True,
        enable_lever_arm_pos=True,
        enable_draft_offset=True
    )
    
    lat, lon, s_ve, s_vn, s_hdg, s_pitch, s_roll = apply_sensor_offsets_and_leverarm(
        times, raw_lat, raw_lon, raw_ve, raw_vn, raw_heading, raw_pitch, raw_roll, offsets
    )
    
    # Check heading bias
    np.testing.assert_allclose(s_hdg, raw_heading + 2.5)
    np.testing.assert_allclose(s_pitch, raw_pitch - 0.5)
    np.testing.assert_allclose(s_roll, raw_roll + 1.0)
    
    # Check position displacement (ADCP is displaced from GNSS)
    assert np.max(np.abs(lat - raw_lat)) > 1e-6, "Latitude should be displaced by lever arm"
    assert np.max(np.abs(lon - raw_lon)) > 1e-6, "Longitude should be displaced by lever arm"
    
    # Check lever-arm induced velocity (yaw rate r != 0 so lever-arm induced speed exists)
    assert np.max(np.abs(s_vn - raw_vn)) > 1e-3, "Lever-arm should induce velocity difference during turn"
    print("   Mathematical offset & lever-arm calculations verified!")
    
    print("2. Testing Pipeline integration with real SigVM dataset...")
    sample_file = r"01_VM-ADCP\Nortek\VM Acquisition\107628_20250828T135335UTC.SigVM"
    reader = SigVMReader(sample_file)
    ds = reader.load()
    
    pipeline = ProcessingPipeline(offsets=offsets)
    ds_proc = pipeline.process(ds)
    assert ds_proc.offsets.heading_offset_deg == 2.5
    assert ds_proc.offsets.transducer_draft_m == 4.5
    print("   Pipeline successfully processed dataset with custom offsets!")
    
    print("3. Testing GUI integration and Dialog interaction...")
    app = VMADCPApplication()
    app.dataset = ds
    app.update_idletasks()
    
    # Test setting offsets via callback
    app.current_offsets = offsets
    app.ctrl_panel.update_offset_summary(offsets)
    assert "LA: (10.0, 2.0, 3.0)m" in app.ctrl_panel.lbl_offset_summary.cget("text")
    assert "Hdg: +2.5°" in app.ctrl_panel.lbl_offset_summary.cget("text")
    
    # Test on_process
    app.on_process()
    app.update_idletasks()
    app.update()
    
    app.destroy()
    print("All Sensor Lever-Arm and Alignment Offset tests PASSED!")

if __name__ == "__main__":
    test_leverarm_and_offsets()
