"""
Main desktop GUI application for Vessel Mounted ADCP post-processing.
Includes Sensor Lever-Arm & Attitude Offset configuration menu and dialog.
"""
import os
import sys
import traceback
import threading
import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import numpy as np

from ..io.sigvm_reader import SigVMReader
from ..io.rdi_reader import RDIReader
from ..io import load_adcp_dataset
from ..io.data_structures import VMADCPDataset, SensorOffsets
from ..processing.pipeline import ProcessingPipeline
from ..processing.motion import estimate_bt_calibration
from ..export.gmt_exporter import GMTExporter
from ..export.data_exporter import DataExporter

from .widgets.profile_view import ProfileViewWidget
from .widgets.track_map import TrackMapWidget
from .widgets.control_panel import ControlPanelWidget
from .widgets.offset_dialog import SensorOffsetDialog
from .styles import THEME, FONT_TITLE, FONT_HEADER, FONT_REGULAR, FONT_BOLD, FONT_CODE

# Display name to internal variable key mapping
VEL_OPTIONS = {
    "Absolute Current Speed (m/s)": "current_speed",
    "Absolute East Velocity U (m/s)": "u_abs",
    "Absolute North Velocity V (m/s)": "v_abs",
    "Vertical Velocity W (m/s)": "w_abs",
    "Acoustic Correlation (%)": "correlation",
}

BS_OPTIONS = {
    "Volume Backscattering Strength Sv (dB)": "volume_backscatter_sv",
    "Echo Intensity / RSSI (dB)": "echo_intensity",
}

