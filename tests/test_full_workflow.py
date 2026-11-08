"""
Integration tests for the VM-ADCP post-processing workflow.
"""
import os
import sys
import shutil

# Ensure current workspace root is in sys.path
sys.path.insert(0, os.path.abspath("."))

import pytest
import numpy as np
from vmadcp.io.sigvm_reader import SigVMReader
from vmadcp.processing.pipeline import ProcessingPipeline
from vmadcp.export.gmt_exporter import GMTExporter
from vmadcp.export.data_exporter import DataExporter

SAMPLE_SIGVM = r"01_VM-ADCP\Nortek\VM Acquisition\107628_20250828T135335UTC.SigVM"
TEST_OUTPUT_DIR = r"tests\output_test"

def test_reader_and_pipeline():
    assert os.path.exists(SAMPLE_SIGVM), "Sample SigVM file does not exist"
    
    # 1. Load Data
    reader = SigVMReader(SAMPLE_SIGVM)
    ds = reader.load()
    assert ds.num_ensembles > 0, "No ensembles parsed"
    assert ds.num_cells == 139, f"Expected 139 cells, got {ds.num_cells}"
    assert ds.num_beams == 4, f"Expected 4 beams, got {ds.num_beams}"
    
    # 2. Process
    pipeline = ProcessingPipeline(
        misalignment_deg=1.5,
        amplitude_scale=1.02,
        velocity_reference="GNSS",
        enable_sidelobe_mask=True,
        min_correlation_pct=40.0
    )
    ds_proc = pipeline.process(ds)
    
    assert ds_proc.u_abs.shape == (ds.num_ensembles, ds.num_cells)
    assert ds_proc.v_abs.shape == (ds.num_ensembles, ds.num_cells)
    assert ds_proc.volume_backscatter_sv.shape == (ds.num_ensembles, ds.num_cells)
    assert ds_proc.mask_valid.shape == (ds.num_ensembles, ds.num_cells)
    
    # 3. Export GMT
    if os.path.exists(TEST_OUTPUT_DIR):
        shutil.rmtree(TEST_OUTPUT_DIR)
        
    gmt_exp = GMTExporter(ds_proc)
    gmt_files = gmt_exp.export(TEST_OUTPUT_DIR, depth_layer_min_m=2.0, depth_layer_max_m=10.0)
    
    assert os.path.exists(gmt_files["track"]), "track_line.txt not created"
    assert os.path.exists(gmt_files["vectors"]), "current_vectors.txt not created"
    assert os.path.exists(gmt_files["bat_script"]), "plot_track_chart.bat not created"
    assert os.path.exists(gmt_files["sh_script"]), "plot_track_chart.sh not created"
    
    # Check GMT script content
    with open(gmt_files["bat_script"], "r", encoding="utf-8") as f:
        bat_content = f.read()
    assert "gmt begin" in bat_content
    assert "gmt velo current_vectors.txt" in bat_content
    assert "gmt end show" in bat_content
    
    # 4. Export CSV & HDF5
    data_exp = DataExporter(ds_proc)
    csv_file = os.path.join(TEST_OUTPUT_DIR, "summary.csv")
    data_exp.export_csv_summary(csv_file)
    assert os.path.exists(csv_file)
    
    h5_file = os.path.join(TEST_OUTPUT_DIR, "dataset.h5")
    data_exp.export_hdf5_netcdf(h5_file)
    assert os.path.exists(h5_file)

if __name__ == "__main__":
    test_reader_and_pipeline()
    print("ALL TESTS PASSED SUCCESSFULLY!")
