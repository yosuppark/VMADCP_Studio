import os
import sys

sys.path.insert(0, os.path.abspath("."))
from vmadcp.gui.app import VMADCPApplication
from vmadcp.io.sigvm_reader import SigVMReader

def test_gui_interactive_elements():
    print("Testing GUI interactive elements and entries...")
    app = VMADCPApplication()
    app.update_idletasks()
    
    # 1. Test Control Panel Entry Values
    cp = app.ctrl_panel
    print("Initial phi:", cp.var_phi.get())
    print("Initial amp:", cp.var_amp.get())
    print("Initial min_cor:", cp.var_min_cor.get())
    
    assert cp.var_phi.get() == "0.0"
    assert cp.var_amp.get() == "1.000"
    assert cp.var_min_cor.get() == "50.0"
    
    # 2. Simulate User Input in Entries
    cp.var_phi.set("2.35")
    cp.var_amp.set("1.015")
    cp.var_min_cor.set("65.0")
    
    params = cp.get_pipeline_params()
    print("Parsed pipeline params with user input:", params)
    assert params["misalignment_deg"] == 2.35
    assert params["amplitude_scale"] == 1.015
    assert params["min_correlation_pct"] == 65.0
    
    # 3. Simulate Empty string input (should safely fallback, not crash)
    cp.var_phi.set("")
    cp.var_amp.set("   ")
    params_fallback = cp.get_pipeline_params()
    print("Fallback on empty input:", params_fallback["misalignment_deg"], params_fallback["amplitude_scale"])
    assert params_fallback["misalignment_deg"] == 0.0
    assert params_fallback["amplitude_scale"] == 1.0
    
    # 4. Load small dataset and trigger processing
    sample_file = r"01_VM-ADCP\Nortek\VM Acquisition\107628_20250828T135335UTC.SigVM"
    reader = SigVMReader(sample_file)
    app.dataset = reader.load()
    
    # Test on_process directly
    print("Triggering on_process...")
    app.on_process()
    app.update_idletasks()
    app.update()
    
    # Test tab change and updates
    app._update_all_views()
    app._generate_qc_report()
    
    app.destroy()
    print("All GUI interactive element tests passed!")

if __name__ == "__main__":
    test_gui_interactive_elements()
