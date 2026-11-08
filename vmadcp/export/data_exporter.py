"""
Data exporter for CSV, NetCDF, and Summary reports.
"""
import os
import datetime
import numpy as np
import h5py
from typing import Dict, Any

from ..io.data_structures import VMADCPDataset

class DataExporter:
    """Exports processed VM-ADCP dataset to NetCDF/HDF5 and CSV."""
    
    def __init__(self, dataset: VMADCPDataset):
        self.ds = dataset
        
    def export_csv_summary(self, filepath: str):
        """Exports profile layer-averaged time-series to CSV."""
        ds = self.ds
        valid = ds.times > 0
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("# VM-ADCP Post-Processed Layer Summary\n")
            f.write(f"# Exported on: {datetime.datetime.now().isoformat()}\n")
            f.write(f"# Misalignment angle: {ds.misalignment_angle_deg:.3f} deg\n")
            f.write(f"# Amplitude scale: {ds.amplitude_scale_factor:.4f}\n")
            f.write("Time_UTC,Longitude,Latitude,Ship_Heading_deg,Ship_Speed_m_s,Seabed_Depth_m,Surface_Current_Speed_m_s,Surface_Current_Dir_deg,Mean_Sv_dB\n")
            
            # Surface layer index (first 5 valid bins)
            surf_u = np.nanmean(ds.u_abs[:, :5], axis=1)
            surf_v = np.nanmean(ds.v_abs[:, :5], axis=1)
            surf_spd = np.sqrt(surf_u**2 + surf_v**2)
            surf_dir = (np.degrees(np.arctan2(surf_u, surf_v))) % 360.0
            mean_sv = np.nanmean(ds.volume_backscatter_sv[:, :5], axis=1)
            
            ship_spd = np.sqrt(ds.ship_vel_east**2 + ds.ship_vel_north**2)
            
            for i in range(len(ds.times)):
                dt_str = datetime.datetime.fromtimestamp(ds.times[i], datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"{dt_str},{ds.lon[i]:.6f},{ds.lat[i]:.6f},{ds.ship_heading[i]:.1f},{ship_spd[i]:.3f},{ds.bt_depth[i]:.2f},{surf_spd[i]:.3f},{surf_dir[i]:.1f},{mean_sv[i]:.1f}\n")

    def export_hdf5_netcdf(self, filepath: str):
        """Exports full 2D post-processed arrays into NetCDF-like HDF5 container."""
        ds = self.ds
        with h5py.File(filepath, 'w') as f:
            # Attributes
            f.attrs['title'] = "Vessel Mounted ADCP Post-Processed Dataset"
            f.attrs['instrument'] = ds.instrument_name
            f.attrs['frequency_khz'] = ds.frequency_khz
            f.attrs['misalignment_deg'] = ds.misalignment_angle_deg
            f.attrs['amplitude_scale'] = ds.amplitude_scale_factor
            
            # Dimensions
            f.create_dataset('time', data=ds.times)
            f.create_dataset('depth', data=ds.depth_bins)
            
            # Coordinates
            f.create_dataset('latitude', data=ds.lat)
            f.create_dataset('longitude', data=ds.lon)
            f.create_dataset('ship_heading', data=ds.ship_heading)
            f.create_dataset('ship_pitch', data=ds.ship_pitch)
            f.create_dataset('ship_roll', data=ds.ship_roll)
            f.create_dataset('ship_vel_east', data=ds.ship_vel_east)
            f.create_dataset('ship_vel_north', data=ds.ship_vel_north)
            
            # Bottom Track
            f.create_dataset('seabed_depth', data=ds.bt_depth)
            f.create_dataset('bt_vel_east', data=ds.bt_vel_east)
            f.create_dataset('bt_vel_north', data=ds.bt_vel_north)
            
            # Water Velocities (2D)
            f.create_dataset('u_abs', data=np.nan_to_num(ds.u_abs, nan=-9999.0))
            f.create_dataset('v_abs', data=np.nan_to_num(ds.v_abs, nan=-9999.0))
            f.create_dataset('w_abs', data=np.nan_to_num(ds.w_abs, nan=-9999.0))
            f.create_dataset('current_speed', data=np.nan_to_num(ds.current_speed, nan=-9999.0))
            f.create_dataset('current_direction', data=np.nan_to_num(ds.current_direction, nan=-9999.0))
            
            # Backscatter (2D)
            f.create_dataset('volume_backscatter_sv', data=np.nan_to_num(ds.volume_backscatter_sv, nan=-9999.0))
            f.create_dataset('echo_intensity', data=ds.echo_intensity_mean)
            
            # Mask (2D)
            f.create_dataset('qc_mask_valid', data=ds.mask_valid.astype(np.uint8))
