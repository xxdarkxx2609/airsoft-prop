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
    datas=[
        (str(project_root / "src" / "web" / "templates"), "src/web/templates"),
        (str(project_root / "src" / "web" / "static"), "src/web/static"),
    ],
    hiddenimports=[
        # Game modes (dynamically imported via importlib)
        "src.modes.random_code",
        "src.modes.set_code",
        "src.modes.random_code_plus",
        "src.modes.set_code_plus",
        "src.modes.usb_key_cracker",
        "src.modes.cut_the_wire",
        # pygame internals
        "pygame.mixer",
        "pygame.display",
        "pygame.event",
        "pygame.font",
        "pygame.draw",
        "pygame.transform",
        "pygame.locals",
        # Mock display (graphical LCD window)
        "src.hal.display_mock_pygame",
        # Web server modules (dynamically imported)
        "src.web.server",
        "src.web.wifi_manager",
        "src.web.captive_portal",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(project_root / "build" / "hook-runtime-mock.py")],
    excludes=[
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
    console=True,  # Keep console open for log output
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
