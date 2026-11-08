"""
Entry point for VM-ADCP Post-Processing Studio Desktop Application.
Usage:
    python run_app.py
    python run_app.py [path_to_sigvm_file]
"""
import sys
import os
import tempfile

# Configure writable Matplotlib directory
if "MPLCONFIGDIR" not in os.environ:
    mpl_dir = os.path.join(tempfile.gettempdir(), "vmadcp_mpl")
    os.makedirs(mpl_dir, exist_ok=True)
    os.environ["MPLCONFIGDIR"] = mpl_dir

# Ensure package root is in python path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from vmadcp.gui.app import VMADCPApplication

def main():
    app = VMADCPApplication()
    
    # If a file path was passed via CLI, automatically load it
    if len(sys.argv) > 1:
        filepath = os.path.abspath(sys.argv[1])
        if os.path.exists(filepath):
            app.after(200, lambda: app._load_file_async(filepath))
            
    app.mainloop()

if __name__ == "__main__":
    main()
