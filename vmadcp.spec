# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = []
datas += collect_data_files('matplotlib')

hiddenimports = [
    'vmadcp',
    'vmadcp.io',
    'vmadcp.io.data_structures',
    'vmadcp.io.sigvm_reader',
    'vmadcp.io.rdi_reader',
    'vmadcp.processing',
    'vmadcp.processing.motion',
    'vmadcp.processing.bottom_track',
    'vmadcp.processing.backscatter',
    'vmadcp.processing.qc_filter',
    'vmadcp.processing.pipeline',
    'vmadcp.export',
    'vmadcp.export.gmt_exporter',
    'vmadcp.export.data_exporter',
    'vmadcp.gui',
    'vmadcp.gui.app',
    'vmadcp.gui.styles',
    'vmadcp.gui.widgets',
    'vmadcp.gui.widgets.profile_view',
    'vmadcp.gui.widgets.track_map',
    'vmadcp.gui.widgets.control_panel',
    'vmadcp.gui.widgets.offset_dialog',
    'matplotlib.backends.backend_tkagg',
    'scipy.ndimage',
    'h5py',
]
hiddenimports += collect_submodules('matplotlib')

a = Analysis(
    ['run_app.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='VMADCP_Studio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False, # Windowed GUI (no black cmd window)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='VMADCP_Studio',
)
