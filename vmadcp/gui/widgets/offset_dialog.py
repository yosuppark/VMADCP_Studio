"""
Sensor Lever-Arm & Attitude Alignment Offset configuration dialog.
Allows precise setting of GNSS antenna to ADCP transducer lever-arm (X, Y, Z, Draft)
and Attitude Biases (Heading, Pitch, Roll offsets) with preset management.
"""
import os
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Callable, Optional

from ...io.data_structures import SensorOffsets
from ..styles import THEME, FONT_HEADER, FONT_REGULAR, FONT_BOLD

def safe_float(val: str, default: float = 0.0) -> float:
    try:
        return float(str(val).strip())
    except (ValueError, TypeError):
        return default

class SensorOffsetDialog(tk.Toplevel):
    """Modal dialog for configuring sensor lever-arm and attitude alignment offsets."""
    
    def __init__(self, parent, current_offsets: SensorOffsets, on_apply_callback: Callable[[SensorOffsets], None]):
        super().__init__(parent)
        
        self.title("Sensor Lever-Arm & Heading Offset Settings")
        self.geometry("540x620")
        self.minsize(480, 560)
        self.configure(bg=THEME["bg_main"])
        self.transient(parent)
        self.grab_set()
        
        self.offsets = current_offsets
        self.on_apply_callback = on_apply_callback
        
        self._build_ui()
        self._load_current_values()
        
    def _create_entry(self, parent, text_var: tk.StringVar, width: int = 10) -> tk.Entry:
        return tk.Entry(
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
        
    def _build_ui(self):
        # Header banner
        header = tk.Frame(self, bg=THEME["bg_panel"], padx=14, pady=10)
        header.pack(fill=tk.X)
        
        lbl_title = tk.Label(
            header, 
            text="📐 Sensor Lever-Arm & Alignment Calibration", 
            font=FONT_HEADER, 
            bg=THEME["bg_panel"], 
            fg=THEME["text_accent"]
        )
        lbl_title.pack(anchor="w")
        
        lbl_desc = tk.Label(
            header,
            text="Configure GNSS antenna to ADCP transducer offset and heading/gyro alignment biases.",
            font=FONT_REGULAR,
            bg=THEME["bg_panel"],
            fg=THEME["text_secondary"]
        )
        lbl_desc.pack(anchor="w", pady=(2, 0))
        
        # Main form container
        body = ttk.Frame(self, padding=12)
        body.pack(fill=tk.BOTH, expand=True)
        
        # --- Section 1: GNSS Antenna to ADCP Lever-Arm ---
        f_la = ttk.LabelFrame(body, text="  1. GNSS Antenna to ADCP Lever-Arm (Vessel Frame)  ", padding=10)
        f_la.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(f_la, text="Forward / Aft (X, meters):\n[Fore +, Aft -]").grid(row=0, column=0, sticky="w", pady=4)
        self.var_lx = tk.StringVar(value="0.00")
        self._create_entry(f_la, self.var_lx).grid(row=0, column=1, sticky="e", pady=4, padx=8)
        
        ttk.Label(f_la, text="Starboard / Port (Y, meters):\n[Starboard +, Port -]").grid(row=1, column=0, sticky="w", pady=4)
        self.var_ly = tk.StringVar(value="0.00")
        self._create_entry(f_la, self.var_ly).grid(row=1, column=1, sticky="e", pady=4, padx=8)
        
        ttk.Label(f_la, text="Vertical Offset (Z, meters):\n[Down +, Up -]").grid(row=2, column=0, sticky="w", pady=4)
        self.var_lz = tk.StringVar(value="0.00")
        self._create_entry(f_la, self.var_lz).grid(row=2, column=1, sticky="e", pady=4, padx=8)
        
        ttk.Label(f_la, text="Transducer Draft (meters):\n[Depth below waterline]").grid(row=3, column=0, sticky="w", pady=4)
        self.var_draft = tk.StringVar(value="0.00")
        self._create_entry(f_la, self.var_draft).grid(row=3, column=1, sticky="e", pady=4, padx=8)
        
        # --- Section 2: Attitude & Heading Alignment Biases ---
        f_att = ttk.LabelFrame(body, text="  2. Heading & Attitude Alignment Offsets  ", padding=10)
        f_att.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(f_att, text="Heading / Compass Offset (°):\n[Yaw bias: True = Meas + Offset]").grid(row=0, column=0, sticky="w", pady=4)
        self.var_hdg_off = tk.StringVar(value="0.000")
        self._create_entry(f_att, self.var_hdg_off).grid(row=0, column=1, sticky="e", pady=4, padx=8)
        
        ttk.Label(f_att, text="Magnetic Declination (°):\n[pyadps: True = Mag + Declination]").grid(row=1, column=0, sticky="w", pady=4)
        self.var_mag_dec = tk.StringVar(value="0.000")
        self._create_entry(f_att, self.var_mag_dec).grid(row=1, column=1, sticky="e", pady=4, padx=8)
        
        ttk.Label(f_att, text="Pitch Offset (°):\n[Bow Up +, Bow Down -]").grid(row=2, column=0, sticky="w", pady=4)
        self.var_pitch_off = tk.StringVar(value="0.000")
        self._create_entry(f_att, self.var_pitch_off).grid(row=2, column=1, sticky="e", pady=4, padx=8)
        
        ttk.Label(f_att, text="Roll Offset (°):\n[Port Up +, Stbd Up -]").grid(row=3, column=0, sticky="w", pady=4)
        self.var_roll_off = tk.StringVar(value="0.000")
        self._create_entry(f_att, self.var_roll_off).grid(row=3, column=1, sticky="e", pady=4, padx=8)
        
        # --- Section 3: Feature Toggles ---
        f_tog = ttk.LabelFrame(body, text="  3. Correction Options  ", padding=10)
        f_tog.pack(fill=tk.X, pady=(0, 10))
        
        self.var_tog_vel = tk.BooleanVar(value=True)
        ttk.Checkbutton(f_tog, text="Enable Lever-Arm Velocity Correction (v = ω × L)", variable=self.var_tog_vel).pack(anchor="w", pady=2)
        
        self.var_tog_pos = tk.BooleanVar(value=True)
        ttk.Checkbutton(f_tog, text="Enable Horizontal Position Offset (Lat / Lon at ADCP)", variable=self.var_tog_pos).pack(anchor="w", pady=2)
        
        self.var_tog_draft = tk.BooleanVar(value=True)
        ttk.Checkbutton(f_tog, text="Apply Transducer Draft to Depth Profile", variable=self.var_tog_draft).pack(anchor="w", pady=2)
        
        # --- Preset Management & Action Buttons ---
        btn_bar = tk.Frame(self, bg=THEME["bg_panel"], padx=12, pady=10)
        btn_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        btn_load = tk.Button(
            btn_bar, text="📁 Load Preset...",
            bg="#475569", fg="white", activebackground="#334155", font=FONT_REGULAR,
            relief=tk.RAISED, cursor="hand2", padx=10, pady=3,
            command=self._on_load_preset
        )
        btn_load.pack(side=tk.LEFT, padx=(0, 6))
        
        btn_save = tk.Button(
            btn_bar, text="💾 Save Preset...",
            bg="#475569", fg="white", activebackground="#334155", font=FONT_REGULAR,
            relief=tk.RAISED, cursor="hand2", padx=10, pady=3,
            command=self._on_save_preset
        )
        btn_save.pack(side=tk.LEFT, padx=(0, 6))
        
        btn_cancel = tk.Button(
            btn_bar, text="Cancel",
            bg="#262b3d", fg="#e2e8f0", activebackground="#1e222d", font=FONT_REGULAR,
            relief=tk.FLAT, cursor="hand2", padx=12, pady=3,
            command=self.destroy
        )
        btn_cancel.pack(side=tk.RIGHT, padx=(6, 0))
        
        btn_apply = tk.Button(
            btn_bar, text="✔ Apply & Reprocess",
            bg="#059669", fg="white", activebackground="#047857", font=FONT_HEADER,
            relief=tk.RAISED, cursor="hand2", padx=14, pady=4,
            command=self._on_apply
        )
        btn_apply.pack(side=tk.RIGHT)

    def _load_current_values(self):
        o = self.offsets
        self.var_lx.set(f"{o.lever_arm_x_m:.2f}")
        self.var_ly.set(f"{o.lever_arm_y_m:.2f}")
        self.var_lz.set(f"{o.lever_arm_z_m:.2f}")
        self.var_draft.set(f"{o.transducer_draft_m:.2f}")
        
        self.var_hdg_off.set(f"{o.heading_offset_deg:.3f}")
        self.var_mag_dec.set(f"{getattr(o, 'magnetic_declination_deg', 0.0):.3f}")
        self.var_pitch_off.set(f"{o.pitch_offset_deg:.3f}")
        self.var_roll_off.set(f"{o.roll_offset_deg:.3f}")
        
        self.var_tog_vel.set(o.enable_lever_arm_vel)
        self.var_tog_pos.set(o.enable_lever_arm_pos)
        self.var_tog_draft.set(o.enable_draft_offset)

    def _get_offsets_from_ui(self) -> SensorOffsets:
        return SensorOffsets(
            lever_arm_x_m=safe_float(self.var_lx.get(), 0.0),
            lever_arm_y_m=safe_float(self.var_ly.get(), 0.0),
            lever_arm_z_m=safe_float(self.var_lz.get(), 0.0),
            transducer_draft_m=safe_float(self.var_draft.get(), 0.0),
            heading_offset_deg=safe_float(self.var_hdg_off.get(), 0.0),
            magnetic_declination_deg=safe_float(self.var_mag_dec.get(), 0.0),
            pitch_offset_deg=safe_float(self.var_pitch_off.get(), 0.0),
            roll_offset_deg=safe_float(self.var_roll_off.get(), 0.0),
            enable_lever_arm_vel=self.var_tog_vel.get(),
            enable_lever_arm_pos=self.var_tog_pos.get(),
            enable_draft_offset=self.var_tog_draft.get(),
        )

    def _on_apply(self):
        updated_offsets = self._get_offsets_from_ui()
        self.on_apply_callback(updated_offsets)
        self.destroy()

    def _on_save_preset(self):
        filepath = filedialog.asksaveasfilename(
            parent=self,
            title="Save Sensor Offset Preset",
            defaultextension=".json",
            filetypes=[("JSON Preset (*.json)", "*.json")]
        )
        if not filepath:
            return
            
        o = self._get_offsets_from_ui()
        data = {
            "lever_arm_x_m": o.lever_arm_x_m,
            "lever_arm_y_m": o.lever_arm_y_m,
            "lever_arm_z_m": o.lever_arm_z_m,
            "transducer_draft_m": o.transducer_draft_m,
            "heading_offset_deg": o.heading_offset_deg,
            "magnetic_declination_deg": o.magnetic_declination_deg,
            "pitch_offset_deg": o.pitch_offset_deg,
            "roll_offset_deg": o.roll_offset_deg,
            "enable_lever_arm_vel": o.enable_lever_arm_vel,
            "enable_lever_arm_pos": o.enable_lever_arm_pos,
            "enable_draft_offset": o.enable_draft_offset,
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        messagebox.showinfo("Preset Saved", f"Preset saved to:\n{os.path.basename(filepath)}", parent=self)

    def _on_load_preset(self):
        filepath = filedialog.askopenfilename(
            parent=self,
            title="Load Sensor Offset Preset",
            filetypes=[("JSON Preset (*.json)", "*.json"), ("All Files (*.*)", "*.*")]
        )
        if not filepath:
            return
            
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.var_lx.set(f"{data.get('lever_arm_x_m', 0.0):.2f}")
            self.var_ly.set(f"{data.get('lever_arm_y_m', 0.0):.2f}")
            self.var_lz.set(f"{data.get('lever_arm_z_m', 0.0):.2f}")
            self.var_draft.set(f"{data.get('transducer_draft_m', 0.0):.2f}")
            self.var_hdg_off.set(f"{data.get('heading_offset_deg', 0.0):.3f}")
            self.var_mag_dec.set(f"{data.get('magnetic_declination_deg', 0.0):.3f}")
            self.var_pitch_off.set(f"{data.get('pitch_offset_deg', 0.0):.3f}")
            self.var_roll_off.set(f"{data.get('roll_offset_deg', 0.0):.3f}")
            self.var_ly.set(f"{data.get('lever_arm_y_m', 0.0):.2f}")
            self.var_lz.set(f"{data.get('lever_arm_z_m', 0.0):.2f}")
            self.var_draft.set(f"{data.get('transducer_draft_m', 0.0):.2f}")
            self.var_hdg_off.set(f"{data.get('heading_offset_deg', 0.0):.3f}")
            self.var_pitch_off.set(f"{data.get('pitch_offset_deg', 0.0):.3f}")
            self.var_roll_off.set(f"{data.get('roll_offset_deg', 0.0):.3f}")
            self.var_tog_vel.set(data.get('enable_lever_arm_vel', True))
            self.var_tog_pos.set(data.get('enable_lever_arm_pos', True))
            self.var_tog_draft.set(data.get('enable_draft_offset', True))
            messagebox.showinfo("Preset Loaded", f"Loaded preset from:\n{os.path.basename(filepath)}", parent=self)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load preset:\n{e}", parent=self)