class VMADCPApplication(tk.Tk):
    """Vessel Mounted ADCP Post-Processing Desktop Program."""
    
    def __init__(self):
        super().__init__()
        
        self.title("VM-ADCP Post-Processing Studio - [Vessel Mounted ADCP Analyzer]")
        self.geometry("1440x920")
        self.minsize(1100, 700)
        self.configure(bg=THEME["bg_main"])
        
        self.dataset: VMADCPDataset = None
        self.current_filepath: str = ""
        self.current_offsets = SensorOffsets()
        self._is_processing = False
        
        self._setup_styles()
        self._build_menu()
        self._build_layout()
        self._update_status("Ready. Please open an ADCP dataset (.SigVM / .AD2CP).")
        
    def _setup_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use('clam')
        except Exception:
            pass
            
        style.configure(".", background=THEME["bg_main"], foreground=THEME["text_primary"])
        style.configure("TFrame", background=THEME["bg_main"])
        style.configure("TLabel", background=THEME["bg_main"], foreground=THEME["text_primary"], font=FONT_REGULAR)
        style.configure("TLabelframe", background=THEME["bg_panel"], foreground=THEME["text_accent"], bordercolor=THEME["border"])
        style.configure("TLabelframe.Label", background=THEME["bg_panel"], foreground=THEME["text_accent"], font=FONT_HEADER)
        style.configure("TCheckbutton", background=THEME["bg_panel"], foreground=THEME["text_primary"], font=FONT_REGULAR)
        style.configure("TNotebook", background=THEME["bg_main"], bordercolor=THEME["border"])
        style.configure("TNotebook.Tab", background=THEME["bg_card"], foreground=THEME["text_secondary"], font=FONT_BOLD, padding=[14, 6])
        style.map("TNotebook.Tab", background=[("selected", THEME["bg_panel"])], foreground=[("selected", THEME["text_accent"])])
        
        style.configure("TEntry", fieldbackground="#111827", foreground="#38bdf8", insertcolor="white")
        style.configure("TCombobox", fieldbackground="#111827", foreground="#ffffff", selectbackground="#0284c7")
        style.map("TCombobox", fieldbackground=[("readonly", "#111827")], foreground=[("readonly", "#ffffff")])
        
    def _build_menu(self):
        menubar = tk.Menu(self, bg=THEME["bg_card"], fg="white", activebackground=THEME["accent_blue"])
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0, bg=THEME["bg_card"], fg="white")
        file_menu.add_command(label="Open ADCP Data File (Auto-Detect)...", command=self.on_open_file, accelerator="Ctrl+O")
        file_menu.add_separator()
        file_menu.add_command(label="Open Teledyne RDI PD0 (*.pd0, *.enr, *.sta, *.lta)...", command=lambda: self.on_open_file(format_hint="RDI"))
        file_menu.add_command(label="Open Nortek SigVM (*.SigVM, *.AD2CP)...", command=lambda: self.on_open_file(format_hint="Nortek"))
        file_menu.add_separator()
        file_menu.add_command(label="Merge Multi-part PD0 Files (pyadps-cat)...", command=self.on_merge_pd0_files)
        file_menu.add_separator()
        file_menu.add_command(label="Export GMT Track Chart & Script...", command=self.on_export_gmt, accelerator="Ctrl+G")
        file_menu.add_command(label="Export Processed CSV Summary...", command=self.on_export_csv)
        file_menu.add_command(label="Export Full Dataset (HDF5/NetCDF)...", command=self.on_export_netcdf)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.destroy)
        menubar.add_cascade(label="File", menu=file_menu)
        
        # Settings menu (Sensor Offsets & Lever-Arm)
        settings_menu = tk.Menu(menubar, tearoff=0, bg=THEME["bg_card"], fg="white")
        settings_menu.add_command(label="Sensor Offsets & Lever-Arm...", command=self.on_configure_offsets, accelerator="Ctrl+L")
        menubar.add_cascade(label="Settings", menu=settings_menu)
        
        # Processing menu
        proc_menu = tk.Menu(menubar, tearoff=0, bg=THEME["bg_card"], fg="white")
        proc_menu.add_command(label="Run Post-Processing Pipeline", command=self.on_process, accelerator="F5")
        proc_menu.add_command(label="Configure Sensor Offsets & Lever-Arm...", command=self.on_configure_offsets)
        proc_menu.add_command(label="Estimate Misalignment (BT vs GPS)", command=self.on_auto_calibrate)
        menubar.add_cascade(label="Processing", menu=proc_menu)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0, bg=THEME["bg_card"], fg="white")
        help_menu.add_command(label="Processing Theory & Documentation", command=self._show_documentation)
        help_menu.add_command(label="About", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        
        self.config(menu=menubar)
        self.bind("<Control-o>", lambda e: self.on_open_file())
        self.bind("<Control-l>", lambda e: self.on_configure_offsets())
        self.bind("<Control-g>", lambda e: self.on_export_gmt())
        self.bind("<F5>", lambda e: self.on_process())

    def _build_layout(self):
        # Top banner with file info and quick actions
        top_bar = ttk.Frame(self, padding=(10, 6))
        top_bar.pack(side=tk.TOP, fill=tk.X)
        
        lbl_app = tk.Label(top_bar, text="VM-ADCP Studio", font=FONT_TITLE, bg=THEME["bg_main"], fg=THEME["text_accent"])
        lbl_app.pack(side=tk.LEFT, padx=(0, 15))
        
        self.lbl_file_info = tk.Label(top_bar, text="No file loaded", font=FONT_REGULAR, bg=THEME["bg_main"], fg=THEME["text_secondary"])
        self.lbl_file_info.pack(side=tk.LEFT)
        
        btn_open = tk.Button(
            top_bar, text="📂 Open ADCP (RDI / Nortek)", 
            bg=THEME["accent_blue"], fg="white", activebackground="#0369a1", activeforeground="white",
            font=FONT_HEADER, relief=tk.RAISED, cursor="hand2", padx=12, pady=4,
            command=self.on_open_file
        )
        btn_open.pack(side=tk.RIGHT, padx=5)
        
        btn_top_offsets = tk.Button(
            top_bar, text="⚙ Sensor Offsets...",
            bg="#334155", fg="#38bdf8", activebackground="#1e293b", activeforeground="white",
            font=FONT_REGULAR, relief=tk.RAISED, cursor="hand2", padx=10, pady=4,
            command=self.on_configure_offsets
        )
        btn_top_offsets.pack(side=tk.RIGHT, padx=5)
        
        # Main content area: Split into Sidebar and Center Notebook
        content = ttk.Frame(self)
        content.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=4)
        
        # Left Sidebar (Control Panel)
        self.ctrl_panel = ControlPanelWidget(
            content,
            on_process=self.on_process,
            on_auto_calibrate=self.on_auto_calibrate,
            on_configure_offsets=self.on_configure_offsets,
            on_export_gmt=self.on_export_gmt,
            on_export_data=self.on_export_csv,
            width=360
        )
        self.ctrl_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 6))
        
        # Center Tabs
        self.notebook = ttk.Notebook(content)
        self.notebook.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Tab 1: Current Velocity Profiles
        tab_vel = ttk.Frame(self.notebook)
        self.notebook.add(tab_vel, text=" 🌊 Current Velocities (2D) ")
        
        sub_tb1 = ttk.Frame(tab_vel, padding=6)
        sub_tb1.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(sub_tb1, text="Variable:").pack(side=tk.LEFT, padx=(5, 5))
        
        self.var_vel_label = tk.StringVar(value="Absolute Current Speed (m/s)")
        cb_vel = ttk.Combobox(sub_tb1, textvariable=self.var_vel_label, values=list(VEL_OPTIONS.keys()), width=32, state="readonly")
        cb_vel.pack(side=tk.LEFT, padx=5)
        cb_vel.bind("<<ComboboxSelected>>", lambda e: self._update_vel_plot())
        
        self.view_vel = ProfileViewWidget(tab_vel)
        self.view_vel.pack(fill=tk.BOTH, expand=True)
        
        # Tab 2: Backscatter (Sv)
        tab_bs = ttk.Frame(self.notebook)
        self.notebook.add(tab_bs, text=" 📡 Backscatter & Echo (Sv) ")
        
        sub_tb2 = ttk.Frame(tab_bs, padding=6)
        sub_tb2.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(sub_tb2, text="Display:").pack(side=tk.LEFT, padx=(5, 5))
        
        self.var_bs_label = tk.StringVar(value="Volume Backscattering Strength Sv (dB)")
        cb_bs = ttk.Combobox(sub_tb2, textvariable=self.var_bs_label, values=list(BS_OPTIONS.keys()), width=40, state="readonly")
        cb_bs.pack(side=tk.LEFT, padx=5)
        cb_bs.bind("<<ComboboxSelected>>", lambda e: self._update_bs_plot())
        
        self.view_bs = ProfileViewWidget(tab_bs)
        self.view_bs.pack(fill=tk.BOTH, expand=True)
        
        # Tab 3: Track Chart & GMT Map
        tab_map = ttk.Frame(self.notebook)
        self.notebook.add(tab_map, text=" 🗺 Cruise Track & Vectors (GMT) ")
        
        self.view_map = TrackMapWidget(tab_map)
        self.view_map.pack(fill=tk.BOTH, expand=True)
        
        # Tab 4: 1D Depth Profile Inspector
        tab_1d = ttk.Frame(self.notebook)
        self.notebook.add(tab_1d, text=" 📊 Depth Profile Inspector ")
        self._build_1d_tab(tab_1d)
        
        # Tab 5: QC & Survey Statistics
        tab_qc = ttk.Frame(self.notebook)
        self.notebook.add(tab_qc, text=" 📋 Survey QC & Statistics ")
        self._build_qc_tab(tab_qc)
        
        # Bottom Status Bar
        status_bar = ttk.Frame(self, padding=(8, 4))
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.lbl_status = tk.Label(status_bar, text="Ready", font=FONT_REGULAR, bg=THEME["bg_main"], fg=THEME["text_secondary"])
        self.lbl_status.pack(side=tk.LEFT)
        
        self.prog_bar = ttk.Progressbar(status_bar, mode="indeterminate", length=150)
        self.prog_bar.pack(side=tk.RIGHT, padx=5)

    def _build_1d_tab(self, parent):
        sub_tb = ttk.Frame(parent, padding=6)
        sub_tb.pack(side=tk.TOP, fill=tk.X)
        
        ttk.Label(sub_tb, text="Ensemble Index:").pack(side=tk.LEFT, padx=5)
        self.slider_ens = ttk.Scale(sub_tb, from_=0, to=100, orient=tk.HORIZONTAL, command=self._on_1d_slider_change)
        self.slider_ens.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        
        self.lbl_ens_info = ttk.Label(sub_tb, text="0 / 0 (Time: --:--:--)", width=28)
        self.lbl_ens_info.pack(side=tk.RIGHT, padx=5)
        
        self.fig_1d = ProfileViewWidget(parent)
        self.fig_1d.pack(fill=tk.BOTH, expand=True)

    def _build_qc_tab(self, parent):
        self.txt_qc = tk.Text(parent, bg=THEME["bg_card"], fg="#e2e8f0", font=FONT_CODE, insertbackground="white", relief=tk.FLAT, padx=12, pady=12)
        self.txt_qc.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        self.txt_qc.insert(tk.END, "=== Survey Statistics & QC Report ===\nNo dataset loaded yet.\n")

    def _update_status(self, msg: str):
        self.lbl_status.config(text=msg)
        self.update_idletasks()

    def on_configure_offsets(self):
        """Opens modal dialog to configure sensor lever-arm and attitude alignment offsets."""
        current_o = self.dataset.offsets if self.dataset is not None else self.current_offsets
        
        def on_apply_callback(new_offsets: SensorOffsets):
            self.current_offsets = new_offsets
            if self.dataset is not None:
                self.dataset.offsets = new_offsets
            self.ctrl_panel.update_offset_summary(new_offsets)
            self._update_status(
                f"Updated Offsets -> Lever-Arm: ({new_offsets.lever_arm_x_m:.2f}, {new_offsets.lever_arm_y_m:.2f}, {new_offsets.lever_arm_z_m:.2f})m, Heading Bias: {new_offsets.heading_offset_deg:+.2f}°"
            )
            # Trigger re-processing automatically
            if self.dataset is not None:
                self.on_process()
                
        SensorOffsetDialog(self, current_o, on_apply_callback)

    def on_open_file(self, format_hint: str = "ALL"):
        if self._is_processing:
            return
            
        filetypes = [
            ("All Supported ADCP Files (*.pd0, *.enr, *.sta, *.lta, *.SigVM, *.AD2CP)", "*.pd0;*.enr;*.sta;*.lta;*.rdi;*.SigVM;*.AD2CP"),
            ("Teledyne RDI PD0 (*.pd0, *.enr, *.sta, *.lta, *.rdi)", "*.pd0;*.enr;*.sta;*.lta;*.rdi"),
            ("Nortek Signature VM (*.SigVM, *.AD2CP)", "*.SigVM;*.AD2CP"),
            ("All Files (*.*)", "*.*")
        ]
        
        filepath = filedialog.askopenfilename(
            title="Select VM-ADCP Data File (RDI PD0 / Nortek SigVM)",
            filetypes=filetypes,
            initialdir=os.path.abspath(r"01_VM-ADCP\Nortek\VM Acquisition")
        )
        if not filepath:
            return
            
        self.current_filepath = filepath
        self._load_file_async(filepath)

    def on_merge_pd0_files(self):
        """Merges multiple sequential PD0 files into a single unified PD0 file (pyadps-cat)."""
        files = filedialog.askopenfilenames(
            title="Select Sequential PD0 Files to Merge",
            filetypes=[("Teledyne RDI PD0 (*.pd0, *.enr, *.sta)", "*.pd0;*.enr;*.sta;*.lta;*.rdi"), ("All Files (*.*)", "*.*")]
        )
        if not files or len(files) < 2:
            if files and len(files) == 1:
                messagebox.showinfo("Merge PD0", "Please select 2 or more files to concatenate.", parent=self)
            return
            
        out_file = filedialog.asksaveasfilename(
            title="Save Merged PD0 File As",
            defaultextension=".pd0",
            filetypes=[("Teledyne RDI PD0 (*.pd0)", "*.pd0"), ("All Files (*.*)", "*.*")]
        )
        if not out_file:
            return
            
        from vmadcp.io.rdi_reader import concatenate_pd0_files
        try:
            total_ens = concatenate_pd0_files(list(files), out_file)
            ans = messagebox.askyesno(
                "Merge Complete",
                f"Successfully concatenated {len(files)} files into:\n{os.path.basename(out_file)}\n\n"
                f"Total ensembles detected: ~{total_ens:,}\n\nDo you want to open the merged file now?",
                parent=self
            )
            if ans:
                self.current_filepath = out_file
                self._load_file_async(out_file)
        except Exception as e:
            messagebox.showerror("Merge Error", f"Failed to merge PD0 files:\n{str(e)}", parent=self)

    def _load_file_async(self, filepath: str):
        self._is_processing = True
        self._update_status(f"Loading {os.path.basename(filepath)}...")
        self.prog_bar.start(10)
        
        def task():
            try:
                ds = load_adcp_dataset(filepath)
                
                # Apply current offsets
                ds.offsets = self.current_offsets
                
                # Default run pipeline
                pipeline = ProcessingPipeline(offsets=self.current_offsets)
                ds_proc = pipeline.process(ds)
                
                self.after(0, lambda: self._on_file_loaded(ds_proc, filepath))
            except Exception as e:
                traceback.print_exc()
                self.after(0, lambda: self._on_load_error(str(e)))
                
        threading.Thread(target=task, daemon=True).start()

    def _on_file_loaded(self, ds: VMADCPDataset, filepath: str):
        self.prog_bar.stop()
        self._is_processing = False
        self.dataset = ds
        filename = os.path.basename(filepath)
        coord_sys = getattr(ds, 'coord_sys', 'BEAM')
        self.lbl_file_info.config(text=f"Loaded: {filename} [{coord_sys}] ({ds.num_ensembles:,} ensembles, {ds.num_cells} cells)")
        self._update_status(f"Loaded {filename} [{coord_sys}] successfully ({ds.num_ensembles:,} ensembles).")
        
        # Configure slider
        self.slider_ens.configure(from_=0, to=ds.num_ensembles - 1)
        self.slider_ens.set(0)
        
        self.ctrl_panel.update_offset_summary(ds.offsets)
        
        # Render visualizations
        self._update_all_views()
        self._generate_qc_report()

    def _on_load_error(self, err_msg: str):
        self.prog_bar.stop()
        self._is_processing = False
        self._update_status("Error loading file.")
        messagebox.showerror("Loading Error", f"Failed to load ADCP data:\n{err_msg}")

    def on_process(self):
        if self._is_processing:
            return
        if self.dataset is None:
            messagebox.showwarning("Warning", "Please load an ADCP dataset first.")
            return
            
        self._is_processing = True
        self._update_status("Processing ADCP data with current parameters...")
        self.prog_bar.start(10)
        params = self.ctrl_panel.get_pipeline_params()
        params['offsets'] = self.current_offsets
        
        def task():
            try:
                pipeline = ProcessingPipeline(**params)
                ds_proc = pipeline.process(self.dataset)
                self.after(0, lambda: self._on_process_complete(ds_proc))
            except Exception as e:
                traceback.print_exc()
                self.after(0, lambda: self._on_load_error(str(e)))
                
        threading.Thread(target=task, daemon=True).start()

    def _on_process_complete(self, ds: VMADCPDataset):
        self.prog_bar.stop()
        self._is_processing = False
        self.dataset = ds
        self._update_status("Post-processing complete and views updated.")
        self._update_all_views()
        self._generate_qc_report()

    def on_auto_calibrate(self):
        if self.dataset is None:
            messagebox.showwarning("Warning", "Please load an ADCP dataset first.")
            return
            
        ds = self.dataset
        phi, A, info = estimate_bt_calibration(ds.ship_vel_east, ds.ship_vel_north, ds.bt_vel_east, ds.bt_vel_north)
        
        self.ctrl_panel.set_calibration_results(phi, A)
        msg = (
            f"Auto-Calibration Result:\n\n"
            f"Status: {info.get('status')}\n"
            f"Transducer Misalignment Angle (φ): {phi:.3f}°\n"
            f"Amplitude Scale Factor (A): {A:.4f}\n"
            f"Matched Data Points: {info.get('points')}\n\n"
            f"Parameters updated in the control panel. Click 'Run Post-Processing' to apply."
        )
        messagebox.showinfo("Bottom-Track Calibration", msg)

    def on_export_gmt(self):
        if self.dataset is None:
            messagebox.showwarning("Warning", "Please load and process a dataset first.")
            return
            
        out_dir = filedialog.askdirectory(title="Select GMT Output Folder", initialdir="c:\\ADCP")
        if not out_dir:
            return
            
        try:
            gmt_params = self.ctrl_panel.get_gmt_params()
            exporter = GMTExporter(self.dataset)
            files = exporter.export(
                out_dir,
                depth_layer_min_m=gmt_params['depth_min_m'],
                depth_layer_max_m=gmt_params['depth_max_m'],
                decimate_step=gmt_params['decimate_step'],
                vector_scale_cm_per_m_s=gmt_params['vector_scale']
            )
            msg = (
                f"GMT Track Chart script and files exported successfully!\n\n"
                f"Folder: {out_dir}\n\n"
                f"Generated Files:\n"
                f"• {os.path.basename(files['track'])}\n"
                f"• {os.path.basename(files['vectors'])}\n"
                f"• {os.path.basename(files['bathymetry'])}\n"
                f"• {os.path.basename(files['backscatter'])}\n"
                f"• Windows Script: {os.path.basename(files['bat_script'])}\n"
                f"• Linux/macOS Script: {os.path.basename(files['sh_script'])}\n\n"
                f"You can double-click 'plot_track_chart.bat' to render with GMT."
            )
            messagebox.showinfo("GMT Export Complete", msg)
        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("Export Error", f"Failed to export GMT files:\n{e}")

    def on_export_csv(self):
        if self.dataset is None:
            messagebox.showwarning("Warning", "Please load a dataset first.")
            return
        filepath = filedialog.asksaveasfilename(
            title="Save CSV Summary",
            defaultextension=".csv",
            filetypes=[("CSV File (*.csv)", "*.csv")]
        )
        if not filepath:
            return
        try:
            exporter = DataExporter(self.dataset)
            exporter.export_csv_summary(filepath)
            messagebox.showinfo("Export Complete", f"CSV summary exported to:\n{filepath}")
        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("Export Error", f"Failed to export CSV:\n{e}")

    def on_export_netcdf(self):
        if self.dataset is None:
            messagebox.showwarning("Warning", "Please load a dataset first.")
            return
        filepath = filedialog.asksaveasfilename(
            title="Save Dataset HDF5/NetCDF",
            defaultextension=".h5",
            filetypes=[("HDF5 / NetCDF (*.h5 *.nc)", "*.h5 *.nc")]
        )
        if not filepath:
            return
        try:
            exporter = DataExporter(self.dataset)
            exporter.export_hdf5_netcdf(filepath)
            messagebox.showinfo("Export Complete", f"Dataset exported to:\n{filepath}")
        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("Export Error", f"Failed to export NetCDF:\n{e}")

    def _update_all_views(self):
        self._update_vel_plot()
        self._update_bs_plot()
        self._update_map_plot()
        self._update_1d_plot()

    def _update_vel_plot(self):
        var_key = VEL_OPTIONS.get(self.var_vel_label.get(), "current_speed")
        self.view_vel.plot_profile(self.dataset, var_key)

    def _update_bs_plot(self):
        var_key = BS_OPTIONS.get(self.var_bs_label.get(), "volume_backscatter_sv")
        self.view_bs.plot_profile(self.dataset, var_key)

    def _update_map_plot(self):
        gmt_p = self.ctrl_panel.get_gmt_params()
        self.view_map.plot_track(
            self.dataset,
            depth_min_m=gmt_p['depth_min_m'],
            depth_max_m=gmt_p['depth_max_m'],
            decimate_step=gmt_p['decimate_step'],
            vector_scale=gmt_p['vector_scale']
        )

    def _on_1d_slider_change(self, val):
        self._update_1d_plot()

    def _update_1d_plot(self):
        if self.dataset is None or self.dataset.num_ensembles == 0:
            return
        idx = int(float(self.slider_ens.get()))
        idx = max(0, min(idx, self.dataset.num_ensembles - 1))
        
        ds = self.dataset
        t_epoch = ds.times[idx]
        dt = datetime.datetime.fromtimestamp(t_epoch, datetime.timezone.utc)
        self.lbl_ens_info.config(text=f"{idx+1} / {ds.num_ensembles:,} ({dt.strftime('%H:%M:%S')})")
        
        # Plot 1D slice
        self.fig_1d.figure.clear()
        ax = self.fig_1d.figure.add_subplot(111)
        self.fig_1d._style_axis(ax)
        self.fig_1d.ax = ax
        self.fig_1d.colorbar = None
        
        if ds.u_abs is None or ds.u_abs.size == 0 or ds.u_abs.ndim < 2:
            ax.text(0.5, 0.5, "Data Not Processed Yet", color='#94a3b8', ha='center', va='center', transform=ax.transAxes)
            self.fig_1d.canvas.draw()
            return
            
        draft = ds.offsets.transducer_draft_m if ds.offsets.enable_draft_offset else 0.0
        depths = ds.depth_bins + draft
        u = ds.u_abs[idx]
        v = ds.v_abs[idx]
        spd = ds.current_speed[idx]
        
        ax.plot(spd, depths, 'o-', color='#38bdf8', label='Current Speed (m/s)', linewidth=1.8, markersize=3)
        ax.plot(u, depths, 's--', color='#10b981', label='East Vel U (m/s)', linewidth=1.2, markersize=2)
        ax.plot(v, depths, 'd--', color='#f59e0b', label='North Vel V (m/s)', linewidth=1.2, markersize=2)
        
        if not np.isnan(ds.bt_depth[idx]):
            eff_bt = ds.bt_depth[idx] + draft
            ax.axhline(eff_bt, color='#ef4444', linestyle='-', linewidth=2.0, label=f'Seabed ({eff_bt:.1f}m)')
            th_rad = np.radians(ds.beam_angle_deg)
            ax.axhline(eff_bt*np.cos(th_rad)-0.5, color='#fbbf24', linestyle='--', label='Sidelobe Mask')
            
        ax.set_ylim(max(depths)*1.05, 0)
        ax.set_xlabel("Velocity (m/s)", fontsize=9)
        ax.set_ylabel("Depth (m) [Draft Corrected]", fontsize=9)
        ax.set_title(f"Ensemble {idx+1:,} Profile: UTC {dt.strftime('%Y-%m-%d %H:%M:%S')}", fontsize=10, fontweight='bold')
        ax.legend(loc='lower left', facecolor='#262b3d', edgecolor='#3b4256', labelcolor='#ffffff', fontsize=8)
        self.fig_1d.canvas.draw()

    def _generate_qc_report(self):
        if self.dataset is None:
            return
        ds = self.dataset
        o = ds.offsets
        
        total_cells = ds.mask_valid.size
        valid_cells = int(ds.mask_valid.sum())
        sl_masked = int((~ds.mask_sidelobe).sum()) if hasattr(ds, 'mask_sidelobe') and ds.mask_sidelobe is not None else 0
        cor_masked = int((~ds.mask_correlation).sum()) if hasattr(ds, 'mask_correlation') and ds.mask_correlation is not None else 0
        err_masked = int((~ds.mask_error_vel).sum()) if hasattr(ds, 'mask_error_vel') and ds.mask_error_vel is not None else 0
        tilt_masked = int((~ds.mask_tilt).sum()) if hasattr(ds, 'mask_tilt') and ds.mask_tilt is not None else 0
        bounds_masked = int((~ds.mask_vel_bounds).sum()) if hasattr(ds, 'mask_vel_bounds') and ds.mask_vel_bounds is not None else 0
        
        pg_str = f"{float(np.nanmean(ds.percent_good)):.1f}%" if (hasattr(ds, 'percent_good') and ds.percent_good is not None and ds.percent_good.size > 0) else "N/A"
        
        ship_spd = np.sqrt(ds.ship_vel_east**2 + ds.ship_vel_north**2)
        mean_ship_spd = float(np.nanmean(ship_spd))
        
        valid_d = ds.bt_depth[~np.isnan(ds.bt_depth)]
        mean_depth = float(np.mean(valid_d)) if len(valid_d) > 0 else 0.0
        
        dt_start = datetime.datetime.fromtimestamp(ds.times[0], datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        dt_end = datetime.datetime.fromtimestamp(ds.times[-1], datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        
        report = f"""========================================================================
VM-ADCP POST-PROCESSING QUALITY CONTROL REPORT
========================================================================
Instrument:              {ds.instrument_name} ({ds.frequency_khz:.1f} kHz)
Coordinate System:       {getattr(ds, 'coord_sys', 'BEAM')} (Orientation: {getattr(ds, 'orientation', 'down').upper()})
Ensembles Recorded:      {ds.num_ensembles:,}
Depth Cells (Bins):      {ds.num_cells} (Cell size: {ds.cell_size_m:.2f} m, Blanking: {ds.blanking_distance_m:.2f} m)
Survey Time Span:        {dt_start}  -->  {dt_end} UTC
Vessel Speed (Mean):     {mean_ship_spd:.2f} m/s ({mean_ship_spd*1.94384:.2f} knots)

SENSOR LEVER-ARM & ALIGNMENT OFFSETS
------------------------------------------------------------------------
GNSS to ADCP Lever-Arm:  X(Fore) = {o.lever_arm_x_m:+.2f} m, Y(Stbd) = {o.lever_arm_y_m:+.2f} m, Z(Down) = {o.lever_arm_z_m:+.2f} m
Transducer Draft:        {o.transducer_draft_m:.2f} m
Heading / Yaw Offset:    {o.heading_offset_deg:+.3f}° (Mag Declination: {getattr(o, 'magnetic_declination_deg', 0.0):+.3f}°)
Pitch / Roll Offsets:    Pitch: {o.pitch_offset_deg:+.3f}°, Roll: {o.roll_offset_deg:+.3f}°
Lever-Arm Velocity Corr: {'Enabled (v = ω × L)' if o.enable_lever_arm_vel else 'Disabled'}
Lever-Arm Position Corr: {'Enabled (Lat/Lon at ADCP)' if o.enable_lever_arm_pos else 'Disabled'}

NAVIGATION & BOTTOM TRACKING
------------------------------------------------------------------------
Coverage Bounding Box:   Lat [{ds.lat.min():.5f}°N ~ {ds.lat.max():.5f}°N]
                         Lon [{ds.lon.min():.5f}°E ~ {ds.lon.max():.5f}°E]
Seabed Depth Range:      {np.nanmin(ds.bt_depth):.2f} m ~ {np.nanmax(ds.bt_depth):.2f} m (Mean: {mean_depth:.2f} m)
Bottom-Track Lock:       {ds.bt_valid.sum():,} / {ds.num_ensembles:,} ensembles ({100*ds.bt_valid.mean():.1f}%)

CALIBRATION & MOTION CORRECTION
------------------------------------------------------------------------
Transducer Misalignment: {ds.misalignment_angle_deg:.3f}°
Amplitude Scale Factor:  {ds.amplitude_scale_factor:.4f}
Attitude Sensors:        Heading (AHRS/Dual-GNSS), Pitch, Roll, Heave

DATA QUALITY CONTROL (QC) MASKS (pyadps multi-step framework)
------------------------------------------------------------------------
Total Water-Track Cells: {total_cells:,}
Valid Accepted Cells:    {valid_cells:,} ({100*valid_cells/total_cells:.1f}%)
Sensor Health Tilt Mask: {tilt_masked:,} cells rejected (Vessel tilt > limit)
Sidelobe Boundary Mask:  {sl_masked:,} cells rejected ({100*sl_masked/total_cells:.1f}%)
Correlation Threshold:   {cor_masked:,} cells rejected ({100*cor_masked/total_cells:.1f}%)
Error Velocity Outliers: {err_masked:,} cells rejected ({100*err_masked/total_cells:.1f}%)
Velocity Bounds Outliers:{bounds_masked:,} cells rejected (Physical speed bounds)
Percent Good (Mean):     {pg_str}

OCEAN CURRENT SUMMARY
------------------------------------------------------------------------
Mean Current Speed:      {np.nanmean(ds.current_speed):.3f} m/s
Max Current Speed:       {np.nanmax(ds.current_speed):.3f} m/s
Mean Backscatter (Sv):   {np.nanmean(ds.volume_backscatter_sv):.1f} dB
========================================================================
"""
        self.txt_qc.delete("1.0", tk.END)
        self.txt_qc.insert(tk.END, report)

    def _show_documentation(self):
        doc = (
            "VM-ADCP Processing Principles & Sensor Offsets:\n\n"
            "1. GNSS-to-ADCP Lever-Arm Offset (X, Y, Z):\n"
            "   When the vessel rotates at angular rate omega = [p, q, r] (roll, pitch, yaw rates),\n"
            "   the distance between GNSS antenna and ADCP transducer induces an artificial velocity:\n"
            "   v_lever = omega x L.\n"
            "   This is subtracted from GNSS velocity to get true speed at the ADCP transducer.\n\n"
            "2. Heading (Yaw) Offset & Gyro Bias:\n"
            "   Compensates for gyrocompass or dual-antenna GNSS heading mounting error:\n"
            "   Heading_true = (Heading_measured + Heading_offset) % 360.\n\n"
            "3. Transducer Draft:\n"
            "   Adds ADCP mounting depth below waterline to all depth cells.\n\n"
            "4. Transducer Misalignment Angle (phi) & Scale Factor (A):\n"
            "   Corrects physical transducer rotation relative to vessel fore-aft line.\n"
            "   Can be auto-calibrated via bottom tracking."
        )
        messagebox.showinfo("Processing Documentation", doc)

    def _show_about(self):
        msg = (
            "VM-ADCP Post-Processing Studio\n"
            "Vessel Mounted Acoustic Doppler Current Profiler Data Post-Processing System\n\n"
            "Features:\n"
            "• Sensor Lever-Arm Offset & Alignment Calibration (X, Y, Z, Draft, Heading Bias)\n"
            "• High-rate Motion & Attitude Correction\n"
            "• Bottom Tracking & Sidelobe Masking\n"
            "• Acoustic Backscatter & Sv Processing\n"
            "• Publication-ready GMT Track Chart Script & Table Generation\n"
            "• NetCDF & CSV Export"
        )
        messagebox.showinfo("About VM-ADCP Studio", msg)
