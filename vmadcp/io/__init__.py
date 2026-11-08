import os
from .data_structures import VMADCPDataset, SensorOffsets
from .sigvm_reader import SigVMReader
from .rdi_reader import RDIReader

def load_adcp_dataset(filepath: str) -> VMADCPDataset:
    """
    Auto-detects format (Nortek SigVM/AD2CP or Teledyne RDI PD0) and loads the dataset.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")
        
    ext = os.path.splitext(filepath)[1].lower()
    
    # 1. Extension-based detection
    if ext in ('.sigvm', '.ad2cp'):
        return SigVMReader(filepath).load()
    elif ext in ('.pd0', '.enr', '.sta', '.lta', '.rdi', '.000'):
        return RDIReader(filepath).load()
        
    # 2. Header magic bytes detection
    with open(filepath, 'rb') as f:
        magic = f.read(16)
        
    if magic.startswith(b'PK\x03\x04'): # Zip container (SigVM)
        return SigVMReader(filepath).load()
    elif b'\xa5\x0a' in magic or b'\xa5\x15' in magic: # AD2CP sync
        return SigVMReader(filepath).load()
    elif magic.startswith(b'\x7f\x7f') or b'\x7f\x7f' in magic[:10]: # RDI PD0 sync
        return RDIReader(filepath).load()
    else:
        # Default try RDI, fallback to SigVM
        try:
            return RDIReader(filepath).load()
        except Exception:
            return SigVMReader(filepath).load()

__all__ = [
    "VMADCPDataset",
    "SensorOffsets",
    "SigVMReader",
    "RDIReader",
    "load_adcp_dataset",
]
