import os
import sys

sys.path.insert(0, os.path.abspath("."))
from vmadcp.io.sigvm_reader import SigVMReader
from vmadcp.processing.pipeline import ProcessingPipeline
from vmadcp.gui.widgets.track_map import TrackMapWidget
import tkinter as tk

def test_track_scaling_render():
    sample_file = r"01_VM-ADCP\Nortek\VM Acquisition\107628_20261029T042301UTC.SigVM"
    reader = SigVMReader(sample_file)
    ds = reader.load()
    
    pipeline = ProcessingPipeline()
    ds_proc = pipeline.process(ds)
    
    root = tk.Tk()
    tm = TrackMapWidget(root)
    tm.pack(fill=tk.BOTH, expand=True)
    
    # Test plot with adaptive scaling
    tm.plot_track(ds_proc, depth_min_m=5.0, depth_max_m=20.0, decimate_step=35, vector_scale=1.0)
    
    # Save figure to verify
    out_img = r"tests\output_track_preview.png"
    tm.figure.savefig(out_img, dpi=120)
    print("Saved preview to:", out_img)
    
    root.destroy()
    print("Track map scaling test completed successfully!")

if __name__ == "__main__":
    test_track_scaling_render()
