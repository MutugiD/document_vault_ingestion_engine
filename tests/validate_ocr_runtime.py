"""Validate the Tesseract OCR runtime bundle manifest contract."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from intake import (  # noqa: E402
    OcrRuntimeError,
    create_tesseract_manifest,
    validate_tesseract_runtime,
)


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary_dir:
        bundle_root = Path(temporary_dir) / "tesseract"
        tessdata = bundle_root / "tessdata"
        tessdata.mkdir(parents=True)
        (bundle_root / "tesseract.exe").write_bytes(b"fake tesseract runtime for tests")
        (tessdata / "eng.traineddata").write_bytes(b"fake english traineddata")

        manifest_payload = create_tesseract_manifest(bundle_root, "5.5.0-test", ("eng",))
        manifest_path = bundle_root / "tesseract-runtime.json"
        manifest_path.write_text(json.dumps(manifest_payload, indent=2), encoding="utf-8")

        runtime = validate_tesseract_runtime(bundle_root, manifest_path)
        assert runtime.executable == bundle_root.resolve() / "tesseract.exe"
        assert runtime.languages == ("eng",)
        assert runtime.version == "5.5.0-test"

        tampered = dict(manifest_payload)
        tampered["files"] = [dict(item) for item in manifest_payload["files"]]  # type: ignore[index]
        tampered["files"][0]["sha256"] = "0" * 64  # type: ignore[index]
        tampered_path = bundle_root / "tampered-runtime.json"
        tampered_path.write_text(json.dumps(tampered, indent=2), encoding="utf-8")
        try:
            validate_tesseract_runtime(bundle_root, tampered_path)
        except OcrRuntimeError as exc:
            assert "hash mismatch" in str(exc)
        else:
            raise AssertionError("tampered OCR runtime manifest should fail validation")

        escaping = dict(manifest_payload)
        escaping["executable"] = "../tesseract.exe"
        escaping_path = bundle_root / "escaping-runtime.json"
        escaping_path.write_text(json.dumps(escaping, indent=2), encoding="utf-8")
        try:
            validate_tesseract_runtime(bundle_root, escaping_path)
        except OcrRuntimeError as exc:
            assert "escapes bundle root" in str(exc)
        else:
            raise AssertionError("escaping OCR runtime path should fail validation")

    print("OCR RUNTIME VALIDATION PASS")


if __name__ == "__main__":
    main()
