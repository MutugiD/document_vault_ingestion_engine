# -*- mode: python ; coding: utf-8 -*-
# PyInstaller one-folder spec. Build with: pyinstaller main.spec

from PyInstaller.utils.hooks import collect_submodules
from pathlib import Path

hiddenimports = []
for package_name in (
    "ai",
    "backup",
    "core",
    "intake",
    "licensing",
    "products",
    "rag",
    "scripts",
    "search",
    "ui",
    "vault",
):
    hiddenimports += collect_submodules(package_name)

datas = [
    ("products/product_catalog.json", "products"),
    ("resources/license_public_key.pem", "resources"),
    ("resources/public_kenyan_legal_docs.json", "resources"),
]
tesseract_runtime = Path("runtime") / "tesseract"
if tesseract_runtime.exists():
    datas.append((str(tesseract_runtime), "runtime/tesseract"))

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
    strip=False,
    upx=False,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="DocumentVaultIngestionEngine",
)
