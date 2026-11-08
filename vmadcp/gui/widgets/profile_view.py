"""
Profile view widget: renders 2D time-depth colormaps for Velocity, Backscatter, Correlation.
Safe colorbar and axis management across Matplotlib versions.
"""
import tkinter as tk
from tkinter import ttk
import numpy as np
import datetime
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
import matplotlib.dates as mdates

from ...io.data_structures import VMADCPDataset

class ProfileViewWidget(ttk.Frame):
    """Interactive 2D Time-Depth section visualization with seabed overlay."""
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        
        self.figure = Figure(figsize=(8, 5), dpi=100)
        self.figure.patch.set_facecolor('#1e222d')
        
        self.ax = self.figure.add_subplot(111)
        self._style_axis(self.ax)
        
        self.canvas = FigureCanvasTkAgg(self.figure, self)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        self.toolbar = NavigationToolbar2Tk(self.canvas, self)
        self.toolbar.config(background='#262b3d')
        for button in self.toolbar.winfo_children():
            try:
                button.config(background='#262b3d')
            except Exception:
                pass
        self.toolbar.update()
        self.toolbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.colorbar = None
        
    def _style_axis(self, ax):
        ax.set_facecolor('#181b24')
        ax.tick_params(colors='#e2e8f0', labelsize=8)
        for spine in ax.spines.values():
            spine.set_color('#3b4256')
        ax.xaxis.label.set_color('#e2e8f0')
        ax.yaxis.label.set_color('#e2e8f0')
        ax.title.set_color('#ffffff')
        ax.grid(True, linestyle='--', alpha=0.2, color='#ffffff')
        
    def plot_profile(self, ds: VMADCPDataset, variable_name: str = "current_speed"):
        """Plots the selected 2D field against time and depth safely."""
        # Clear entire figure to prevent Matplotlib colorbar subplotspec bugs
        self.figure.clear()
        self.ax = self.figure.add_subplot(111)
        self._style_axis(self.ax)
        self.colorbar = None
        
        if ds is None or ds.num_ensembles == 0:
            self.ax.text(0.5, 0.5, "No ADCP Dataset Loaded", 
                         color='#94a3b8', ha='center', va='center', transform=self.ax.transAxes)
            self.canvas.draw()
            return
            
        # Select data array and label
        cmap = "turbo"
        vmin, vmax = None, None
        title = ""
        
        if variable_name == "current_speed":
            data = ds.current_speed
            title = "Ocean Current Speed (m/s) [Absolute]"
            cmap = "viridis"
            vmin, vmax = 0.0, np.nanpercentile(data, 98) if not np.all(np.isnan(data)) else 1.0
        elif variable_name == "u_abs":
            data = ds.u_abs
            title = "East Velocity U (m/s) [Absolute]"
            cmap = "RdBu_r"
            limit = max(abs(np.nanpercentile(data, 2)), abs(np.nanpercentile(data, 98))) if not np.all(np.isnan(data)) else 0.5
            vmin, vmax = -limit, limit
        elif variable_name == "v_abs":
            data = ds.v_abs
            title = "North Velocity V (m/s) [Absolute]"
            cmap = "RdBu_r"
            limit = max(abs(np.nanpercentile(data, 2)), abs(np.nanpercentile(data, 98))) if not np.all(np.isnan(data)) else 0.5
            vmin, vmax = -limit, limit
        elif variable_name == "w_abs":
            data = ds.w_abs
            title = "Vertical Velocity W (m/s)"
            cmap = "coolwarm"
            vmin, vmax = -0.15, 0.15
        elif variable_name == "volume_backscatter_sv":
            data = ds.volume_backscatter_sv
            title = "Volume Backscattering Strength Sv (dB)"
            cmap = "plasma"
            vmin, vmax = np.nanpercentile(data, 5), np.nanpercentile(data, 98) if not np.all(np.isnan(data)) else (0, 80)
        elif variable_name == "echo_intensity":
            data = ds.echo_intensity_mean
            title = "Echo Intensity / RSSI (dB)"
            cmap = "inferno"
            vmin, vmax = np.nanpercentile(data, 5), np.nanpercentile(data, 98) if not np.all(np.isnan(data)) else (20, 100)
        elif variable_name == "correlation":
            data = np.nanmean(ds.raw_correlation, axis=2) if ds.raw_correlation.ndim == 3 else ds.raw_correlation
            title = "Acoustic Correlation (%)"
            cmap = "cividis"
            vmin, vmax = 0, 100
        else:
            data = ds.current_speed
            title = "Current Speed (m/s)"
            
        if data is None or data.size == 0 or data.ndim < 2 or data.shape[0] != len(ds.times):
            self.ax.text(0.5, 0.5, "Data Array Not Ready (Click 'Run Post-Processing')", 
                         color='#94a3b8', ha='center', va='center', transform=self.ax.transAxes)
            self.canvas.draw()
            return
            
        # Convert timestamps to matplotlib dates
        times_dt = [datetime.datetime.fromtimestamp(t, datetime.timezone.utc) for t in ds.times]
        times_num = mdates.date2num(times_dt)
        
        # 2D Meshgrid
        T, D = np.meshgrid(times_num, ds.depth_bins)
        
        # Pcolormesh (Transpose data so shape is (num_cells, N))
        mesh = self.ax.pcolormesh(T, D, data.T, cmap=cmap, vmin=vmin, vmax=vmax, shading='auto')
        
        # Invert depth axis (0 at surface, increasing downwards)
        self.ax.set_ylim(max(ds.depth_bins) * 1.05, 0)
        self.ax.xaxis_date()
        self.ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
        self.figure.autofmt_xdate(rotation=20)
        
        # Overlay Seabed Depth and Sidelobe Cutoff Line
        if ds.bt_valid.sum() > 0:
            bt_d = ds.bt_depth.copy()
            self.ax.plot(times_num, bt_d, color='#ff3366', linewidth=2.0, label='Seabed Depth (BT)')
            # Sidelobe cutoff line (d * cos(25 deg))
            th_rad = np.radians(ds.beam_angle_deg)
            sl_d = bt_d * np.cos(th_rad) - 0.5
            self.ax.plot(times_num, sl_d, color='#fbbf24', linestyle='--', linewidth=1.5, label='Sidelobe Cutoff')
            self.ax.legend(loc='lower left', facecolor='#262b3d', edgecolor='#3b4256', labelcolor='#ffffff', fontsize=8)
            
        self.ax.set_title(title, fontsize=10, fontweight='bold', pad=10)
        self.ax.set_xlabel("Time (UTC)", fontsize=9)
        self.ax.set_ylabel("Depth (m)", fontsize=9)
        
        # Add colorbar safely to the freshly created axis
        self.colorbar = self.figure.colorbar(mesh, ax=self.ax, orientation='vertical', pad=0.02, shrink=0.85)
        self.colorbar.ax.tick_params(colors='#e2e8f0', labelsize=8)
        for spine in self.colorbar.ax.spines.values():
            spine.set_color('#3b4256')
            
        self.figure.tight_layout()
        self.canvas.draw()
