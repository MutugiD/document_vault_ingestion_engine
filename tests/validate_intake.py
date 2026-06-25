"""Validate F3 document intake behavior."""

from __future__ import annotations

import hashlib
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from intake import (  # noqa: E402
    ACCEPTED_STATUS,
    DUPLICATE_STATUS,
    REJECTED_STATUS,
    import_document,
    list_intake_records,
)
from vault import initialize_vault  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary_dir:
        workspace = Path(temporary_dir)
        vault_root = workspace / "vault"
        initialize_vault(vault_root, "intake validator recovery key")

        pdf_path = workspace / "sample-pleading.pdf"
        pdf_bytes = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
        pdf_path.write_bytes(pdf_bytes)
        pdf_record = import_document(vault_root, pdf_path)
        assert pdf_record.status == ACCEPTED_STATUS
        assert pdf_record.detected_file_type == "pdf"
        assert pdf_record.source_sha256 == hashlib.sha256(pdf_bytes).hexdigest()
        assert pdf_record.quarantine_path.exists()
        assert pdf_record.quarantine_path.read_bytes() == pdf_bytes

        duplicate_record = import_document(vault_root, pdf_path)
        assert duplicate_record.status == DUPLICATE_STATUS
        assert "duplicate_source_hash" in duplicate_record.warnings

        mismatched_pdf_path = workspace / "wrong-extension.docx"
        mismatched_pdf_path.write_bytes(pdf_bytes + b"second")
        mismatched_record = import_document(vault_root, mismatched_pdf_path)
        assert mismatched_record.status == ACCEPTED_STATUS
        assert mismatched_record.detected_file_type == "pdf"
        assert "extension_signature_mismatch" in mismatched_record.warnings

        docx_path = workspace / "drafting.docx"
        _write_minimal_docx(docx_path)
        docx_record = import_document(vault_root, docx_path)
        assert docx_record.status == ACCEPTED_STATUS
        assert docx_record.detected_file_type == "docx"

        png_path = workspace / "scan.png"
        png_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"scan image bytes")
        png_record = import_document(vault_root, png_path)
        assert png_record.status == ACCEPTED_STATUS
        assert png_record.detected_file_type == "png"

        unsupported_path = workspace / "notes.txt"
        unsupported_path.write_text("plain text should not enter F3 intake", encoding="utf-8")
        unsupported_record = import_document(vault_root, unsupported_path)
        assert unsupported_record.status == REJECTED_STATUS
        assert unsupported_record.detected_file_type == "unsupported"
        assert "unsupported_type" in unsupported_record.warnings

        corrupt_docx_path = workspace / "corrupt.docx"
        corrupt_docx_path.write_bytes(b"PK\x03\x04not actually a zip")
        corrupt_record = import_document(vault_root, corrupt_docx_path)
        assert corrupt_record.status == REJECTED_STATUS
        assert "corrupt_file" in corrupt_record.warnings

        empty_path = workspace / "empty.pdf"
        empty_path.write_bytes(b"")
        empty_record = import_document(vault_root, empty_path)
        assert empty_record.status == REJECTED_STATUS
        assert "empty_document" in empty_record.warnings

        records = list_intake_records(vault_root)
        assert len(records) == 8

    print("INTAKE VALIDATION PASS")


def _write_minimal_docx(path: Path) -> None:
    with zipfile.ZipFile(path, mode="w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="xml" ContentType="application/xml"/>'
                "</Types>"
            ),
        )
        archive.writestr(
            "word/document.xml",
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body><w:p><w:r><w:t>Draft pleading</w:t></w:r></w:p></w:body>"
                "</w:document>"
            ),
        )


if __name__ == "__main__":
    main()
