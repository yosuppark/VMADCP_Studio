"""
GMT (Generic Mapping Tools) exporter module.
Exports ADCP cruise track, velocity vectors, bathymetry, and backscatter
into GMT-compatible tables and generates modern GMT6 plotting scripts (.bat / .sh).
"""
import os
import math
import numpy as np
from typing import Optional, Dict, Any, List

from ..io.data_structures import VMADCPDataset

class GMTExporter:
    """Generates GMT 6 scripts and datasets for publication-quality Track Charts."""
    
    def __init__(self, dataset: VMADCPDataset):
        self.ds = dataset
        
    def export(self, output_dir: str,
               depth_layer_min_m: float = 5.0,
               depth_layer_max_m: float = 15.0,
               decimate_step: int = 15,
               vector_scale_cm_per_m_s: float = 2.0) -> Dict[str, str]:
        """
        Exports all GMT files into output_dir.
        Returns dictionary of created file paths.
        """
        os.makedirs(output_dir, exist_ok=True)
        ds = self.ds
        
        # 1. Filter region bounding box
        valid_coords = (~np.isnan(ds.lat)) & (~np.isnan(ds.lon)) & (ds.lat != 0.0)
        if not np.any(valid_coords):
            raise ValueError("No valid GPS coordinates available to export GMT chart.")
            
        lats = ds.lat[valid_coords]
        lons = ds.lon[valid_coords]
        
        min_lon, max_lon = float(np.min(lons)), float(np.max(lons))
        min_lat, max_lat = float(np.min(lats)), float(np.max(lats))
        
        # Add 10% padding
        dlon = max(max_lon - min_lon, 0.01) * 0.15
        dlat = max(max_lat - min_lat, 0.01) * 0.15
        region_str = f"{min_lon - dlon:.4f}/{max_lon + dlon:.4f}/{min_lat - dlat:.4f}/{max_lat + dlat:.4f}"
        
        # 2. Export Track Line (lon, lat)
        track_path = os.path.join(output_dir, "track_line.txt")
        with open(track_path, "w", encoding="utf-8") as f:
            f.write("# Ship Track Line (Longitude, Latitude)\n")
            f.write("# Lon\tLat\n")
            for lo, la in zip(lons, lats):
                f.write(f"{lo:.6f}\t{la:.6f}\n")
                
        # 3. Layer average velocity vectors
        # Find cell indices within depth range
        cell_mask = (ds.depth_bins >= depth_layer_min_m) & (ds.depth_bins <= depth_layer_max_m)
        if not np.any(cell_mask):
            cell_mask = np.ones(len(ds.depth_bins), dtype=bool)
            
        u_layer = np.nanmean(ds.u_abs[:, cell_mask], axis=1) # (N,)
        v_layer = np.nanmean(ds.v_abs[:, cell_mask], axis=1) # (N,)
        spd_layer = np.sqrt(u_layer**2 + v_layer**2)
        
        # Export Velocity Vectors for GMT velo
        # Format for 'gmt velo -Se':
        # lon lat u_vel v_vel sigma_u sigma_v corr [label]
        velo_path = os.path.join(output_dir, "current_vectors.txt")
        with open(velo_path, "w", encoding="utf-8") as f:
            f.write(f"# Depth Layer Averaged Current Vectors ({depth_layer_min_m:.1f}m - {depth_layer_max_m:.1f}m)\n")
            f.write("# Lon\tLat\tEast_vel(m/s)\tNorth_vel(m/s)\tsigma_u\tsigma_v\tcorrelation\n")
            for i in range(0, len(ds.times), decimate_step):
                if not valid_coords[i]:
                    continue
                lo = ds.lon[i]
                la = ds.lat[i]
                u = u_layer[i]
                v = v_layer[i]
                if not (np.isnan(u) or np.isnan(v)):
                    f.write(f"{lo:.6f}\t{la:.6f}\t{u:.4f}\t{v:.4f}\t0.02\t0.02\t0.0\n")
                    
        # 4. Export Bathymetry (lon, lat, depth)
        bathy_path = os.path.join(output_dir, "bathymetry.xyz")
        with open(bathy_path, "w", encoding="utf-8") as f:
            f.write("# ADCP Seabed Bathymetry\n# Lon\tLat\tDepth_m\n")
            for i in range(len(ds.times)):
                if valid_coords[i] and not np.isnan(ds.bt_depth[i]):
                    f.write(f"{ds.lon[i]:.6f}\t{ds.lat[i]:.6f}\t{ds.bt_depth[i]:.2f}\n")
                    
        # 5. Export Backscatter Surface / Layer Mean (lon, lat, Sv)
        sv_layer = np.nanmean(ds.volume_backscatter_sv[:, cell_mask], axis=1)
        sv_path = os.path.join(output_dir, "backscatter_layer.xyz")
        with open(sv_path, "w", encoding="utf-8") as f:
            f.write(f"# Mean Volume Backscattering Strength Sv (dB) [{depth_layer_min_m:.1f}m - {depth_layer_max_m:.1f}m]\n")
            f.write("# Lon\tLat\tSv_dB\n")
            for i in range(len(ds.times)):
                if valid_coords[i] and not np.isnan(sv_layer[i]):
                    f.write(f"{ds.lon[i]:.6f}\t{ds.lat[i]:.6f}\t{sv_layer[i]:.2f}\n")
                    
        # 6. Generate Modern GMT 6 Batch Script (Windows .bat)
        bat_path = os.path.join(output_dir, "plot_track_chart.bat")
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write("@echo off\n")
            f.write("REM ========================================================\n")
            f.write("REM Vessel Mounted ADCP Track Chart & Current Vector Plot\n")
            f.write("REM Generated by VMADCP Post-Processing System\n")
            f.write("REM ========================================================\n\n")
            f.write("set OUTPUT_NAME=VMADCP_Track_Chart\n")
            f.write(f"set REGION={region_str}\n")
            f.write("set PROJECTION=M16c\n\n")
            f.write("echo [GMT] Generating publication-quality ADCP Track Chart...\n")
            f.write("gmt begin %OUTPUT_NAME% png,pdf\n")
            f.write("    gmt set FONT_ANNOT_PRIMARY 9p,Helvetica,black\n")
            f.write("    gmt set FONT_LABEL 11p,Helvetica-Bold,black\n")
            f.write("    gmt set MAP_FRAME_TYPE fancy\n\n")
            f.write("    REM 1. Basemap and Coastlines\n")
            f.write("    gmt basemap -R%REGION% -J%PROJECTION% -Bafg -B+t\"Vessel Mounted ADCP Track & Current Vectors\"\n")
            f.write("    gmt coast -W0.5p,black -G230/230/230 -S210/230/250 -Df -Ia/0.25p,blue\n\n")
            f.write("    REM 2. Plot Cruise Track Line\n")
            f.write("    gmt plot track_line.txt -W1.5p,darkgray\n\n")
            f.write("    REM 3. Plot Current Vectors (gmt velo)\n")
            f.write(f"    REM Vector scale: 1 m/s = {vector_scale_cm_per_m_s:.1f} cm on map\n")
            f.write(f"    gmt velo current_vectors.txt -Se{vector_scale_cm_per_m_s:.2f}/0.95/0 -W1.0p,red -Gred\n\n")
            f.write("    REM 4. Start & End points\n")
            f.write(f"    echo {lons[0]} {lats[0]} Start | gmt text -F+f9p,Helvetica-Bold,forestgreen+jRB -D0.2c/0.2c\n")
            f.write(f"    echo {lons[-1]} {lats[-1]} End   | gmt text -F+f9p,Helvetica-Bold,firebrick+jLT -D0.2c/0.2c\n\n")
            f.write("    REM 5. Velocity Vector Legend\n")
            f.write(f"    echo {min_lon + dlon*0.5:.4f} {min_lat + dlat*0.5:.4f} 0.5 0.0 0.0 0.0 0.0 | gmt velo -Se{vector_scale_cm_per_m_s:.2f}/0.95/0 -W1.2p,black -Gblack\n")
            f.write(f"    echo {min_lon + dlon*0.5:.4f} {min_lat + dlat*0.3:.4f} 0.5 m/s | gmt text -F+f8p,Helvetica-Bold,black+jCT\n")
            f.write("gmt end show\n\n")
            f.write("echo [GMT] Plotting complete: %OUTPUT_NAME%.png\n")
            
        # 7. Generate Linux/macOS Shell Script (.sh)
        sh_path = os.path.join(output_dir, "plot_track_chart.sh")
        with open(sh_path, "w", encoding="utf-8") as f:
            f.write("#!/usr/bin/env bash\n")
            f.write("# Generated by VMADCP Post-Processing System\n")
            f.write("OUTPUT_NAME=\"VMADCP_Track_Chart\"\n")
            f.write(f"REGION=\"{region_str}\"\n")
            f.write("PROJECTION=\"M16c\"\n\n")
            f.write("gmt begin $OUTPUT_NAME png,pdf\n")
            f.write("    gmt set FONT_ANNOT_PRIMARY 9p,Helvetica,black\n")
            f.write("    gmt set FONT_LABEL 11p,Helvetica-Bold,black\n")
            f.write("    gmt set MAP_FRAME_TYPE fancy\n")
            f.write("    gmt basemap -R$REGION -J$PROJECTION -Bafg -B+t\"Vessel Mounted ADCP Track & Current Vectors\"\n")
            f.write("    gmt coast -W0.5p,black -G230/230/230 -S210/230/250 -Df -Ia/0.25p,blue\n")
            f.write("    gmt plot track_line.txt -W1.5p,darkgray\n")
            f.write(f"    gmt velo current_vectors.txt -Se{vector_scale_cm_per_m_s:.2f}/0.95/0 -W1.0p,red -Gred\n")
            f.write(f"    echo \"{lons[0]} {lats[0]} Start\" | gmt text -F+f9p,Helvetica-Bold,forestgreen+jRB -D0.2c/0.2c\n")
            f.write(f"    echo \"{lons[-1]} {lats[-1]} End\"   | gmt text -F+f9p,Helvetica-Bold,firebrick+jLT -D0.2c/0.2c\n")
            f.write("gmt end show\n")
            
        return {
            "track": track_path,
            "vectors": velo_path,
            "bathymetry": bathy_path,
            "backscatter": sv_path,
            "bat_script": bat_path,
            "sh_script": sh_path
        }
