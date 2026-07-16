"""
Free licensing obfuscation for WakiliOS (no PyArmor).

Compiles licensing modules to native .pyd/.so using Cython, so the shipped
bundle carries compiled machine code for the licence/clock logic instead of
decompilable .pyc. The hard-coded RSA public key (spec §6.2) is baked into
core.pyd.

What it does (in place, intended for a RELEASE checkout -- it removes source):
  1. Cythonize licensing/core.py, licensing/clockguard.py -> *.pyd (via Cython + C compiler),
  2. Delete the .py (and generated .c), leaving __init__.py + the .pyd + public_key.pem,
  3. Smoke-import the compiled package so the build fails loudly if broken.

Prerequisites (build host only): pip install cython + a C compiler.
On Windows: MSVC Build Tools for Visual Studio (free).
On Linux: gcc.

Usage:
    python scripts/obfuscate_licensing.py            # compile + strip sources (release)
    python scripts/obfuscate_licensing.py --keep-sources   # compile but keep .py (inspect)
    python scripts/obfuscate_licensing.py --check    # just verify Cython + compiler available
"""

from __future__ import annotations

import argparse
import glob
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "licensing")
# __init__.py stays a thin re-export; public_key.pem is data
MODULES = ("core", "clockguard")


def _have_compiler() -> bool:
    """True if a C compiler is available."""
    try:
        from setuptools._distutils import ccompiler, errors

        c = ccompiler.new_compiler()
        try:
            c.initialize()
        except (errors.DistutilsPlatformError, AttributeError):
            return False
        return True
    except Exception:
        return False


def _check() -> int:
    try:
        import Cython  # noqa: F401

        cy = True
    except ImportError:
        cy = False
    cc = _have_compiler()
    print(f"Cython installed : {cy}")
    print(f"C compiler found : {cc}")
    if not cy:
        print("  -> pip install cython")
    if not cc:
        print("  -> install MSVC Build Tools (Windows) or gcc (Linux)")
    return 0 if (cy and cc) else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Cython-obfuscate the licensing package.")
    ap.add_argument(
        "--keep-sources",
        action="store_true",
        help="keep the .py after compiling (inspect)",
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="only report Cython + compiler availability",
    )
    args = ap.parse_args(argv)

    if args.check:
        return _check()
    if _check() != 0:
        print("\nERROR: prerequisites missing (see above).")
        return 2

    print(f"\ncythonize -> .pyd: {', '.join(MODULES)}")
    tmp = tempfile.mkdtemp(prefix="obf_licensing_")
    try:
        build_pkg = os.path.join(tmp, "licensing")
        os.makedirs(build_pkg)
        # Copy __init__.py
        shutil.copy2(os.path.join(PKG, "__init__.py"), build_pkg)
        # Copy data files
        for data_file in ("public_key.pem",):
            src = os.path.join(PKG, data_file)
            if os.path.exists(src):
                shutil.copy2(src, build_pkg)
        # Copy source files
        for m in MODULES:
            shutil.copy2(os.path.join(PKG, f"{m}.py"), build_pkg)

        # Create __init__.py in tmp build dir that imports from the compiled modules
        # (Cython needs this for module resolution)

        r = subprocess.run(
            [sys.executable, "-m", "Cython.Build.Cythonize", "-i", "-3"]
            + [os.path.join("licensing", f"{m}.py") for m in MODULES],
            cwd=tmp,
        )
        if r.returncode != 0:
            print("ERROR: cythonize failed")
            return 2

        for m in MODULES:
            built = glob.glob(os.path.join(build_pkg, f"{m}.*.pyd"))
            if not built:
                built = glob.glob(os.path.join(build_pkg, f"{m}.*.so"))
            if not built:
                print(f"ERROR: no compiled extension produced for {m}")
                return 2
            shutil.copy2(built[0], os.path.join(PKG, os.path.basename(built[0])))
            if not args.keep_sources:
                os.remove(os.path.join(PKG, f"{m}.py"))
            status = "removed" if not args.keep_sources else "kept"
            print(f"  {m}: {os.path.basename(built[0])} ({status})")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # Clean up generated .c files
    for m in MODULES:
        c_file = os.path.join(PKG, f"{m}.c")
        if os.path.exists(c_file):
            os.remove(c_file)

    # Smoke-import the compiled package
    smoke = "import licensing; print('compiled OK')"
    chk = subprocess.run([sys.executable, "-c", smoke], cwd=ROOT)
    if chk.returncode != 0:
        print("ERROR: compiled licensing package failed to import")
        return 2
    print("\nlicensing/ obfuscated (native extension). Now run: pyinstaller main.spec")
    return 0


if __name__ == "__main__":
    sys.exit(main())
