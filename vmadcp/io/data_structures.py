"""
ADCP Dataset structures for Vessel Mounted ADCP processing.
Includes Sensor Lever-Arm and Alignment Offset parameters.
"""
from dataclasses import dataclass, field
import numpy as np
from typing import Optional, Dict, Any, List

@dataclass
class SensorOffsets:
    """Sensor mounting lever-arm offsets and attitude alignment biases."""
    # GNSS Antenna to ADCP Transducer Lever-Arm (Vessel Coordinate: X=Fore, Y=Stbd, Z=Down)
    lever_arm_x_m: float = 0.0     # Fore (+) / Aft (-) in meters
    lever_arm_y_m: float = 0.0     # Starboard (+) / Port (-) in meters
    lever_arm_z_m: float = 0.0     # Down (+) / Up (-) in meters
    transducer_draft_m: float = 0.0 # Transducer depth below waterline in meters
    
    # Attitude Alignment Biases (Offsets)
    heading_offset_deg: float = 0.0 # Heading/Yaw offset in degrees
    magnetic_declination_deg: float = 0.0 # Magnetic Declination (True North = Mag North + Declination)
    pitch_offset_deg: float = 0.0   # Pitch offset in degrees
    roll_offset_deg: float = 0.0    # Roll offset in degrees
    
    # Toggle flags
    enable_lever_arm_vel: bool = True
    enable_lever_arm_pos: bool = True
    enable_draft_offset: bool = True

@dataclass
class VMADCPDataset:
    """Complete Vessel Mounted ADCP dataset including raw and processed data."""
    # Metadata
    instrument_name: str = "Nortek Signature500"
    frequency_khz: float = 500.0
    beam_angle_deg: float = 25.0
    num_beams: int = 4
    num_cells: int = 139
    cell_size_m: float = 0.5
    blanking_distance_m: float = 0.5
    coord_sys: str = "BEAM"               # 'BEAM', 'INST', 'SHIP', or 'EARTH'
    orientation: str = "down"             # 'down' (downward-looking) or 'up' (upward-looking)
    is_convex: bool = True                # Convex vs Concave beam geometry
    
    # Sensor Lever-arm and Alignment Offsets
    offsets: SensorOffsets = field(default_factory=SensorOffsets)
    
    # Coordinates & Bins
    depth_bins: np.ndarray = field(default_factory=lambda: np.array([]))  # shape: (num_cells,)
    times: np.ndarray = field(default_factory=lambda: np.array([]))       # timestamps (epoch seconds)
    
    # Raw GNSS/INS Navigation (before lever-arm correction)
    raw_lat: np.ndarray = field(default_factory=lambda: np.array([]))
    raw_lon: np.ndarray = field(default_factory=lambda: np.array([]))
    raw_ship_ve: np.ndarray = field(default_factory=lambda: np.array([]))
    raw_ship_vn: np.ndarray = field(default_factory=lambda: np.array([]))
    raw_heading: np.ndarray = field(default_factory=lambda: np.array([]))
    raw_pitch: np.ndarray = field(default_factory=lambda: np.array([]))
    raw_roll: np.ndarray = field(default_factory=lambda: np.array([]))
    
    # Corrected Navigation / Motion at ADCP Transducer (shape: N)
    lat: np.ndarray = field(default_factory=lambda: np.array([]))
    lon: np.ndarray = field(default_factory=lambda: np.array([]))
    ship_vel_east: np.ndarray = field(default_factory=lambda: np.array([]))  # m/s
    ship_vel_north: np.ndarray = field(default_factory=lambda: np.array([])) # m/s
    ship_heading: np.ndarray = field(default_factory=lambda: np.array([]))   # deg
    ship_pitch: np.ndarray = field(default_factory=lambda: np.array([]))     # deg
    ship_roll: np.ndarray = field(default_factory=lambda: np.array([]))      # deg
    ship_heave: np.ndarray = field(default_factory=lambda: np.array([]))     # m
    
    # Environmental sensors (shape: N)
    sound_speed: np.ndarray = field(default_factory=lambda: np.array([]))    # m/s
    temperature: np.ndarray = field(default_factory=lambda: np.array([]))    # degC
    pressure: np.ndarray = field(default_factory=lambda: np.array([]))       # dbar
    
    # Raw ADCP Profile Data (shape: N, num_cells, num_beams)
    raw_beam_vel: np.ndarray = field(default_factory=lambda: np.array([]))   # m/s
    raw_amplitude: np.ndarray = field(default_factory=lambda: np.array([]))  # counts or dB
    raw_correlation: np.ndarray = field(default_factory=lambda: np.array([]))# 0..100
    raw_percent_good: np.ndarray = field(default_factory=lambda: np.array([]))# 0..100 (N, num_cells, 4)
    percent_good: np.ndarray = field(default_factory=lambda: np.array([]))    # 0..100 (N, num_cells)
    
    # Instrument to System Transform Matrix
    transform_matrix: np.ndarray = field(default_factory=lambda: np.eye(4))
    
    # Bottom Track Data (shape: N)
    bt_range_beam: np.ndarray = field(default_factory=lambda: np.array([]))  # shape: (N, 4) in meters
    bt_depth: np.ndarray = field(default_factory=lambda: np.array([]))       # mean vertical depth (m)
    bt_vel_east: np.ndarray = field(default_factory=lambda: np.array([]))    # m/s
    bt_vel_north: np.ndarray = field(default_factory=lambda: np.array([]))   # m/s
    bt_valid: np.ndarray = field(default_factory=lambda: np.array([]))       # boolean mask
    
    # Processed Water Velocities (shape: N, num_cells)
    u_rel: np.ndarray = field(default_factory=lambda: np.array([]))          # Relative East vel (m/s)
    v_rel: np.ndarray = field(default_factory=lambda: np.array([]))          # Relative North vel (m/s)
    w_rel: np.ndarray = field(default_factory=lambda: np.array([]))          # Relative Up vel (m/s)
    err_vel: np.ndarray = field(default_factory=lambda: np.array([]))        # Error vel (m/s)
    
    u_abs: np.ndarray = field(default_factory=lambda: np.array([]))          # True/Absolute East vel (m/s)
    v_abs: np.ndarray = field(default_factory=lambda: np.array([]))          # True/Absolute North vel (m/s)
    w_abs: np.ndarray = field(default_factory=lambda: np.array([]))          # True Up vel (m/s)
    current_speed: np.ndarray = field(default_factory=lambda: np.array([]))  # sqrt(u^2 + v^2) (m/s)
    current_direction: np.ndarray = field(default_factory=lambda: np.array([])) # oceanographic dir (deg)
    
    # Processed Acoustic Backscatter (shape: N, num_cells)
    volume_backscatter_sv: np.ndarray = field(default_factory=lambda: np.array([])) # Sv in dB
    echo_intensity_mean: np.ndarray = field(default_factory=lambda: np.array([]))   # beam average dB
    
    # Quality Flags / Masks (shape: N, num_cells) - True = Valid, False = Masked/Rejected
    mask_valid: np.ndarray = field(default_factory=lambda: np.array([]))
    mask_sidelobe: np.ndarray = field(default_factory=lambda: np.array([]))
    mask_correlation: np.ndarray = field(default_factory=lambda: np.array([]))
    mask_error_vel: np.ndarray = field(default_factory=lambda: np.array([]))

    # Calibration parameters used
    misalignment_angle_deg: float = 0.0
    amplitude_scale_factor: float = 1.0
    sound_absorption_db_per_m: float = 0.139
    
    @property
    def num_ensembles(self) -> int:
        return len(self.times)
