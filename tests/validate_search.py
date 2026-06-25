"""Validate F5 matter, version, and FTS search behavior."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from search import (  # noqa: E402
    DRAFT_STATUS,
    FILED_STATUS,
    IMPORTED_STATUS,
    add_document_version,
    create_document,
    create_matter,
    initialize_search_store,
    rebuild_search_index,
    search_documents,
)
from vault import initialize_vault  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary_dir:
        vault_root = Path(temporary_dir) / "vault"
        vault_session = initialize_vault(vault_root, "search validator recovery key")
        initialize_search_store(vault_root)

        nairobi_matter = create_matter(
            vault_root,
            internal_reference="WAK-2026-001",
            client_name="Amani Traders Ltd",
            parties="Amani Traders Ltd v Umoja Supplies",
            court="High Court",
            station="Nairobi",
            case_number="HCOMM E001 of 2026",
            practice_area="Commercial",
            responsible_advocate="M. Mutugi",
        )
        kisumu_matter = create_matter(
            vault_root,
            internal_reference="WAK-2026-002",
            client_name="Lake Basin Co",
            parties="Lake Basin Co v County Office",
            court="ELC",
            station="Kisumu",
            case_number="ELC E002 of 2026",
            practice_area="Land",
            responsible_advocate="M. Mutugi",
        )

        stored_pleading = vault_session.write_object(
            b"draft pleading bytes",
            original_name="draft-pleading.pdf",
            content_type="application/pdf",
        )
        pleading = create_document(
            vault_root,
            matter_id=nairobi_matter.matter_id,
            title="Draft Plaint",
            document_type="Pleading",
            lifecycle_status=IMPORTED_STATUS,
        )
        first_version = add_document_version(
            vault_root,
            document_id=pleading.document_id,
            object_id=stored_pleading.object_id,
            source_sha256=stored_pleading.sha256,
            extracted_text="The applicant seeks an injunction over supplied goods in Nairobi.",
            lifecycle_status=DRAFT_STATUS,
        )
        second_version = add_document_version(
            vault_root,
            document_id=pleading.document_id,
            object_id=stored_pleading.object_id,
            source_sha256=stored_pleading.sha256,
            extracted_text="Filed plaint seeking injunction and commercial damages.",
            lifecycle_status=FILED_STATUS,
        )
        assert first_version.version_number == 1
        assert second_version.version_number == 2

        stored_land_doc = vault_session.write_object(
            b"land document bytes",
            original_name="land-affidavit.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        land_document = create_document(
            vault_root,
            matter_id=kisumu_matter.matter_id,
            title="Land Affidavit",
            document_type="Affidavit",
        )
        add_document_version(
            vault_root,
            document_id=land_document.document_id,
            object_id=stored_land_doc.object_id,
            source_sha256=stored_land_doc.sha256,
            extracted_text="Kisumu land parcel occupation and boundary dispute affidavit.",
            lifecycle_status=DRAFT_STATUS,
        )

        global_results = search_documents(vault_root, "injunction")
        assert len(global_results) == 2
        assert {result.document_id for result in global_results} == {pleading.document_id}

        nairobi_results = search_documents(
            vault_root,
            "injunction",
            matter_id=nairobi_matter.matter_id,
        )
        assert len(nairobi_results) == 2
        assert all(result.matter_id == nairobi_matter.matter_id for result in nairobi_results)
        assert any(result.lifecycle_status == FILED_STATUS for result in nairobi_results)

        kisumu_results = search_documents(
            vault_root,
            "injunction",
            matter_id=kisumu_matter.matter_id,
        )
        assert kisumu_results == []

        land_results = search_documents(vault_root, "boundary")
        assert len(land_results) == 1
        assert land_results[0].matter_id == kisumu_matter.matter_id

        _clear_search_index(vault_root)
        assert search_documents(vault_root, "boundary") == []
        rebuild_search_index(vault_root)
        assert len(search_documents(vault_root, "boundary")) == 1

    print("SEARCH VALIDATION PASS")


def _clear_search_index(vault_root: Path) -> None:
    connection = sqlite3.connect(vault_root / "vault.sqlite")
    try:
        connection.execute("DELETE FROM search_index")
        connection.commit()
    finally:
        connection.close()


if __name__ == "__main__":
    main()
