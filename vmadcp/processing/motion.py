"""
Motion correction module for Vessel Mounted ADCP.
Handles coordinate transformations (Beam -> Inst -> Earth ENU),
Attitude rotations (Roll, Pitch, Heading),
Sensor Lever-Arm and Alignment Offset corrections,
Transducer misalignment angle and amplitude scaling,
and Ship velocity removal (GNSS or Bottom-Track).
"""
import math
import numpy as np
from typing import Tuple, Dict, Any, Optional

from ..io.data_structures import SensorOffsets

def apply_sensor_offsets_and_leverarm(
    times: np.ndarray,
    raw_lat: np.ndarray,
    raw_lon: np.ndarray,
    raw_ve: np.ndarray,
    raw_vn: np.ndarray,
    raw_heading: np.ndarray,
    raw_pitch: np.ndarray,
    raw_roll: np.ndarray,
    offsets: SensorOffsets
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Applies attitude alignment biases and GNSS-to-ADCP lever-arm offsets.
    
    1. Attitude Offsets:
       heading = (raw_heading + heading_offset) % 360
       pitch   = raw_pitch + pitch_offset
       roll    = raw_roll + roll_offset
       
    2. Lever-Arm Velocity Correction:
       v_lever_ship = omega x L
       v_lever_enu = R * v_lever_ship
       ship_ve_adcp = ship_ve_gnss + v_lever_east
       ship_vn_adcp = ship_vn_gnss + v_lever_north
       
    3. Lever-Arm Horizontal Position Offset:
       lat_adcp = lat_gnss + dNorth / R_earth
       lon_adcp = lon_gnss + dEast / (R_earth * cos(lat))
       
    Returns:
       (lat, lon, ship_ve, ship_vn, heading, pitch, roll)
    """
    N = len(times)
    if N == 0:
        return raw_lat, raw_lon, raw_ve, raw_vn, raw_heading, raw_pitch, raw_roll

    # 1. Apply Attitude Alignment Biases & Magnetic Declination (True North = Mag North + Declination)
    total_hdg_bias = offsets.heading_offset_deg + getattr(offsets, 'magnetic_declination_deg', 0.0)
    heading = (raw_heading + total_hdg_bias) % 360.0
    pitch = raw_pitch + offsets.pitch_offset_deg
    roll = raw_roll + offsets.roll_offset_deg
    
    lat = raw_lat.copy()
    lon = raw_lon.copy()
    ship_ve = raw_ve.copy()
    ship_vn = raw_vn.copy()
    
    Lx = offsets.lever_arm_x_m  # Fore (+) / Aft (-)
    Ly = offsets.lever_arm_y_m  # Stbd (+) / Port (-)
    Lz = offsets.lever_arm_z_m  # Down (+) / Up (-)
    
    # Check if lever-arm is effectively non-zero
    has_lever_arm = (abs(Lx) > 1e-4 or abs(Ly) > 1e-4 or abs(Lz) > 1e-4)
    
    # 2. Lever-Arm Horizontal Position Offset
    if offsets.enable_lever_arm_pos and has_lever_arm:
        hdg_rad = np.radians(heading)
        # Ship frame to geographic displacement:
        # X is forward (heading direction), Y is starboard (heading + 90 deg)
        # dNorth = Lx * cos(hdg) - Ly * sin(hdg)
        # dEast  = Lx * sin(hdg) + Ly * cos(hdg)
        dNorth = Lx * np.cos(hdg_rad) - Ly * np.sin(hdg_rad)
        dEast  = Lx * np.sin(hdg_rad) + Ly * np.cos(hdg_rad)
        
        # WGS84 approximate earth radius in meters
        R_earth = 6378137.0
        dLat_deg = np.degrees(dNorth / R_earth)
        dLon_deg = np.degrees(dEast / (R_earth * np.cos(np.radians(raw_lat))))
        
        lat = raw_lat + dLat_deg
        lon = raw_lon + dLon_deg

    # 3. Lever-Arm Velocity Correction (v = omega x L)
    if offsets.enable_lever_arm_vel and has_lever_arm and N > 2:
        # Check monotonic timestamps
        t_diff = np.diff(times)
        if np.all(t_diff > 0):
            t_axis = times
        else:
            t_axis = np.arange(N, dtype=float)
            
        # Calculate angular rates (rad/s) via gradient along time axis
        hdg_unwrapped_rad = np.unwrap(np.radians(heading))
        r_rate = np.gradient(hdg_unwrapped_rad, t_axis) # yaw rate (rad/s)
        
        pitch_rad = np.radians(pitch)
        q_rate = np.gradient(pitch_rad, t_axis)         # pitch rate (rad/s)
        
        roll_rad = np.radians(roll)
        p_rate = np.gradient(roll_rad, t_axis)          # roll rate (rad/s)
        
        # Lever-arm cross product: v_ship = omega x L
        # omega = [p, q, r], L = [Lx, Ly, Lz]
        # vx = q * Lz - r * Ly
        # vy = r * Lx - p * Lz
        # vz = p * Ly - q * Lx
        vx_lever = q_rate * Lz - r_rate * Ly
        vy_lever = r_rate * Lx - p_rate * Lz
        
        # Rotate horizontal ship lever-arm velocity into Earth ENU frame:
        # East velocity component from ship frame:
        cos_h = np.cos(hdg_rad)
        sin_h = np.sin(hdg_rad)
        v_lever_east  = vx_lever * sin_h + vy_lever * cos_h
        v_lever_north = vx_lever * cos_h - vy_lever * sin_h
        
        # Add to GNSS vessel speed
        ship_ve = raw_ve + v_lever_east
        ship_vn = raw_vn + v_lever_north
        
    return lat, lon, ship_ve, ship_vn, heading, pitch, roll

def euler_rotation_matrix(heading_deg: float, pitch_deg: float, roll_deg: float) -> np.ndarray:
    """
    Constructs the 3D rotation matrix from Instrument frame to Earth ENU frame.
    Uses standard oceanographic convention:
    - Heading (yaw): clockwise from North
    - Pitch: bow up positive
    - Roll: port up / starboard down positive
    """
    psi = math.radians(heading_deg)
    theta = math.radians(pitch_deg)
    phi = math.radians(roll_deg)
    
    ch = math.cos(psi)
    sh = math.sin(psi)
    cp = math.cos(theta)
    sp = math.sin(theta)
    cr = math.cos(phi)
    sr = math.sin(phi)
    
    # Direct rotation matrix to East, North, Up
    R = np.array([
        [ ch*cr + sh*sp*sr,  sh*cp,  ch*sr - sh*sp*cr],
        [-sh*cr + ch*sp*sr,  ch*cp, -sh*sr - ch*sp*cr],
        [-cp*sr,             sp,     cp*cr]
    ])
    return R

def compute_rdi_transform_matrix(beam_angle_deg: float = 20.0, is_convex: bool = True) -> np.ndarray:
    """
    Calculates standard Teledyne RDI Janus 4-beam transformation matrix:
    [u_inst, v_inst, w_inst, err_vel]^T = T * [b1, b2, b3, b4]^T
    where:
    c = 1 / (2 * sin(theta))
    d = 1 / (4 * cos(theta))
    """
    th = math.radians(beam_angle_deg)
    c = 1.0 / (2.0 * math.sin(th))
    d = 1.0 / (4.0 * math.cos(th))
    if not is_convex:
        c = -c
        
    return np.array([
        [ c, -c,  0,  0],   # u: starboard (+) / port (-)
        [ 0,  0, -c,  c],   # v: forward (+) / aft (-)
        [ d,  d,  d,  d],   # w: up (+)
        [ d,  d, -d, -d]    # err: error velocity
    ])

def beam_to_instrument(beam_vel: np.ndarray, transform_matrix: np.ndarray, allow_3beam: bool = True) -> np.ndarray:
    """
    Converts 4-beam radial velocities to Instrument XYZ velocities:
    u_inst, v_inst, w_inst, err_vel.
    Supports 3-beam solution when exactly 1 beam is bad (NaN),
    matching Teledyne RDI firmware and smerckel/adcpreader behavior.
    
    beam_vel shape: (..., 4)
    transform_matrix shape: (4, 4)
    Returns: inst_vel shape: (..., 4)
    """
    orig_shape = beam_vel.shape
    flat_beam = beam_vel.reshape(-1, 4).copy()
    N_pts = flat_beam.shape[0]
    flat_inst = np.full((N_pts, 4), np.nan, dtype=float)
    
    isnan = np.isnan(flat_beam)
    num_nan = np.sum(isnan, axis=1)
    
    # 1. 4-beam valid: standard matrix multiplication
    mask_4b = (num_nan == 0)
    if np.any(mask_4b):
        flat_inst[mask_4b] = np.dot(flat_beam[mask_4b], transform_matrix.T)
        
    # 2. 3-beam solution: exactly 1 beam missing, assume error vel = 0 (b1 + b2 = b3 + b4)
    if allow_3beam:
        mask_3b = (num_nan == 1)
        if np.any(mask_3b):
            b = flat_beam[mask_3b]
            nan_b = isnan[mask_3b]
            
            # Reconstruct missing beam assuming b1 + b2 == b3 + b4
            # Beam 1 missing:
            idx1 = nan_b[:, 0]
            if np.any(idx1):
                b[idx1, 0] = b[idx1, 2] + b[idx1, 3] - b[idx1, 1]
            # Beam 2 missing:
            idx2 = nan_b[:, 1]
            if np.any(idx2):
                b[idx2, 1] = b[idx2, 2] + b[idx2, 3] - b[idx2, 0]
            # Beam 3 missing:
            idx3 = nan_b[:, 2]
            if np.any(idx3):
                b[idx3, 2] = b[idx3, 0] + b[idx3, 1] - b[idx3, 3]
            # Beam 4 missing:
            idx4 = nan_b[:, 3]
            if np.any(idx4):
                b[idx4, 3] = b[idx4, 0] + b[idx4, 1] - b[idx4, 2]
                
            res_3b = np.dot(b, transform_matrix.T)
            res_3b[:, 3] = np.nan # Error velocity is undefined for 3-beam solution
            flat_inst[mask_3b] = res_3b
            
    return flat_inst.reshape(orig_shape)

def transform_xyz_to_sfu(xyz_vel: np.ndarray,
                         pitch_offset_deg: float = 0.0,
                         roll_offset_deg: float = 0.0,
                         yaw_offset_deg: float = 0.0) -> np.ndarray:
    """
    Transforms velocities from Instrument frame (XYZ) to Ship/Platform frame (SFU: Starboard, Forward, Up).
    Accounts for physical mounting angles of the ADCP on the vessel hull.
    """
    if abs(pitch_offset_deg) < 1e-5 and abs(roll_offset_deg) < 1e-5 and abs(yaw_offset_deg) < 1e-5:
        return xyz_vel.copy()
        
    R = euler_rotation_matrix(yaw_offset_deg, pitch_offset_deg, roll_offset_deg)
    orig_shape = xyz_vel.shape
    flat = xyz_vel.reshape(-1, 4)
    u_xyz = flat[:, :3]
    valid = ~np.isnan(u_xyz).any(axis=1)
    
    flat_sfu = flat.copy()
    if np.any(valid):
        flat_sfu[valid, :3] = np.dot(u_xyz[valid], R.T)
        
    return flat_sfu.reshape(orig_shape)

def transform_sfu_to_enu(sfu_vel: np.ndarray,
                         heading_deg: np.ndarray,
                         pitch_deg: np.ndarray,
                         roll_deg: np.ndarray,
                         is_upward: bool = False) -> np.ndarray:
    """
    Transforms velocities from Ship/Platform frame (SFU) to Earth ENU frame
    using time-varying vessel heading, pitch, and roll.
    sfu_vel: shape (N, nc, 4) or (N, 4)
    Returns: enu_vel: shape (N, nc, 4) or (N, 4) [East, North, Up, Err]
    """
    N = len(heading_deg)
    orig_shape = sfu_vel.shape
    if sfu_vel.ndim == 3:
        nc = sfu_vel.shape[1]
        enu_vel = np.full_like(sfu_vel, np.nan)
        for i in range(N):
            hdg = heading_deg[i]
            pit = pitch_deg[i]
            rol = roll_deg[i]
            if np.isnan(hdg) or np.isnan(pit) or np.isnan(rol):
                continue
            if is_upward:
                pit = -pit
                rol = -rol
            R = euler_rotation_matrix(hdg, pit, rol)
            
            pts = sfu_vel[i, :, :3]
            v_mask = ~np.isnan(pts).any(axis=1)
            if np.any(v_mask):
                enu_vel[i, v_mask, :3] = np.dot(pts[v_mask], R.T)
            enu_vel[i, :, 3] = sfu_vel[i, :, 3] # Keep error velocity unchanged
        return enu_vel
    else:
        enu_vel = np.full_like(sfu_vel, np.nan)
        for i in range(N):
            hdg = heading_deg[i]
            pit = pitch_deg[i]
            rol = roll_deg[i]
            if np.isnan(hdg) or np.isnan(pit) or np.isnan(rol):
                continue
            R = euler_rotation_matrix(hdg, pit, rol)
            pt = sfu_vel[i, :3]
            if not np.isnan(pt).any():
                enu_vel[i, :3] = np.dot(pt, R.T)
            enu_vel[i, 3] = sfu_vel[i, 3]
        return enu_vel

def transform_enu_to_sfu(enu_vel: np.ndarray,
                         heading_deg: np.ndarray,
                         pitch_deg: np.ndarray,
                         roll_deg: np.ndarray,
                         is_upward: bool = False) -> np.ndarray:
    """
    Inverse transformation from Earth ENU back to Ship/Platform frame (SFU).
    Allows recalculating velocities when attitude or mounting calibrations are adjusted.
    """
    N = len(heading_deg)
    if enu_vel.ndim == 3:
        sfu_vel = np.full_like(enu_vel, np.nan)
        for i in range(N):
            hdg = heading_deg[i]
            pit = pitch_deg[i]
            rol = roll_deg[i]
            if np.isnan(hdg) or np.isnan(pit) or np.isnan(rol):
                continue
            if is_upward:
                pit = -pit
                rol = -rol
            R = euler_rotation_matrix(hdg, pit, rol)
            pts = enu_vel[i, :, :3]
            v_mask = ~np.isnan(pts).any(axis=1)
            if np.any(v_mask):
                # R is orthogonal, so inverse is R.T: v_sfu = dot(v_enu, R)
                sfu_vel[i, v_mask, :3] = np.dot(pts[v_mask], R)
            sfu_vel[i, :, 3] = enu_vel[i, :, 3]
        return sfu_vel
    else:
        sfu_vel = np.full_like(enu_vel, np.nan)
        for i in range(N):
            hdg = heading_deg[i]
            pit = pitch_deg[i]
            rol = roll_deg[i]
            if np.isnan(hdg) or np.isnan(pit) or np.isnan(rol):
                continue
            R = euler_rotation_matrix(hdg, pit, rol)
            pt = enu_vel[i, :3]
            if not np.isnan(pt).any():
                sfu_vel[i, :3] = np.dot(pt, R)
            sfu_vel[i, 3] = enu_vel[i, 3]
        return sfu_vel

def calibrate_misalignment(u: np.ndarray, v: np.ndarray, 
                           phi_deg: float, amplitude_factor: float) -> Tuple[np.ndarray, np.ndarray]:
    """
    Applies transducer misalignment angle (phi) and amplitude scaling factor (A)
    to horizontal velocities:
    [u_cal, v_cal]^T = A * [cos(phi) -sin(phi); sin(phi) cos(phi)] * [u, v]^T
    """
    phi_rad = math.radians(phi_deg)
    cos_phi = math.cos(phi_rad)
    sin_phi = math.sin(phi_rad)
    
    u_cal = amplitude_factor * (u * cos_phi - v * sin_phi)
    v_cal = amplitude_factor * (u * sin_phi + v * cos_phi)
    return u_cal, v_cal

def estimate_bt_calibration(ship_ve: np.ndarray, ship_vn: np.ndarray,
                            bt_ve: np.ndarray, bt_vn: np.ndarray,
                            min_speed_m_s: float = 1.0) -> Tuple[float, float, Dict[str, Any]]:
    """
    Estimates transducer misalignment angle (phi in deg) and amplitude factor (A)
    using Bottom Track velocity vs GPS velocity (Least Squares complex regression).
    """
    ship_spd = np.sqrt(ship_ve**2 + ship_vn**2)
    mask = (~np.isnan(ship_ve)) & (~np.isnan(ship_vn)) & \
           (~np.isnan(bt_ve)) & (~np.isnan(bt_vn)) & \
           (ship_spd >= min_speed_m_s)
           
    if np.sum(mask) < 20:
        return 0.0, 1.0, {'status': 'Insufficient valid data (<20 points)', 'points': int(np.sum(mask))}
        
    v_gps = ship_ve[mask] + 1j * ship_vn[mask]
    v_bt = -(bt_ve[mask] + 1j * bt_vn[mask])
    
    numerator = np.sum(v_gps * np.conj(v_bt))
    denominator = np.sum(np.abs(v_bt)**2)
    
    if denominator == 0:
        return 0.0, 1.0, {'status': 'Zero denominator', 'points': 0}
        
    z = numerator / denominator
    A = float(np.abs(z))
    phi_deg = float(math.degrees(np.angle(z)))
    
    corr = float(np.abs(numerator) / (np.sqrt(np.sum(np.abs(v_gps)**2)) * np.sqrt(denominator)))
    
    info = {
        'status': 'Success',
        'points': int(np.sum(mask)),
        'correlation': corr,
        'mean_ship_speed': float(np.mean(ship_spd[mask])),
        'residual_std': float(np.std(np.abs(v_gps - z * v_bt)))
    }
    return phi_deg, A, info

def compute_absolute_velocities(u_rel: np.ndarray, v_rel: np.ndarray, w_rel: np.ndarray,
                                ship_ve: np.ndarray, ship_vn: np.ndarray,
                                ship_heave: Optional[np.ndarray] = None) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Calculates absolute earth-referenced water velocities:
    u_abs = u_rel + ship_ve
    v_abs = v_rel + ship_vn
    w_abs = w_rel + ship_heave (if provided)
    """
    N, nc = u_rel.shape
    u_abs = u_rel + ship_ve[:, np.newaxis]
    v_abs = v_rel + ship_vn[:, np.newaxis]
    
    if ship_heave is not None and len(ship_heave) == N:
        w_abs = w_rel + ship_heave[:, np.newaxis]
    else:
        w_abs = w_rel.copy()
        
    return u_abs, v_abs, w_abs
