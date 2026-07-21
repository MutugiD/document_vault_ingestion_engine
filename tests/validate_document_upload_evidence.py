"""Evidence that UI uploads reach intake, encrypted vault, search, and restore."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fitz  # noqa: E402
from docx import Document  # noqa: E402
from fixture_document_understanding import FixtureDocumentUnderstanding  # noqa: E402
from PySide6.QtWidgets import QListWidget  # noqa: E402

from ui import MainWindow, create_app  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="dv-upload-evidence-") as temporary_dir:
        root = Path(temporary_dir)
        sources = root / "sources"
        sources.mkdir()
        pdf = sources / "kenyan-application.pdf"
        docx = sources / "registry-letter.docx"
        _write_pdf(pdf, "Kenyan application registry evidence 001")
        _write_docx(docx, "Registry letter evidence for Nairobi matter 001")

        app = create_app(["validate_document_upload_evidence"])
        window = MainWindow(
            workspace=root / "app-workspace",
            document_understanding=FixtureDocumentUnderstanding(),
        )
        window.import_files([pdf, docx])
        app.processEvents()

        queue = window.findChild(QListWidget, "documentReviewQueue")
        assert queue is not None
        assert queue.count() == 2
        results = window.manual_session.import_results
        assert len(results) == 2
        assert all(result.status == "accepted" for result in results)
        assert all(result.source_copy_preserved for result in results)
        assert all(result.vault_object_created for result in results)
        assert all(result.text_available for result in results)

        object_files = list((root / "app-workspace" / "vault" / "objects").rglob("*.vaultobj"))
        assert len(object_files) == 4
        source_bytes = {pdf.read_bytes(), docx.read_bytes()}
        assert all(path.read_bytes() not in source_bytes for path in object_files)
        assert all(
            b"Kenyan application registry evidence" not in path.read_bytes()
            for path in object_files
        )

        assert window.manual_session.search("registry evidence") > 0
        backup = window.manual_session.backup_and_restore()
        assert backup.restore_verified
        assert backup.wrong_key_failed

        window.close()
        app.processEvents()

    print("DOCUMENT UPLOAD EVIDENCE PASS")


def _write_pdf(path: Path, text: str) -> None:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    document.save(path)
    document.close()


def _write_docx(path: Path, text: str) -> None:
    document = Document()
    document.add_paragraph(text)
    document.save(path)


if __name__ == "__main__":
    main()
