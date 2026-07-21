# -*- mode: python ; coding: utf-8 -*-
# PyInstaller one-folder spec. Build with: pyinstaller main.spec
#
# For release builds, run scripts/obfuscate_licensing.py FIRST to compile
# the licensing modules to .pyd (spec §6.3). Then run pyinstaller.

from PyInstaller.utils.hooks import collect_data_files, collect_submodules
from pathlib import Path

hiddenimports = []
for package_name in (
    "ai",
    "backup",
    "core",
    "docling",
    "docling_core",
    "docling_ibm_models",
    "docling_parse",
    "integrations",
    "intake",
    "licensing",
    "products",
    "rag",
    "scripts",
    "search",
    "ui",
    "vault",
    "wakilios",
):
    hiddenimports += collect_submodules(package_name)

docling_datas = []
for package_name in ("docling", "docling_core", "docling_ibm_models", "docling_parse"):
    docling_datas += collect_data_files(package_name, include_py_files=False)

datas = [
    ("products/product_catalog.json", "products"),
    ("resources/license_public_key.pem", "resources"),
    ("resources/public_kenyan_legal_docs.json", "resources"),
    ("ui/wakilios.qss", "ui"),
]
datas += docling_datas
docling_runtime = Path("runtime") / "docling"
if docling_runtime.exists():
    datas.append((str(docling_runtime), "runtime/docling"))
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
