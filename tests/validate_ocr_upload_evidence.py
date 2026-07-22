"""Evidence for scanned-image upload through UI, vault, backup, and restore."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QListWidget  # noqa: E402

from ui import MainWindow, create_app  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="dv-ocr-upload-evidence-") as temporary_dir:
        root = Path(temporary_dir)
        source = root / "scanned-kenyan-registry.png"
        source.write_bytes(b"\x89PNG\r\n\x1a\nscanned fixture")
        source.with_suffix(source.suffix + ".ocr.txt").write_text(
            "Kenyan registry scanned application evidence", encoding="utf-8"
        )

        app = create_app(["validate_ocr_upload_evidence"])
        window = MainWindow(workspace=root / "app-workspace")
        window.import_files([source])
        app.processEvents()

        queue = window.findChild(QListWidget, "documentReviewQueue")
        assert queue is not None and queue.count() == 1
        result = window.manual_session.import_results[0]
        assert result.status == "accepted"
        assert result.extraction_status == "completed_tesseract"
        assert result.text_available
        assert result.vault_object_created
        assert result.source_copy_preserved

        backup = window.manual_session.backup_and_restore()
        assert backup.restore_verified
        assert backup.wrong_key_failed
        window.close()
        app.processEvents()

    print("OCR UPLOAD EVIDENCE PASS")


if __name__ == "__main__":
    main()
