"""Validate a portable install extracted from the checked release ZIP."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from release import APP_NAME, run_portable_install_smoke  # noqa: E402


def main() -> None:
    if sys.platform != "win32":
        print("PORTABLE INSTALL VALIDATION SKIP: Windows-only validator")
        return

    zip_path = _release_zip_path()
    assert zip_path.exists(), (
        "missing release ZIP; run tests\\validate_release_bundle.py before portable install"
    )

    result = run_portable_install_smoke(zip_path, ROOT / "test-output" / "portable-install")
    assert result.executable.exists()
    assert "SELFTEST PASS" in result.selftest_stdout
    assert "windows-legal-document-vault" in result.products_stdout
    assert "document-intake-engine" in result.products_stdout
    assert "local-matter-rag-connector" in result.products_stdout

    print("PORTABLE INSTALL VALIDATION PASS")
    print(f"Portable install: {result.install_dir}")


def _release_zip_path() -> Path:
    import tomllib

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = str(pyproject["project"]["version"])
    return ROOT / "release-output" / f"{APP_NAME}-{version}-windows-x64.zip"


if __name__ == "__main__":
    main()
