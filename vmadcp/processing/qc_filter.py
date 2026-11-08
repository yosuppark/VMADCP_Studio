"""
Quality Control (QC) and filtering module for ADCP data.
"""
import numpy as np
from scipy.ndimage import median_filter
from typing import Tuple, Dict, Any

def apply_correlation_filter(correlation: np.ndarray, min_correlation_pct: float = 50.0) -> np.ndarray:
    """
    Flags cells with low acoustic correlation.
    correlation: shape (N, num_cells, num_beams) or (N, num_cells)
    Returns: mask: shape (N, num_cells), True = valid, False = low correlation
    """
    if correlation is None or correlation.size == 0:
        return np.array([])
    if correlation.ndim == 3:
        # Require all or mean beams above threshold
        mean_cor = np.nanmean(correlation, axis=2)
    else:
        mean_cor = correlation
    return (mean_cor >= min_correlation_pct)

def apply_percent_good_filter(percent_good: np.ndarray, min_pg_pct: float = 25.0) -> np.ndarray:
    """
    Flags cells with insufficient percent good pings (Teledyne RDI PD0 block 0x0400).
    percent_good: shape (N, num_cells, 4) or (N, num_cells)
    For Earth coordinates: field 4 is 4-beam good %, field 1 is 3-beam good %.
    Returns: mask: shape (N, num_cells), True = valid, False = insufficient good pings
    """
    if percent_good is None or percent_good.size == 0:
        return np.array([])
    if percent_good.ndim == 3:
        # If 4 columns, sum of 3-beam (col 0) and 4-beam (col 3) solutions for Earth coord,
        # or mean of 4 beams for Beam coord
        if percent_good.shape[2] == 4:
            good_pct = percent_good[:, :, 0] + percent_good[:, :, 3]
            # Clip at 100%
            good_pct = np.clip(good_pct, 0.0, 100.0)
        else:
            good_pct = np.nanmean(percent_good, axis=2)
    else:
        good_pct = percent_good
    return (good_pct >= min_pg_pct) | np.isnan(good_pct)

def apply_error_velocity_filter(err_vel: np.ndarray, max_err_vel_m_s: float = 0.25) -> np.ndarray:
    """
    Flags cells with excessive error velocity.
    err_vel: shape (N, num_cells)
    Returns: mask: shape (N, num_cells), True = valid, False = excessive error
    """
    return (np.abs(err_vel) <= max_err_vel_m_s) | np.isnan(err_vel)

def apply_sensor_health_filter(pitch_deg: np.ndarray, roll_deg: np.ndarray, 
                                max_tilt_deg: float = 15.0) -> np.ndarray:
    """
    Evaluates internal motion sensor health (pyadps apply_sensor_health).
    Flags ensembles where vessel tilt exceeds acceptable limits for ADCP beam geometry.
    Total tilt angle = arccos(cos(pitch) * cos(roll))
    Returns: mask: shape (N,), True = healthy attitude, False = excessive tilt
    """
    if len(pitch_deg) == 0 or len(roll_deg) == 0:
        return np.array([], dtype=bool)
    p_rad = np.radians(pitch_deg)
    r_rad = np.radians(roll_deg)
    # Cosine of total tilt from vertical
    cos_tilt = np.clip(np.cos(p_rad) * np.cos(r_rad), -1.0, 1.0)
    tilt_deg = np.degrees(np.arccos(cos_tilt))
    return (tilt_deg <= max_tilt_deg) & (~np.isnan(tilt_deg))

def apply_velocity_cutoff_filter(u: np.ndarray, v: np.ndarray, w: np.ndarray,
                                 max_horizontal_spd_m_s: float = 3.0,
                                 max_vertical_spd_m_s: float = 0.8) -> np.ndarray:
    """
    Screens unphysical velocity outliers (pyadps apply_velocity_check).
    Flags bins where horizontal current speed or vertical velocity exceeds oceanographic thresholds.
    Returns: mask: shape (N, num_cells), True = valid, False = out of physical bounds
    """
    horiz_spd_sq = u**2 + v**2
    vert_spd = np.abs(w)
    
    mask_h = (horiz_spd_sq <= (max_horizontal_spd_m_s**2)) | np.isnan(horiz_spd_sq)
    mask_w = (vert_spd <= max_vertical_spd_m_s) | np.isnan(vert_spd)
    return mask_h & mask_w

def apply_echo_threshold_filter(amplitude: np.ndarray, min_echo_counts: float = 20.0) -> np.ndarray:
    """
    Screens bins with insufficient echo intensity (pyadps apply_signal_quality).
    amplitude: shape (N, num_cells, num_beams) or (N, num_cells)
    Returns: mask: shape (N, num_cells), True = valid signal, False = weak return / noise
    """
    if amplitude is None or amplitude.size == 0:
        return np.array([], dtype=bool)
    if amplitude.ndim == 3:
        mean_amp = np.nanmean(amplitude, axis=2)
    else:
        mean_amp = amplitude
    return (mean_amp >= min_echo_counts) | np.isnan(mean_amp)

def apply_ship_speed_filter(ship_speed_m_s: np.ndarray, 
                            min_speed: float = 0.2, 
                            max_speed: float = 12.0) -> np.ndarray:
    """
    Flags ensembles where ship speed is out of nominal surveying range
    (e.g., vessel stopped, drifting, or cruising too fast).
    Returns: mask: shape (N,), True = valid
    """
    return (ship_speed_m_s >= min_speed) & (ship_speed_m_s <= max_speed)

def apply_median_despike_filter(data_2d: np.ndarray, 
                                kernel_size: Tuple[int, int] = (5, 3),
                                max_deviation: float = 0.5) -> np.ndarray:
    """
    Detects and removes 2D spikes in time-depth velocity arrays using a median filter.
    data_2d: shape (N, num_cells)
    Returns: cleaned_data: shape (N, num_cells) with outliers replaced by NaN
    """
    # Replace NaNs with local mean for filtering
    nan_mask = np.isnan(data_2d)
    if np.all(nan_mask):
        return data_2d
        
    filled = data_2d.copy()
    valid_mean = np.nanmean(data_2d)
    filled[nan_mask] = valid_mean
    
    med = median_filter(filled, size=kernel_size)
    diff = np.abs(data_2d - med)
    
    cleaned = data_2d.copy()
    cleaned[diff > max_deviation] = np.nan
    return cleaned
