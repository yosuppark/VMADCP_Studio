import os
import sys

sys.path.insert(0, os.path.abspath("."))
from vmadcp.io.sigvm_reader import SigVMReader
from vmadcp.processing.pipeline import ProcessingPipeline
from vmadcp.export.gmt_exporter import GMTExporter
from vmadcp.gui.app import VMADCPApplication

def test_full_pipeline_with_large_dataset():
    sample_file = r"01_VM-ADCP\Nortek\VM Acquisition\107628_20261029T042301UTC.SigVM"
    print("1. Loading SigVM dataset:", sample_file)
    reader = SigVMReader(sample_file)
    ds = reader.load()
    print(f"   Ensembles: {ds.num_ensembles}, Cells: {ds.num_cells}, Beams: {ds.num_beams}")
    
    print("2. Running Processing Pipeline...")
    pipeline = ProcessingPipeline(
        misalignment_deg=0.0,
        amplitude_scale=1.0,
        velocity_reference="GNSS",
        enable_sidelobe_mask=True,
        min_correlation_pct=50.0
    )
    ds_proc = pipeline.process(ds)
    print("   Valid ocean velocity cells:", ds_proc.mask_valid.sum())
    
    print("3. Exporting GMT Track Chart...")
    gmt_exp = GMTExporter(ds_proc)
    out_dir = r"tests\output_large_gmt"
    files = gmt_exp.export(out_dir, depth_layer_min_m=5.0, depth_layer_max_m=20.0, decimate_step=20)
    for k, v in files.items():
        print(f"   [{k}] -> {v}")
        
    print("4. Testing GUI rendering with loaded dataset...")
    app = VMADCPApplication()
    app.dataset = ds_proc
    app._update_all_views()
    app._generate_qc_report()
    app.update_idletasks()
    app.update()
    app.destroy()
    print("5. All E2E stages succeeded!")

if __name__ == "__main__":
    test_full_pipeline_with_large_dataset()
