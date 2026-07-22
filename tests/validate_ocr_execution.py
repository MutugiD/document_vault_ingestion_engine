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
        engine = TesseractOcrEngine(runtime, preprocess=False)

        tsv = (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
            "5\t1\t1\t1\t1\t1\t0\t0\t10\t10\t75.0\tKenyan\n"
            "5\t1\t1\t1\t1\t2\t0\t0\t10\t10\t85.0\tregistry\n"
            "5\t1\t1\t1\t1\t3\t0\t0\t10\t10\t65.0\tapplication\n"
            "5\t1\t1\t1\t1\t4\t0\t0\t10\t10\t75.0\tevidence\n"
        )

        class FakeProcess:
            returncode = 0

            def communicate(self, timeout=None):
                return tsv, ""

            def kill(self):
                raise AssertionError("unexpected kill")

        with patch("intake.ocr_runtime.subprocess.Popen", return_value=FakeProcess()):
            result = engine.recognize_image_with_metadata(image)
        assert isinstance(result, OcrRecognition)
        assert "Kenyan registry" in result.text
        assert result.confidence == 0.75
        assert result.language == "eng"
        assert result.engine_version == "5.5.0-test"
        with patch("intake.ocr_runtime.subprocess.Popen", return_value=FakeProcess()):
            assert engine.recognize_image(image) == result.text

        class TimeoutProcess(FakeProcess):
            timed_out = False

            def communicate(self, timeout=None):
                if self.timed_out:
                    return "", ""
                self.timed_out = True
                raise subprocess.TimeoutExpired(cmd="tesseract", timeout=120)

            def kill(self):
                self.returncode = -9

        with patch(
            "intake.ocr_runtime.subprocess.Popen",
            return_value=TimeoutProcess(),
        ):
            try:
                engine.recognize_image(image)
            except OcrRuntimeError as exc:
                assert "timed out" in str(exc)
            else:
                raise AssertionError("OCR timeout was not reported")

        class FailedProcess(FakeProcess):
            returncode = 1

            def communicate(self, timeout=None):
                return "", "missing traineddata"

        with patch("intake.ocr_runtime.subprocess.Popen", return_value=FailedProcess()):
            try:
                engine.recognize_image(image)
            except OcrRuntimeError as exc:
                assert "traineddata" in str(exc)
            else:
                raise AssertionError("OCR subprocess failure was not reported")

    print("OCR EXECUTION VALIDATION PASS")


if __name__ == "__main__":
    main()
