# -*- mode: python ; coding: utf-8 -*-
# PyInstaller one-folder spec. Build with: pyinstaller main.spec

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=["hooks"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DocumentVaultIngestionEngine",
    debug=False,
    strip=True,
    upx=False,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=True,
    upx=False,
    name="DocumentVaultIngestionEngine",
)
