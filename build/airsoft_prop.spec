# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Airsoft Prop standalone build.

Build with:  pyinstaller build/airsoft_prop.spec
Output:      dist/AirsoftProp/AirsoftProp.exe

After building, copy config/ and assets/ into dist/AirsoftProp/:
    xcopy /E /I config dist\\AirsoftProp\\config
    xcopy /E /I assets dist\\AirsoftProp\\assets
"""

from pathlib import Path

block_cipher = None
project_root = Path(SPECPATH).parent

a = Analysis(
    [str(project_root / "src" / "main.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=[],
    hiddenimports=[
        # Game modes (dynamically imported via importlib)
        "src.modes.random_code",
        "src.modes.set_code",
        "src.modes.random_code_plus",
        "src.modes.set_code_plus",
        "src.modes.usb_key_cracker",
        # pygame internals
        "pygame.mixer",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(project_root / "build" / "hook-runtime-mock.py")],
    excludes=[
        # Web server (not needed in standalone)
        "flask",
        "werkzeug",
        "jinja2",
        "markupsafe",
        "blinker",
        "itsdangerous",
        "click",
        "src.web",
        "src.web.server",
        "src.web.wifi_manager",
        "src.web.captive_portal",
        # RPi-only libraries
        "RPi",
        "RPi.GPIO",
        "RPLCD",
        "smbus2",
        "gpiozero",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AirsoftProp",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # Terminal needed for mock display
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="AirsoftProp",
)
