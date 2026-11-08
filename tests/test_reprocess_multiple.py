import os
import sys

sys.path.insert(0, os.path.abspath("."))
from vmadcp.io.sigvm_reader import SigVMReader
from vmadcp.gui.app import VMADCPApplication

def test_multiple_reprocess_and_view_switching():
    print("Testing continuous reprocessing and colorbar removal...")
    sample_file = r"01_VM-ADCP\Nortek\VM Acquisition\107628_20250828T135335UTC.SigVM"
    reader = SigVMReader(sample_file)
    ds = reader.load()
    
    app = VMADCPApplication()
    app.dataset = ds
    
    # 1. First render
    app._update_all_views()
    
    # 2. Continuous view changes
    for var_label in [
        "Absolute Current Speed (m/s)",
        "Absolute East Velocity U (m/s)",
        "Absolute North Velocity V (m/s)",
        "Vertical Velocity W (m/s)",
        "Acoustic Correlation (%)",
        "Absolute Current Speed (m/s)"
    ]:
        print(f"Switching velocity view to: {var_label}")
        app.var_vel_label.set(var_label)
        app._update_vel_plot()
        
    for bs_label in [
        "Volume Backscattering Strength Sv (dB)",
        "Echo Intensity / RSSI (dB)",
        "Volume Backscattering Strength Sv (dB)"
    ]:
        print(f"Switching backscatter view to: {bs_label}")
        app.var_bs_label.set(bs_label)
        app._update_bs_plot()
        
    # 3. Simulate multiple Post-Processing cycles
    for cycle in range(3):
        print(f"Executing post-processing cycle #{cycle+1}")
        app.on_process()
        app.update_idletasks()
        app.update()
        app._update_all_views()
        
    app.destroy()
    print("SUCCESS: No colorbar set_subplotspec error occurred across all cycles!")

if __name__ == "__main__":
    test_multiple_reprocess_and_view_switching()
