"""
Track Map widget: interactive 2D cruise track chart and current vector overlay.
Adaptive scaling, no scientific notation offsets, responsive controls, and clear vector key.
"""
import tkinter as tk
from tkinter import ttk
import numpy as np
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
import matplotlib.ticker as ticker

from ...io.data_structures import VMADCPDataset

class TrackMapWidget(ttk.Frame):
    """Interactive Track Chart displaying vessel navigation and ADCP current vectors."""
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        
        self.dataset: VMADCPDataset = None
        self.cached_depth_min = 5.0
        self.cached_depth_max = 20.0
        
        # 1. Quick adjustment toolbar at the top of the map
        tb_frame = ttk.Frame(self, padding=(6, 4))
        tb_frame.pack(side=tk.TOP, fill=tk.X)
        
        ttk.Label(tb_frame, text="Vector Scale:").pack(side=tk.LEFT, padx=(4, 2))
        self.var_scale = tk.DoubleVar(value=1.0)
        scale_spin = ttk.Spinbox(tb_frame, from_=0.1, to=10.0, increment=0.2, textvariable=self.var_scale, width=5, command=self._replot_cached)
        scale_spin.pack(side=tk.LEFT, padx=(0, 10))
        scale_spin.bind("<Return>", lambda e: self._replot_cached())
        
        ttk.Label(tb_frame, text="Spacing (Decimate):").pack(side=tk.LEFT, padx=(4, 2))
        self.var_decimate = tk.IntVar(value=35)
        dec_spin = ttk.Spinbox(tb_frame, from_=5, to=200, increment=10, textvariable=self.var_decimate, width=5, command=self._replot_cached)
        dec_spin.pack(side=tk.LEFT, padx=(0, 10))
        dec_spin.bind("<Return>", lambda e: self._replot_cached())
        
        ttk.Label(tb_frame, text="Layer:").pack(side=tk.LEFT, padx=(4, 2))
        self.lbl_layer_info = ttk.Label(tb_frame, text="5.0m - 20.0m", font=("Segoe UI", 9, "bold"))
        self.lbl_layer_info.pack(side=tk.LEFT, padx=(0, 10))
        
        btn_refresh = tk.Button(
            tb_frame, text="🔄 Apply Scale",
            bg="#0284c7", fg="white", activebackground="#0369a1", activeforeground="white",
            font=("Segoe UI", 8, "bold"), relief=tk.RAISED, cursor="hand2", padx=8, pady=1,
            command=self._replot_cached
        )
        btn_refresh.pack(side=tk.LEFT, padx=5)
        
        # 2. Matplotlib Figure Canvas
        self.figure = Figure(figsize=(7, 6), dpi=100)
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
        ax.grid(True, linestyle='--', alpha=0.3, color='#38bdf8')
        
        # Disable scientific notation on coordinates (+1.2944e2)
        ax.ticklabel_format(useOffset=False, style='plain')
        ax.xaxis.set_major_formatter(ticker.FormatStrFormatter('%.4f°'))
        ax.yaxis.set_major_formatter(ticker.FormatStrFormatter('%.4f°'))
        
    def _replot_cached(self):
        if self.dataset is not None:
            self.plot_track(
                self.dataset,
                depth_min_m=self.cached_depth_min,
                depth_max_m=self.cached_depth_max,
                decimate_step=self.var_decimate.get(),
                vector_scale=self.var_scale.get()
            )
            
    def plot_track(self, ds: VMADCPDataset,
                   depth_min_m: float = 5.0,
                   depth_max_m: float = 20.0,
                   decimate_step: int = 35,
                   vector_scale: float = 1.0):
        """Renders the cruise track line and adaptively scaled velocity vectors."""
        self.dataset = ds
        self.cached_depth_min = depth_min_m
        self.cached_depth_max = depth_max_m
        self.lbl_layer_info.config(text=f"{depth_min_m:.1f}m - {depth_max_m:.1f}m")
        
        # Synchronize toolbar inputs
        if decimate_step != self.var_decimate.get():
            self.var_decimate.set(decimate_step)
        if vector_scale != self.var_scale.get():
            self.var_scale.set(vector_scale)
            
        # Clear entire figure to prevent colorbar subplotspec bugs
        self.figure.clear()
        self.ax = self.figure.add_subplot(111)
        self._style_axis(self.ax)
        self.colorbar = None
        
        if ds is None or ds.num_ensembles == 0:
            self.ax.text(0.5, 0.5, "No ADCP Navigation Data Loaded", 
                         color='#94a3b8', ha='center', va='center', transform=self.ax.transAxes)
            self.canvas.draw()
            return
            
        valid = (~np.isnan(ds.lat)) & (~np.isnan(ds.lon)) & (ds.lat != 0.0)
        if not np.any(valid):
            self.ax.text(0.5, 0.5, "No Valid GPS Coordinates Found", 
                         color='#ef4444', ha='center', va='center', transform=self.ax.transAxes)
            self.canvas.draw()
            return
            
        lons = ds.lon[valid]
        lats = ds.lat[valid]
        
        min_lon, max_lon = np.min(lons), np.max(lons)
        min_lat, max_lat = np.min(lats), np.max(lats)
        
        span_lon = max(max_lon - min_lon, 0.001)
        span_lat = max(max_lat - min_lat, 0.001)
        mean_lat = np.mean(lats)
        
        # Map aspect ratio corrected for latitude
        self.ax.set_aspect(1.0 / np.cos(np.radians(mean_lat)))
        
        # Margin around track
        pad_x = span_lon * 0.12
        pad_y = span_lat * 0.12
        self.ax.set_xlim(min_lon - pad_x, max_lon + pad_x)
        self.ax.set_ylim(min_lat - pad_y, max_lat + pad_y)
        
        # 1. Plot Cruise Track Line
        self.ax.plot(lons, lats, color='#cbd5e1', linestyle='-', linewidth=1.5, alpha=0.9, zorder=2, label='Cruise Track')
        
        # Start & End markers
        self.ax.scatter([lons[0]], [lats[0]], color='#10b981', s=70, zorder=6, edgecolors='white', linewidths=1.2, label='Start')
        self.ax.text(lons[0], lats[0], " Start", color='#10b981', fontsize=9, fontweight='bold', va='bottom', zorder=7)
        
        self.ax.scatter([lons[-1]], [lats[-1]], color='#ef4444', s=70, zorder=6, edgecolors='white', linewidths=1.2, label='End')
        self.ax.text(lons[-1], lats[-1], " End", color='#ef4444', fontsize=9, fontweight='bold', va='top', zorder=7)
        
        # 2. Extract layer-averaged current velocity (if processed)
        has_vel = (ds.u_abs is not None and ds.u_abs.size > 0 and ds.u_abs.ndim == 2 and ds.u_abs.shape[0] == len(ds.times))
        if has_vel:
            cell_mask = (ds.depth_bins >= depth_min_m) & (ds.depth_bins <= depth_max_m)
            if not np.any(cell_mask):
                cell_mask = np.ones(len(ds.depth_bins), dtype=bool)
                
            step = max(int(decimate_step), 1)
            dec_indices = np.arange(0, len(ds.times), step)
            dec_indices = [idx for idx in dec_indices if valid[idx]]
            
            u_dec = np.nanmean(ds.u_abs[dec_indices][:, cell_mask], axis=1)
            v_dec = np.nanmean(ds.v_abs[dec_indices][:, cell_mask], axis=1)
            x_dec = ds.lon[dec_indices]
            y_dec = ds.lat[dec_indices]
            
            speeds = np.sqrt(u_dec**2 + v_dec**2)
            valid_vecs = (~np.isnan(u_dec)) & (~np.isnan(v_dec)) & (speeds > 0.001)
        else:
            valid_vecs = np.array([], dtype=bool)
        
        if np.any(valid_vecs):
            # ADAPTIVE SCALING CALCULATION:
            # We want a 0.5 m/s current vector to occupy roughly 4% of the geographic map span.
            map_span_deg = max(span_lon, span_lat)
            ref_speed = 0.5 # m/s
            desired_ref_len_deg = map_span_deg * 0.045 * max(vector_scale, 0.05)
            
            deg_per_m_s = desired_ref_len_deg / ref_speed
            
            # Scaled vector components in geographic degrees
            u_plot = (u_dec[valid_vecs] / np.cos(np.radians(mean_lat))) * deg_per_m_s
            v_plot = v_dec[valid_vecs] * deg_per_m_s
            spd_valid = speeds[valid_vecs]
            
            # Quiver plot
            vmax_spd = max(float(np.nanpercentile(spd_valid, 95)), 0.5)
            q = self.ax.quiver(
                x_dec[valid_vecs], y_dec[valid_vecs],
                u_plot, v_plot,
                spd_valid,
                angles='xy', scale_units='xy', scale=1.0,
                cmap='turbo', clim=(0.0, vmax_spd),
                width=0.004, headwidth=3.5, headlength=4.5, headaxislength=4.0,
                zorder=5
            )
            
            # Quiver Key / Scale Legend
            # Place in bottom left or top left
            key_x = min_lon - pad_x * 0.5
            key_y = min_lat - pad_y * 0.5
            key_len = desired_ref_len_deg
            self.ax.quiver(
                [key_x], [key_y],
                [key_len], [0.0],
                angles='xy', scale_units='xy', scale=1.0,
                color='white', width=0.005, headwidth=3.5, headlength=4.5,
                zorder=6
            )
            self.ax.text(key_x + key_len*0.5, key_y - span_lat*0.025, f"{ref_speed:.1f} m/s", 
                         color='white', fontsize=8, fontweight='bold', ha='center', va='top')
            
            # Colorbar
            self.colorbar = self.figure.colorbar(q, ax=self.ax, orientation='vertical', pad=0.02, shrink=0.82)
            self.colorbar.set_label('Current Speed (m/s)', color='#e2e8f0', fontsize=8)
            self.colorbar.ax.tick_params(colors='#e2e8f0', labelsize=8)
            for spine in self.colorbar.ax.spines.values():
                spine.set_color('#3b4256')
                
        self.ax.set_title(f"Track Chart & Velocity Vectors [{depth_min_m:.1f}m - {depth_max_m:.1f}m]", 
                          fontsize=10, fontweight='bold', pad=10)
        self.ax.set_xlabel("Longitude (°E)", fontsize=9)
        self.ax.set_ylabel("Latitude (°N)", fontsize=9)
        self.ax.legend(loc='upper right', facecolor='#262b3d', edgecolor='#3b4256', labelcolor='#ffffff', fontsize=8)
        
        self.figure.tight_layout()
        self.canvas.draw()
