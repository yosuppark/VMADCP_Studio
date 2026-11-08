"""
Comprehensive VM-ADCP post-processing pipeline.
Coordinates:
1. Sensor Lever-Arm and Attitude Offset corrections
2. Coordinate transformations (Beam -> Inst XYZ -> Earth ENU)
3. Transducer misalignment & amplitude factor calibration
4. Bottom-track & GNSS vessel velocity removal
5. Sidelobe interference masking (D_bottom * cos(theta))
6. Backscatter conversion to Volume Backscattering Strength (Sv)
7. Multi-criteria Quality Control and outlier rejection
"""
import math
import numpy as np
from typing import Dict, Any, Optional

from ..io.data_structures import VMADCPDataset, SensorOffsets
from .motion import (
    beam_to_instrument, 
    transform_xyz_to_sfu,
    transform_sfu_to_enu,
    calibrate_misalignment, 
    compute_absolute_velocities,
    apply_sensor_offsets_and_leverarm
)
from .bottom_track import generate_sidelobe_mask, compute_vertical_depth
from .backscatter import compute_volume_backscatter
from .qc_filter import (
    apply_correlation_filter, 
    apply_error_velocity_filter, 
    apply_percent_good_filter,
    apply_sensor_health_filter,
    apply_velocity_cutoff_filter,
    apply_echo_threshold_filter,
    apply_median_despike_filter
)

