"""
Acoustic backscatter processing module.
Calculates seawater acoustic absorption coefficient (Ainslie & McColm, 1998),
Spherical spreading transmission loss (20 log10 R),
and Volume Backscattering Strength (Sv, dB) from ADCP Echo Intensity/RSSI.
"""
import math
import numpy as np
from typing import Tuple, Optional, Union

def ainslie_mccolm_absorption(frequency_khz: float, 
                              temperature_c: float = 15.0, 
                              salinity_psu: float = 35.0, 
                              depth_m: float = 20.0, 
                              ph: float = 8.0) -> float:
    """
    Calculates acoustic absorption coefficient in seawater (dB/m)
    using the Ainslie and McColm (1998) simplified formula.
    
    Formula yields dB/km, which is then converted to dB/m.
    frequency_khz: acoustic frequency in kHz (e.g., 500 for Signature 500)
    temperature_c: temperature in deg C
    salinity_psu: salinity in PSU (default: 35.0)
    depth_m: water depth in meters
    ph: seawater pH (default: 8.0)
    Returns: alpha in dB/m
    """
    f = frequency_khz
    T = temperature_c
    S = salinity_psu
    D = depth_m / 1000.0  # depth in km
    
    # Relaxation frequency for Boric acid (f1, kHz)
    f1 = 0.78 * math.sqrt(S / 35.0) * math.exp(T / 26.0)
    
    # Relaxation frequency for Magnesium sulfate (f2, kHz)
    f2 = 42.0 * math.exp(T / 17.0)
    
    # Boric acid contribution
    A1 = 0.106 * (f1 * f**2) / (f**2 + f1**2) * math.exp((ph - 8.0) / 0.56)
    
    # Magnesium sulfate contribution
    A2 = 0.52 * (1.0 + T / 43.0) * (S / 35.0) * (f2 * f**2) / (f**2 + f2**2) * math.exp(-D / 6.0)
    
    # Pure water viscosity contribution
    A3 = 0.00049 * f**2 * math.exp(-(T / 27.0 + D / 17.0))
    
    # Total absorption in dB/km
    alpha_db_km = A1 + A2 + A3
    
    # Return in dB/m
    return alpha_db_km / 1000.0

def compute_volume_backscatter(raw_amplitude: np.ndarray,
                               depth_bins: np.ndarray,
                               beam_angle_deg: float = 25.0,
                               frequency_khz: float = 500.0,
                               temperature_c: float = 15.0,
                               salinity_psu: float = 35.0,
                               noise_floor_counts: float = 30.0,
                               kc_db_per_count: float = 0.45,
                               c_calibration_offset_db: float = -75.0) -> Tuple[np.ndarray, np.ndarray]:
    """
    Processes ADCP Echo Amplitude/Intensity into Volume Backscattering Strength (Sv, dB).
    
    Sv = C + 10*log10( (T+273.16)*R^2 ) + 2*alpha*R + Kc*(E - Er)
    
    raw_amplitude: shape (N, num_cells, num_beams) or (N, num_cells)
    depth_bins: shape (num_cells,) in meters
    Returns: (Sv, mean_echo_db) of shape (N, num_cells)
    """
    # Average amplitude across available beams
    if raw_amplitude.ndim == 3:
        amp_mean = np.nanmean(raw_amplitude, axis=2)
    else:
        amp_mean = raw_amplitude.copy()
        
    N, nc = amp_mean.shape
    th = math.radians(beam_angle_deg)
    cos_th = math.cos(th)
    
    # Slant range along beam: R = depth / cos(theta)
    slant_range_m = depth_bins / cos_th  # shape (nc,)
    slant_range_2d = slant_range_m[np.newaxis, :]  # shape (1, nc)
    
    # Compute absorption alpha (dB/m) for mean depth
    mean_depth = np.mean(depth_bins) if len(depth_bins) > 0 else 20.0
    alpha = ainslie_mccolm_absorption(frequency_khz, temperature_c, salinity_psu, mean_depth)
    
    # 1. Transmission Loss - Spherical spreading: 20 * log10(R)
    # (Avoid log of zero by clipping min range to 0.1m)
    r_safe = np.maximum(slant_range_2d, 0.1)
    tl_spreading = 20.0 * np.log10(r_safe)
    
    # 2. Transmission Loss - Two-way absorption: 2 * alpha * R
    tl_absorption = 2.0 * alpha * r_safe
    
    # 3. Received acoustic intensity above noise floor: Kc * (E - Er)
    signal_above_noise = np.maximum(amp_mean - noise_floor_counts, 0.1)
    rssi_db = kc_db_per_count * signal_above_noise
    
    # 4. Total Volume Backscattering Strength (Sv, dB)
    sv = c_calibration_offset_db + tl_spreading + tl_absorption + rssi_db
    
    # Mean calibrated echo intensity (dB)
    mean_echo_db = amp_mean * kc_db_per_count
    
    return sv, mean_echo_db
