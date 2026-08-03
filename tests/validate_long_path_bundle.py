"""Validate that the release bundle survives Windows MAX_PATH.

The frozen bundle contains deeply nested third-party licence directories --
``_internal/torch-*.dist-info/licenses/third_party/kineto/libkineto/third_party/
dynolog/third_party/DCGM/testing/python3/libs_3rdparty/colorama`` and similar.
Once an install root is prepended these exceed the 260-character Windows path
cap, and every plain filesystem call against them fails with WinError 206.

That broke three things in sequence: building the bundle, extracting it, and
cleaning up a previous extraction. The third mattered most -- it is what a
customer hits when they unzip to anywhere but a very short path.

Those licence files must be distributed, so excluding them is not an option.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from release.bundle import _long_path  # noqa: E402

# Deliberately past MAX_PATH once a root is prepended.
DEEP = Path(
    "_internal/torch-2.13.0.dist-info/licenses/third_party/kineto/libkineto/"
    "third_party/dynolog/third_party/DCGM/testing/python3/libs_3rdparty/colorama"
)


def main() -> None:
    if os.name != "nt":
        # The cap is a Windows constraint; the helper is a no-op elsewhere.
        assert _long_path(Path("/tmp/x")) == "/tmp/x"
        print("LONG PATH BUNDLE VALIDATION SKIPPED (not Windows)")
        return

    prefixed = _long_path(Path.cwd() / "sample")
    assert prefixed.startswith("\\\\?\\"), prefixed
    # Applying it twice must not double the prefix.
    assert _long_path(Path(prefixed)) == prefixed

    with tempfile.TemporaryDirectory() as temp_dir:
        # A customer unzips into Downloads or a synced folder, not a short temp
        # path, so pad to a realistic install depth before nesting.
        root = (
            Path(temp_dir)
            / "Users"
            / "advocate.name"
            / "OneDrive - Kiunga and Company Advocates"
            / "Downloads"
            / "DocumentVaultIngestionEngine-0.1.0-windows-x64"
            / "DocumentVaultIngestionEngine"
        )
        target = root / DEEP
        assert len(str(target)) > 260, (
            f"test path is only {len(str(target))} characters; it no longer "
            f"exercises the MAX_PATH limit"
        )

        # Creating, writing and reading all have to go through the extended form.
        os.makedirs(_long_path(target), exist_ok=True)
        licence = target / "LICENSE.txt"
        with open(_long_path(licence), "w", encoding="utf-8") as handle:
            handle.write("Apache License 2.0")
        with open(_long_path(licence), encoding="utf-8") as handle:
            assert handle.read() == "Apache License 2.0"

        # And removal, which is what failed on a repeat portable-install run.
        import shutil

        shutil.rmtree(_long_path(root))
        assert not root.exists(), "deep tree was not removed"

    print("LONG PATH BUNDLE VALIDATION PASS")


if __name__ == "__main__":
    main()
