"""Validate the mandatory Docling model bundle integrity boundary."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from intake import DoclingRuntimeError, validate_docling_runtime  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary_dir:
        root = Path(temporary_dir) / "docling"
        models = root / "models"
        models.mkdir(parents=True)
        model_path = models / "layout-model.bin"
        model_path.write_bytes(b"deterministic docling model fixture")
        manifest = {
            "manifest_format_version": 1,
            "provider": "docling",
            "version": "2.41.0-test",
            "files": [
                {
                    "relative_path": "models/layout-model.bin",
                    "size_bytes": model_path.stat().st_size,
                    "sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
                }
            ],
        }
        manifest_path = root / "docling-runtime.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        result = validate_docling_runtime(root)
        assert result["provider"] == "docling"
        assert result["files_verified"] == 1

        model_path.write_bytes(b"tampered")
        try:
            validate_docling_runtime(root)
        except DoclingRuntimeError as exc:
            assert any(term in str(exc) for term in ("size mismatch", "hash mismatch"))
        else:
            raise AssertionError("tampered Docling model unexpectedly passed validation")

    print("DOCLING RUNTIME VALIDATION PASS")


if __name__ == "__main__":
    main()
