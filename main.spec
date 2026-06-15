# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


PROJECT_DIR = Path(globals().get("SPECPATH", ".")).resolve()

# Auto-detect all local .py modules as hidden imports
AUTO_HIDDEN_IMPORTS = sorted(
    {
        py_file.stem
        for py_file in PROJECT_DIR.glob("*.py")
        if py_file.name != "main.py" and not py_file.name.startswith("_")
    }
)

# Additional hidden imports required by the optimized codebase
EXTRA_HIDDEN_IMPORTS = [
    "urllib3.util.retry",       # twitch_client.py: Retry
    "requests.adapters",        # twitch_client.py: HTTPAdapter
]

ALL_HIDDEN_IMPORTS = sorted(set(AUTO_HIDDEN_IMPORTS + EXTRA_HIDDEN_IMPORTS))


a = Analysis(
    ['main.py'],
    pathex=[str(PROJECT_DIR)],
    binaries=[],
    datas=[],
    hiddenimports=ALL_HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='TwitchStreamManager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
