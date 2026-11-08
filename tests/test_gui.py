import os
import sys

sys.path.insert(0, os.path.abspath("."))
from vmadcp.gui.app import VMADCPApplication

def test_gui_launch():
    print("Launching VMADCPApplication for verification...")
    app = VMADCPApplication()
    app.update_idletasks()
    app.update()
    print("Window initialized successfully!")
    app.destroy()
    print("Window closed successfully!")

if __name__ == "__main__":
    test_gui_launch()