class ProcessingPipeline:
    """Configurable processing engine for VMADCP datasets."""
    
    def __init__(self,
                 offsets: Optional[SensorOffsets] = None,
                 misalignment_deg: float = 0.0,
                 amplitude_scale: float = 1.0,
                 velocity_reference: str = "GNSS", # "GNSS" or "BottomTrack"
                 enable_sidelobe_mask: bool = True,
                 sidelobe_margin_m: float = 0.5,
                 min_correlation_pct: float = 50.0,
                 max_error_vel_m_s: float = 0.3,
                 min_percent_good_pct: float = 25.0,
                 max_tilt_deg: float = 15.0,
                 max_horizontal_spd_m_s: float = 3.5,
                 max_vertical_spd_m_s: float = 0.8,
                 min_echo_counts: float = 20.0,
                 enable_despike: bool = True,
                 temperature_c: float = 15.0,
                 salinity_psu: float = 34.5,
                 noise_floor_counts: float = 25.0):
        self.offsets = offsets if offsets is not None else SensorOffsets()
        self.misalignment_deg = misalignment_deg
        self.amplitude_scale = amplitude_scale
        self.velocity_reference = velocity_reference
        self.enable_sidelobe_mask = enable_sidelobe_mask
        self.sidelobe_margin_m = sidelobe_margin_m
        self.min_correlation_pct = min_correlation_pct
        self.max_error_vel_m_s = max_error_vel_m_s
        self.min_percent_good_pct = min_percent_good_pct
        self.max_tilt_deg = max_tilt_deg
        self.max_horizontal_spd_m_s = max_horizontal_spd_m_s
        self.max_vertical_spd_m_s = max_vertical_spd_m_s
        self.min_echo_counts = min_echo_counts
        self.enable_despike = enable_despike
        self.temperature_c = temperature_c
        self.salinity_psu = salinity_psu
        self.noise_floor_counts = noise_floor_counts
        
    def process(self, ds: VMADCPDataset) -> VMADCPDataset:
        """Executes the full post-processing sequence on the dataset."""
        N = ds.num_ensembles
        nc = ds.num_cells
        nb = ds.num_beams
        
        # 1. Apply Sensor Lever-Arm & Attitude Alignment Offsets
        ds.offsets = self.offsets
        if len(ds.raw_heading) == N and N > 0:
            lat, lon, s_ve, s_vn, s_hdg, s_pitch, s_roll = apply_sensor_offsets_and_leverarm(
                ds.times,
                ds.raw_lat, ds.raw_lon,
                ds.raw_ship_ve, ds.raw_ship_vn,
                ds.raw_heading, ds.raw_pitch, ds.raw_roll,
                self.offsets
            )
            ds.lat = lat
            ds.lon = lon
            ds.ship_vel_east = s_ve
            ds.ship_vel_north = s_vn
            ds.ship_heading = s_hdg
            ds.ship_pitch = s_pitch
            ds.ship_roll = s_roll
            
        # 2. Account for Transducer Draft (depth offset)
        draft = self.offsets.transducer_draft_m if self.offsets.enable_draft_offset else 0.0
        # Depth bins from water surface
        effective_depth_bins = ds.depth_bins + draft
        
        # 3. Coordinate Transformation (Pipeline Architecture based on smerckel/adcpreader)
        # Coordinate frames: BEAM -> INST (XYZ) -> SHIP (SFU) -> EARTH (ENU)
        coord_sys = getattr(ds, 'coord_sys', 'BEAM').upper()
        is_upward = (getattr(ds, 'orientation', 'down').lower() == 'up')
        
        if coord_sys == 'BEAM':
            # 3.1 Beam to Instrument (XYZ) with 3-beam solution capability
            inst_vel = beam_to_instrument(ds.raw_beam_vel, ds.transform_matrix, allow_3beam=True)
            # 3.2 Instrument to Ship (SFU) using physical mounting offsets
            sfu_vel = transform_xyz_to_sfu(
                inst_vel,
                pitch_offset_deg=self.offsets.pitch_offset_deg,
                roll_offset_deg=self.offsets.roll_offset_deg,
                yaw_offset_deg=0.0
            )
            # 3.3 Ship to Earth (ENU) using vessel attitude
            enu_vel = transform_sfu_to_enu(
                sfu_vel,
                heading_deg=ds.ship_heading,
                pitch_deg=ds.ship_pitch,
                roll_deg=ds.ship_roll,
                is_upward=is_upward
            )
            u_rel = enu_vel[..., 0]
            v_rel = enu_vel[..., 1]
            w_rel = enu_vel[..., 2]
            err_vel = enu_vel[..., 3]
            
        elif coord_sys == 'INST':
            inst_vel = ds.raw_beam_vel
            sfu_vel = transform_xyz_to_sfu(
                inst_vel,
                pitch_offset_deg=self.offsets.pitch_offset_deg,
                roll_offset_deg=self.offsets.roll_offset_deg,
                yaw_offset_deg=0.0
            )
            enu_vel = transform_sfu_to_enu(
                sfu_vel,
                heading_deg=ds.ship_heading,
                pitch_deg=ds.ship_pitch,
                roll_deg=ds.ship_roll,
                is_upward=is_upward
            )
            u_rel = enu_vel[..., 0]
            v_rel = enu_vel[..., 1]
            w_rel = enu_vel[..., 2]
            err_vel = enu_vel[..., 3]
            
        elif coord_sys == 'SHIP':
            sfu_vel = ds.raw_beam_vel
            enu_vel = transform_sfu_to_enu(
                sfu_vel,
                heading_deg=ds.ship_heading,
                pitch_deg=ds.ship_pitch,
                roll_deg=ds.ship_roll,
                is_upward=is_upward
            )
            u_rel = enu_vel[..., 0]
            v_rel = enu_vel[..., 1]
            w_rel = enu_vel[..., 2]
            err_vel = enu_vel[..., 3]
            
        else: # 'EARTH'
            # Data is already stored in Earth coordinates [East, North, Up, Error]
            u_rel = ds.raw_beam_vel[..., 0].copy()
            v_rel = ds.raw_beam_vel[..., 1].copy()
            w_rel = ds.raw_beam_vel[..., 2].copy()
            err_vel = ds.raw_beam_vel[..., 3].copy() if ds.raw_beam_vel.shape[-1] > 3 else np.zeros((N, nc))
        
        # 4. Apply Transducer Misalignment Angle and Amplitude Scaling
        u_rel_cal, v_rel_cal = calibrate_misalignment(u_rel, v_rel, self.misalignment_deg, self.amplitude_scale)
        
        # 5. Remove Vessel Speed (GNSS or Bottom-Track)
        if self.velocity_reference.upper() == "BOTTOMTRACK" and ds.bt_valid.sum() > 10:
            ship_ve = -ds.bt_vel_east
            ship_vn = -ds.bt_vel_north
        else:
            ship_ve = ds.ship_vel_east
            ship_vn = ds.ship_vel_north
            
        u_abs, v_abs, w_abs = compute_absolute_velocities(u_rel_cal, v_rel_cal, w_rel, 
                                                           ship_ve, ship_vn, ds.ship_heave)
        
        # 6. Process Acoustic Backscatter (Volume Backscattering Strength, Sv)
        temp_c = np.nanmean(ds.temperature) if len(ds.temperature) > 0 and not np.all(np.isnan(ds.temperature)) else self.temperature_c
        sv, mean_echo = compute_volume_backscatter(
            ds.raw_amplitude,
            effective_depth_bins,
            beam_angle_deg=ds.beam_angle_deg,
            frequency_khz=ds.frequency_khz,
            temperature_c=temp_c,
            salinity_psu=self.salinity_psu,
            noise_floor_counts=self.noise_floor_counts
        )
        
        # 7. Quality Control Filtering & Masks (pyadps multi-step QC framework)
        # 7.1 Sensor Health: Excessive vessel tilt (pitch/roll)
        mask_tilt = apply_sensor_health_filter(ds.ship_pitch, ds.ship_roll, self.max_tilt_deg)
        mask_tilt_2d = mask_tilt[:, np.newaxis] if len(mask_tilt) == N else np.ones((N, nc), dtype=bool)
        
        # 7.2 Signal Quality: Correlation, Error Velocity, Echo Intensity
        mask_cor = apply_correlation_filter(ds.raw_correlation, self.min_correlation_pct)
        mask_err = apply_error_velocity_filter(err_vel, self.max_error_vel_m_s)
        mask_echo = apply_echo_threshold_filter(ds.raw_amplitude, self.min_echo_counts)
        
        # Percent Good filter (smerckel/adcpreader & RDI PD0 0x0400)
        if hasattr(ds, 'percent_good') and ds.percent_good is not None and ds.percent_good.size > 0:
            mask_pg = apply_percent_good_filter(ds.percent_good, self.min_percent_good_pct)
        elif hasattr(ds, 'raw_percent_good') and ds.raw_percent_good is not None and ds.raw_percent_good.size > 0:
            mask_pg = apply_percent_good_filter(ds.raw_percent_good, self.min_percent_good_pct)
        else:
            mask_pg = np.ones((N, nc), dtype=bool)
            
        # 7.3 Sidelobe boundary cutoff
        if self.enable_sidelobe_mask:
            effective_bt_depth = ds.bt_depth + draft
            mask_sl = generate_sidelobe_mask(effective_depth_bins, effective_bt_depth, 
                                             beam_angle_deg=ds.beam_angle_deg, 
                                             safety_margin_m=self.sidelobe_margin_m)
        else:
            mask_sl = np.ones((N, nc), dtype=bool)
            
        # 7.4 Physical Velocity Bounds Check (pyadps apply_velocity_check)
        mask_vel_bounds = apply_velocity_cutoff_filter(u_abs, v_abs, w_abs,
                                                      self.max_horizontal_spd_m_s,
                                                      self.max_vertical_spd_m_s)
            
        combined_mask = mask_tilt_2d & mask_cor & mask_err & mask_echo & mask_pg & mask_sl & mask_vel_bounds
        
        # 8. Despike if enabled
        if self.enable_despike:
            u_abs = apply_median_despike_filter(u_abs)
            v_abs = apply_median_despike_filter(v_abs)
            
        # Apply combined mask to ocean velocities
        u_abs_masked = np.where(combined_mask, u_abs, np.nan)
        v_abs_masked = np.where(combined_mask, v_abs, np.nan)
        w_abs_masked = np.where(combined_mask, w_abs, np.nan)
        
        # Current speed and oceanographic direction
        current_spd = np.sqrt(u_abs_masked**2 + v_abs_masked**2)
        current_dir = (np.degrees(np.arctan2(u_abs_masked, v_abs_masked))) % 360.0
        
        # Store results in dataset
        ds.u_rel = u_rel_cal
        ds.v_rel = v_rel_cal
        ds.w_rel = w_rel
        ds.err_vel = err_vel
        ds.u_abs = u_abs_masked
        ds.v_abs = v_abs_masked
        ds.w_abs = w_abs_masked
        ds.current_speed = current_spd
        ds.current_direction = current_dir
        ds.volume_backscatter_sv = np.where(mask_sl, sv, np.nan)
        ds.echo_intensity_mean = mean_echo
        
        ds.mask_valid = combined_mask
        ds.mask_tilt = mask_tilt_2d
        ds.mask_sidelobe = mask_sl
        ds.mask_correlation = mask_cor
        ds.mask_error_vel = mask_err
        ds.mask_echo = mask_echo
        ds.mask_vel_bounds = mask_vel_bounds
        
        ds.misalignment_angle_deg = self.misalignment_deg
        ds.amplitude_scale_factor = self.amplitude_scale
        
        return ds
