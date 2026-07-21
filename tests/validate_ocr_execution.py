"""Validate OCR metadata, timeout, and failure behavior without real binaries."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from intake import OcrRecognition, OcrRuntimeError  # noqa: E402
from intake.ocr_runtime import TesseractOcrEngine, TesseractRuntime  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary_dir:
        root = Path(temporary_dir)
        executable = root / "tesseract.exe"
        executable.write_bytes(b"test")
        runtime = TesseractRuntime(root, executable, ("eng",), "5.5.0-test")
        image = root / "scan.png"
        image.write_bytes(b"image")
        engine = TesseractOcrEngine(runtime)

        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="Kenyan registry application evidence", stderr=""
        )
        with patch("intake.ocr_runtime.subprocess.run", return_value=completed):
            result = engine.recognize_image_with_metadata(image)
        assert isinstance(result, OcrRecognition)
        assert "Kenyan registry" in result.text
        assert result.confidence == 0.75
        assert result.language == "eng"
        assert result.engine_version == "5.5.0-test"
        with patch("intake.ocr_runtime.subprocess.run", return_value=completed):
            assert engine.recognize_image(image) == result.text

        with patch(
            "intake.ocr_runtime.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="tesseract", timeout=120),
        ):
            try:
                engine.recognize_image(image)
            except OcrRuntimeError as exc:
                assert "timed out" in str(exc)
            else:
                raise AssertionError("OCR timeout was not reported")

        failed = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="missing traineddata"
        )
        with patch("intake.ocr_runtime.subprocess.run", return_value=failed):
            try:
                engine.recognize_image(image)
            except OcrRuntimeError as exc:
                assert "traineddata" in str(exc)
            else:
                raise AssertionError("OCR subprocess failure was not reported")

    print("OCR EXECUTION VALIDATION PASS")


if __name__ == "__main__":
    main()
