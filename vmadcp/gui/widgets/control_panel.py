"""
Control panel widget: post-processing parameter inputs and action buttons.
Robust design with safe variable parsing and distinct input field styling.
Includes quick access to Sensor Lever-Arm & Attitude Offset configuration.
"""
import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, Any

from ...io.data_structures import SensorOffsets
from ..styles import THEME, FONT_HEADER, FONT_REGULAR, FONT_BOLD

def safe_float(val_str: str, default: float) -> float:
    try:
        return float(str(val_str).strip())
    except (ValueError, TypeError):
        return default

def safe_int(val_str: str, default: int) -> int:
    try:
        return int(float(str(val_str).strip()))
    except (ValueError, TypeError):
        return default

class ControlPanelWidget(ttk.Frame):
    """Sidebar for adjusting motion, bottom-track, backscatter, and GMT parameters."""
    
    def __init__(self, parent,
                 on_process: Callable[[], None],
                 on_auto_calibrate: Callable[[], None],
                 on_configure_offsets: Callable[[], None],
                 on_export_gmt: Callable[[], None],
                 on_export_data: Callable[[], None],
                 **kwargs):
        super().__init__(parent, **kwargs)
        
        self.on_process = on_process
        self.on_auto_calibrate = on_auto_calibrate
        self.on_configure_offsets = on_configure_offsets
        self.on_export_gmt = on_export_gmt
        self.on_export_data = on_export_data
        
        self.offsets = SensorOffsets()
        self._build_ui()
        
    def _create_entry(self, parent, text_var: tk.StringVar, width: int = 8) -> tk.Entry:
        """Creates a styled, highly visible Entry field."""
        entry = tk.Entry(
            parent,
            textvariable=text_var,
            width=width,
            bg="#111827",
            fg="#38bdf8",
            insertbackground="white",
            relief=tk.SOLID,
            bd=1,
            highlightthickness=1,
            highlightcolor="#38bdf8",
            highlightbackground="#374151",
            font=("Segoe UI", 9, "bold")
        )
        return entry
        
    def _build_ui(self):
        # 1. Top Scrollable Area for Parameters
        scroll_container = ttk.Frame(self)
        scroll_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(scroll_container, bg=THEME["bg_panel"], highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(scroll_container, orient="vertical", command=self.canvas.yview)
        self.scroll_content = ttk.Frame(self.canvas)
        
        self.scroll_window = self.canvas.create_window((0, 0), window=self.scroll_content, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.yview_moveto(0.0)
        
        # Configure scrollregion and dynamic width
        def on_configure(event):
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            self.canvas.itemconfig(self.scroll_window, width=event.width)
            
        self.canvas.bind("<Configure>", on_configure)
        self.scroll_content.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        def _on_mousewheel(event):
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            
        self.canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        # --- Section 1: Motion Correction & Misalignment ---
        f_motion = ttk.LabelFrame(self.scroll_content, text="  1. Motion & Misalignment Correction  ", padding=8)
        f_motion.pack(fill=tk.X, padx=6, pady=4)
        
        # Sensor Offsets Button & Status
        btn_offsets = tk.Button(
            f_motion, text="⚙ Sensor Offsets & Lever-Arm...",
            bg="#334155", fg="#38bdf8", activebackground="#1e293b", activeforeground="white",
            font=("Segoe UI", 8, "bold"), relief=tk.RAISED, cursor="hand2", bd=1, pady=3,
            command=self.on_configure_offsets
        )
        btn_offsets.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(2, 4))
        
        self.lbl_offset_summary = tk.Label(
            f_motion, text="LA: (0.0, 0.0, 0.0)m | Hdg: +0.0°",
            bg=THEME["bg_panel"], fg="#94a3b8", font=("Consolas", 8)
        )
        self.lbl_offset_summary.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        
        ttk.Label(f_motion, text="Misalignment Angle φ (°):").grid(row=2, column=0, sticky="w", pady=3)
        self.var_phi = tk.StringVar(value="0.0")
        self._create_entry(f_motion, self.var_phi, width=10).grid(row=2, column=1, sticky="e", pady=3)
        
        ttk.Label(f_motion, text="Amplitude Scale Factor A:").grid(row=3, column=0, sticky="w", pady=3)
        self.var_amp = tk.StringVar(value="1.000")
        self._create_entry(f_motion, self.var_amp, width=10).grid(row=3, column=1, sticky="e", pady=3)
        
        ttk.Label(f_motion, text="Velocity Reference:").grid(row=4, column=0, sticky="w", pady=3)
        self.var_ref = tk.StringVar(value="GNSS")
        cb_ref = ttk.Combobox(f_motion, textvariable=self.var_ref, values=["GNSS", "BottomTrack"], width=11, state="readonly")
        cb_ref.grid(row=4, column=1, sticky="e", pady=3)
        
        btn_cal = tk.Button(
            f_motion, text="⚡ Auto-Calibrate (BT vs GPS)", 
            bg=THEME["accent_blue"], fg="white", activebackground="#0369a1", activeforeground="white",
            font=FONT_REGULAR, relief=tk.RAISED, cursor="hand2", bd=1,
            command=self.on_auto_calibrate
        )
        btn_cal.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(6, 2))
        
        # --- Section 2: Bottom Tracking & Sidelobe ---
        f_bt = ttk.LabelFrame(self.scroll_content, text="  2. Bottom Tracking & Sidelobe  ", padding=8)
        f_bt.pack(fill=tk.X, padx=6, pady=4)
        
        self.var_sidelobe = tk.BooleanVar(value=True)
        cb_sl = ttk.Checkbutton(f_bt, text="Enable Sidelobe Cutoff (D·cosθ)", variable=self.var_sidelobe)
        cb_sl.grid(row=0, column=0, columnspan=2, sticky="w", pady=3)
        
        ttk.Label(f_bt, text="Safety Margin (m):").grid(row=1, column=0, sticky="w", pady=3)
        self.var_sl_margin = tk.StringVar(value="0.5")
        self._create_entry(f_bt, self.var_sl_margin, width=10).grid(row=1, column=1, sticky="e", pady=3)
        
        # --- Section 3: Backscatter Processing ---
        f_bs = ttk.LabelFrame(self.scroll_content, text="  3. Acoustic Backscatter (Sv)  ", padding=8)
        f_bs.pack(fill=tk.X, padx=6, pady=4)
        
        ttk.Label(f_bs, text="Salinity (PSU):").grid(row=0, column=0, sticky="w", pady=3)
        self.var_salinity = tk.StringVar(value="34.5")
        self._create_entry(f_bs, self.var_salinity, width=10).grid(row=0, column=1, sticky="e", pady=3)
        
        ttk.Label(f_bs, text="Noise Floor (counts):").grid(row=1, column=0, sticky="w", pady=3)
        self.var_noise = tk.StringVar(value="25.0")
        self._create_entry(f_bs, self.var_noise, width=10).grid(row=1, column=1, sticky="e", pady=3)
        
        # --- Section 4: Quality Control Filters ---
        f_qc = ttk.LabelFrame(self.scroll_content, text="  4. Quality Control Filters  ", padding=8)
        f_qc.pack(fill=tk.X, padx=6, pady=4)
        
        ttk.Label(f_qc, text="Min Correlation (%):").grid(row=0, column=0, sticky="w", pady=3)
        self.var_min_cor = tk.StringVar(value="50.0")
        self._create_entry(f_qc, self.var_min_cor, width=10).grid(row=0, column=1, sticky="e", pady=3)
        
        ttk.Label(f_qc, text="Max Error Vel (m/s):").grid(row=1, column=0, sticky="w", pady=3)
        self.var_max_err = tk.StringVar(value="0.30")
        self._create_entry(f_qc, self.var_max_err, width=10).grid(row=1, column=1, sticky="e", pady=3)
        
        ttk.Label(f_qc, text="Min Percent Good (%):").grid(row=2, column=0, sticky="w", pady=3)
        self.var_min_pg = tk.StringVar(value="25.0")
        self._create_entry(f_qc, self.var_min_pg, width=10).grid(row=2, column=1, sticky="e", pady=3)
        
        ttk.Label(f_qc, text="Max Tilt Angle (°):").grid(row=3, column=0, sticky="w", pady=3)
        self.var_max_tilt = tk.StringVar(value="15.0")
        self._create_entry(f_qc, self.var_max_tilt, width=10).grid(row=3, column=1, sticky="e", pady=3)
        
        ttk.Label(f_qc, text="Max Vert Vel (m/s):").grid(row=4, column=0, sticky="w", pady=3)
        self.var_max_w = tk.StringVar(value="0.80")
        self._create_entry(f_qc, self.var_max_w, width=10).grid(row=4, column=1, sticky="e", pady=3)
        
        self.var_despike = tk.BooleanVar(value=True)
        ttk.Checkbutton(f_qc, text="Apply 2D Median Despike", variable=self.var_despike).grid(row=5, column=0, columnspan=2, sticky="w", pady=3)
        
        # --- Section 5: Track Chart & GMT Settings ---
        f_gmt = ttk.LabelFrame(self.scroll_content, text="  5. Track Chart & GMT Layer  ", padding=8)
        f_gmt.pack(fill=tk.X, padx=6, pady=4)
        
        ttk.Label(f_gmt, text="Layer Min Depth (m):").grid(row=0, column=0, sticky="w", pady=3)
        self.var_layer_min = tk.StringVar(value="5.0")
        self._create_entry(f_gmt, self.var_layer_min, width=10).grid(row=0, column=1, sticky="e", pady=3)
        
        ttk.Label(f_gmt, text="Layer Max Depth (m):").grid(row=1, column=0, sticky="w", pady=3)
        self.var_layer_max = tk.StringVar(value="20.0")
        self._create_entry(f_gmt, self.var_layer_max, width=10).grid(row=1, column=1, sticky="e", pady=3)
        
        ttk.Label(f_gmt, text="Vector Decimation:").grid(row=2, column=0, sticky="w", pady=3)
        self.var_decimate = tk.StringVar(value="35")
        self._create_entry(f_gmt, self.var_decimate, width=10).grid(row=2, column=1, sticky="e", pady=3)
        
        ttk.Label(f_gmt, text="Vector Scale Factor:").grid(row=3, column=0, sticky="w", pady=3)
        self.var_vec_scale = tk.StringVar(value="1.0")
        self._create_entry(f_gmt, self.var_vec_scale, width=10).grid(row=3, column=1, sticky="e", pady=3)
        
        # --- 2. Fixed Bottom Dock for Action Buttons ---
        f_dock = tk.Frame(self, bg=THEME["bg_card"], bd=1, relief=tk.SOLID, padx=8, pady=8)
        f_dock.pack(side=tk.BOTTOM, fill=tk.X, padx=4, pady=4)
        
        btn_proc = tk.Button(
            f_dock, text="▶ Run Post-Processing",
            bg="#059669", fg="white", activebackground="#047857", activeforeground="white",
            font=FONT_HEADER, relief=tk.RAISED, cursor="hand2", bd=2, pady=7,
            command=self.on_process
        )
        btn_proc.pack(fill=tk.X, pady=(2, 4))
        
        btn_gmt = tk.Button(
            f_dock, text="🗺 Export GMT Track Chart",
            bg="#7c3aed", fg="white", activebackground="#6d28d9", activeforeground="white",
            font=FONT_REGULAR, relief=tk.RAISED, cursor="hand2", bd=1, pady=4,
            command=self.on_export_gmt
        )
        btn_gmt.pack(fill=tk.X, pady=2)
        
        btn_exp = tk.Button(
            f_dock, text="💾 Export CSV / NetCDF",
            bg="#374151", fg="white", activebackground="#1f2937", activeforeground="white",
            font=FONT_REGULAR, relief=tk.RAISED, cursor="hand2", bd=1, pady=4,
            command=self.on_export_data
        )
        btn_exp.pack(fill=tk.X, pady=2)

    def update_offset_summary(self, o: SensorOffsets):
        """Updates the offset summary label in Section 1."""
        self.offsets = o
        mag_str = f" | Dec: {o.magnetic_declination_deg:+.1f}°" if abs(getattr(o, 'magnetic_declination_deg', 0.0)) > 1e-4 else ""
        self.lbl_offset_summary.config(
            text=f"LA: ({o.lever_arm_x_m:.1f}, {o.lever_arm_y_m:.1f}, {o.lever_arm_z_m:.1f})m | Hdg: {o.heading_offset_deg:+.1f}°{mag_str}"
        )

    def get_pipeline_params(self) -> Dict[str, Any]:
        """Returns dictionary of pipeline parameters with safe fallback defaults."""
        return {
            'offsets': self.offsets,
            'misalignment_deg': safe_float(self.var_phi.get(), 0.0),
            'amplitude_scale': safe_float(self.var_amp.get(), 1.0),
            'velocity_reference': self.var_ref.get(),
            'enable_sidelobe_mask': bool(self.var_sidelobe.get()),
            'sidelobe_margin_m': safe_float(self.var_sl_margin.get(), 0.5),
            'min_correlation_pct': safe_float(self.var_min_cor.get(), 50.0),
            'max_error_vel_m_s': safe_float(self.var_max_err.get(), 0.30),
            'min_percent_good_pct': safe_float(self.var_min_pg.get(), 25.0),
            'max_tilt_deg': safe_float(self.var_max_tilt.get(), 15.0),
            'max_vertical_spd_m_s': safe_float(self.var_max_w.get(), 0.80),
            'enable_despike': bool(self.var_despike.get()),
            'salinity_psu': safe_float(self.var_salinity.get(), 34.5),
            'noise_floor_counts': safe_float(self.var_noise.get(), 25.0),
        }
        
    def get_gmt_params(self) -> Dict[str, Any]:
        """Returns dictionary of GMT export parameters with safe fallback defaults."""
        return {
            'depth_min_m': safe_float(self.var_layer_min.get(), 5.0),
            'depth_max_m': safe_float(self.var_layer_max.get(), 20.0),
            'decimate_step': safe_int(self.var_decimate.get(), 35),
            'vector_scale': safe_float(self.var_vec_scale.get(), 1.0),
        }
        
    def set_calibration_results(self, phi: float, amplitude: float):
        """Updates UI entries with auto-calibrated values."""
        self.var_phi.set(f"{phi:.3f}")
        self.var_amp.set(f"{amplitude:.4f}")
