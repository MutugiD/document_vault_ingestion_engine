"""Build the checked Windows release ZIP from the frozen PyInstaller output."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from release import APP_NAME, create_release_bundle  # noqa: E402


def main() -> int:
    bundle = create_release_bundle(ROOT / "dist" / APP_NAME, ROOT / "release-output", ROOT)
    print(f"Release ZIP: {bundle.zip_path}")
    print(f"Release manifest: {bundle.manifest_path}")
    print(f"Bundle SHA-256: {bundle.manifest.bundle_sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
