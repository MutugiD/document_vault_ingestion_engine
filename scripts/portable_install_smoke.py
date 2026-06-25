"""Run a portable install smoke test from the generated release ZIP."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from release import APP_NAME, run_portable_install_smoke  # noqa: E402


def main() -> int:
    version = _project_version()
    zip_path = ROOT / "release-output" / f"{APP_NAME}-{version}-windows-x64.zip"
    result = run_portable_install_smoke(zip_path, ROOT / "test-output" / "portable-install")
    print(f"Portable install: {result.install_dir}")
    print(f"Executable: {result.executable}")
    return 0


def _project_version() -> str:
    import tomllib

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(pyproject["project"]["version"])


if __name__ == "__main__":
    raise SystemExit(main())
