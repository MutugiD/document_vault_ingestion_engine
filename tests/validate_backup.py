"""Validate F6 encrypted backup and restore behavior."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backup import (  # noqa: E402
    InvalidBackupKeyError,
    create_local_backup,
    read_backup_manifest,
    restore_backup_package,
)
from search import create_document, create_matter, initialize_search_store  # noqa: E402
from vault import initialize_vault, open_vault  # noqa: E402


def main() -> None:
    recovery_key = "backup validator recovery key"
    installation_id = "install-backup-validator"
    secret_text = b"Confidential affidavit backup payload must stay encrypted."

    with tempfile.TemporaryDirectory() as temporary_dir:
        workspace = Path(temporary_dir)
        vault_root = workspace / "vault"
        backup_path = workspace / "backups" / "snapshot.wakilibak"
        restore_root = workspace / "restore"

        vault_session = initialize_vault(vault_root, recovery_key)
        stored_object = vault_session.write_object(
            secret_text,
            original_name="affidavit.pdf",
            content_type="application/pdf",
            actor="backup-validator",
        )
        initialize_search_store(vault_root)
        matter = create_matter(
            vault_root,
            internal_reference="BACK-001",
            client_name="Backup Client",
            parties="Backup Client v Restore Respondent",
            court="High Court",
            station="Nairobi",
            case_number="HCOMM BACK 001",
            practice_area="Commercial",
            responsible_advocate="M. Mutugi",
        )
        create_document(
            vault_root,
            matter_id=matter.matter_id,
            title="Backup Affidavit",
            document_type="Affidavit",
        )

        package = create_local_backup(
            vault_root,
            backup_path,
            recovery_key=recovery_key,
            installation_id=installation_id,
        )
        assert package.path.exists()
        assert package.manifest.installation_id == installation_id
        assert package.manifest.file_count >= 2
        assert package.manifest.package_hash
        assert package.manifest.package_size_bytes == backup_path.stat().st_size

        package_bytes = backup_path.read_bytes()
        assert secret_text not in package_bytes
        assert b"Backup Client" not in package_bytes
        assert b"HCOMM BACK 001" not in package_bytes

        manifest = read_backup_manifest(backup_path)
        assert manifest.snapshot_id == package.manifest.snapshot_id
        assert manifest.package_hash == package.manifest.package_hash

        try:
            restore_backup_package(
                backup_path,
                restore_root,
                recovery_key="wrong recovery key",
            )
        except InvalidBackupKeyError:
            pass
        else:
            raise AssertionError("wrong recovery key unexpectedly restored the backup")

        report = restore_backup_package(
            backup_path,
            restore_root,
            recovery_key=recovery_key,
        )
        assert report.verified
        assert (report.restored_path / "vault.sqlite").exists()
        assert (report.restored_path / "restore-report.json").exists()

        restored_session = open_vault(report.restored_path, recovery_key)
        assert restored_session.read_object(stored_object.object_id) == secret_text

    print("BACKUP VALIDATION PASS")


if __name__ == "__main__":
    main()
