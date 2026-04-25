# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller configuration for LLM-ROUTE
Cross-platform build support for Windows, Linux, and macOS
"""

import os
import sys
import platform

block_cipher = None

# Detect current platform
current_system = platform.system()

# Check if icon exists
icon_path = None
if current_system == "Windows":
    icon_path = "icon.ico"
    if not os.path.exists(icon_path):
        icon_path = None
elif current_system == "Darwin":
    icon_path = "icon.icns"
    if not os.path.exists(icon_path):
        icon_path = None

# Platform-specific hidden imports
hiddenimports = [
    'PIL._tkinter_finder',
    'pystray',
    'pystray._base',
]

if current_system == "Linux":
    # GI requires explicit declaration of specific repositories
    hiddenimports.extend([
        'gi',
        'gi.repository',
        'gi.repository.AppIndicator3',
        'gi.repository.GLib',
        'gi.repository.GdkPixbuf',
    ])
elif current_system == "Windows":
    hiddenimports.extend([
        'pystray._win32',
        'pystray._win32.Notification',
    ])
elif current_system == "Darwin":
    # macOS uses pystray's native backend
    hiddenimports.extend([
        'pystray._darwin',
        'pystray._darwin.Notification',
    ])

# Platform-specific data files
datas = [
    ('config.yaml', '.'),
    ('presets', 'presets'),
]

# On Linux, collect GI data files
if current_system == "Linux":
    try:
        from PyInstaller.utils.hooks import collect_data_files
        gi_data = collect_data_files('gi')
        datas.extend(gi_data)
    except Exception:
        pass

a = Analysis(
    ['src/main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter.test',
        'unittest',
        'pydoc',
    ],
    win_no_prefer_redirects=False if current_system == "Windows" else None,
    win_private_assemblies=False if current_system == "Windows" else None,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

if current_system == "Darwin":
    # macOS: Create .app bundle
    exe = EXE(
        pyz,
        a.scripts,
        exclude_binaries=True,
        name='llm-route',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=True,
        icon=icon_path,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name='llm-route',
    )
    app = BUNDLE(
        coll,
        name='LLM-ROUTE.app',
        icon=icon_path,
        bundle_identifier='com.llm-route.app',
        version='1.0.0',
        info_plist={
            'NSHighResolutionCapable': True,
            'LSMinimumSystemVersion': '10.13',
        },
    )
else:
    # Windows and Linux: Create single executable
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name='llm-route',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True if current_system != "Darwin" else False,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False if current_system == "Windows" else True,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=icon_path,
    )
