"""
VMADCP: Vessel Mounted ADCP Post-Processing System
"""
import os
import tempfile
import warnings

warnings.filterwarnings("ignore", category=RuntimeWarning, message=".*Mean of empty slice.*")
warnings.filterwarnings("ignore", category=RuntimeWarning, message=".*All-NaN slice encountered.*")

if "MPLCONFIGDIR" not in os.environ:
    mpl_dir = os.path.join(tempfile.gettempdir(), "vmadcp_mpl")
    os.makedirs(mpl_dir, exist_ok=True)
    os.environ["MPLCONFIGDIR"] = mpl_dir

from .io.data_structures import VMADCPDataset, SensorOffsets
from .io.sigvm_reader import SigVMReader
from .io.rdi_reader import RDIReader
from .io import load_adcp_dataset
from .processing.pipeline import ProcessingPipeline
from .processing.motion import estimate_bt_calibration
from .export.gmt_exporter import GMTExporter
from .export.data_exporter import DataExporter
from .gui.app import VMADCPApplication

__version__ = "1.1.0"
__all__ = [
    "VMADCPDataset",
    "SensorOffsets",
    "SigVMReader",
    "RDIReader",
    "load_adcp_dataset",
    "ProcessingPipeline",
    "estimate_bt_calibration",
    "GMTExporter",
    "DataExporter",
    "VMADCPApplication",
]
