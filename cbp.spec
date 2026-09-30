import os
import sys

block_cipher = None
icon_path = os.path.join(SPECPATH, "logo.ico") if sys.platform == "win32" else None

a = Analysis(
    ["cbp.py"],
    pathex=[SPECPATH],
    binaries=[],
    datas=[(os.path.join(SPECPATH, "logo.png"), "."), (os.path.join(SPECPATH, "logo.ico"), ".")],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "scipy", "pandas", "PyQt5", "PySide2", "PySide6", "setuptools", "pip", "wheel", "unittest", "pydoc_data", "lib2to3"],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CBP",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=icon_path,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="CBP",
)
