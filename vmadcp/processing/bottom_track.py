"""
Bottom tracking and sidelobe interference removal module.
"""
import math
import numpy as np
from typing import Tuple, Optional, Dict, Any

def compute_vertical_depth(beam_ranges: np.ndarray, beam_angle_deg: float = 25.0) -> np.ndarray:
    """
    Computes mean vertical seabed depth from multi-beam slant ranges.
    beam_ranges: shape (N, 4) in meters
    Returns: vertical_depth: shape (N,) in meters
    """
    th = math.radians(beam_angle_deg)
    cos_th = math.cos(th)
    
    # Calculate vertical depth per beam
    vert_beams = beam_ranges * cos_th
    
    # Take mean of valid beams
    vert_depth = np.nanmean(vert_beams, axis=1)
    return vert_depth

def detect_bottom_from_echo(amplitude: np.ndarray, depth_bins: np.ndarray, 
                            threshold_db: float = 120.0) -> np.ndarray:
    """
    Detects bottom depth based on peak acoustic echo amplitude profile.
    amplitude: shape (N, num_cells, num_beams) or (N, num_cells)
    depth_bins: shape (num_cells,)
    Returns: detected_depth shape: (N,)
    """
    if amplitude.ndim == 3:
        mean_amp = np.nanmean(amplitude, axis=2) # average across beams
    else:
        mean_amp = amplitude
        
    N, nc = mean_amp.shape
    detected = np.full(N, np.nan)
    
    for i in range(N):
        prof = mean_amp[i]
        if np.all(np.isnan(prof)):
            continue
        max_idx = np.nanargmax(prof)
        max_val = prof[max_idx]
        if max_val >= threshold_db and max_idx > 3: # skip surface blanking
            detected[i] = depth_bins[max_idx]
            
    return detected

def generate_sidelobe_mask(depth_bins: np.ndarray, bottom_depth: np.ndarray,
                           beam_angle_deg: float = 25.0,
                           safety_margin_m: float = 0.5) -> np.ndarray:
    """
    Generates a boolean mask (True = valid, False = contaminated by sidelobe reflection).
    The critical cutoff depth is:
        D_cut = D_bottom * cos(beam_angle) - safety_margin
    Any cell whose center depth > D_cut is contaminated by strong acoustic sidelobe
    reflection from the seafloor.
    
    depth_bins: shape (num_cells,)
    bottom_depth: shape (N,)
    Returns: mask: shape (N, num_cells), dtype bool
    """
    N = len(bottom_depth)
    nc = len(depth_bins)
    
    th = math.radians(beam_angle_deg)
    cos_th = math.cos(th)
    
    # Calculate cutoff depth for each ensemble
    cutoff_depth = bottom_depth * cos_th - safety_margin_m
    
    # Broadcast comparison: depth_bins shape (1, nc) vs cutoff_depth shape (N, 1)
    # Valid where depth_bins <= cutoff_depth OR where bottom_depth is NaN (deep water)
    bins_2d = depth_bins[np.newaxis, :] # (1, nc)
    cutoff_2d = cutoff_depth[:, np.newaxis] # (N, 1)
    
    mask = (bins_2d <= cutoff_2d) | np.isnan(cutoff_2d)
    return mask

def filter_bottom_track_velocities(bt_ve: np.ndarray, bt_vn: np.ndarray,
                                  max_speed_m_s: float = 12.0,
                                  max_acceleration_m_s2: float = 2.0,
                                  dt_s: float = 1.0) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Quality control for bottom-track velocities: removes spikes and unrealistic accelerations.
    Returns: (cleaned_bt_ve, cleaned_bt_vn, valid_mask)
    """
    N = len(bt_ve)
    valid = (~np.isnan(bt_ve)) & (~np.isnan(bt_vn))
    
    speed = np.sqrt(bt_ve**2 + bt_vn**2)
    valid &= (speed <= max_speed_m_s)
    
    # Acceleration check
    acc = np.zeros(N)
    valid_idx = np.where(valid)[0]
    if len(valid_idx) > 1:
        d_spd = np.abs(np.diff(speed[valid_idx]))
        acc[valid_idx[1:]] = d_spd / dt_s
        valid[valid_idx[1:][acc[valid_idx[1:]] > max_acceleration_m_s2]] = False
        
    cleaned_ve = np.where(valid, bt_ve, np.nan)
    cleaned_vn = np.where(valid, bt_vn, np.nan)
    return cleaned_ve, cleaned_vn, valid
