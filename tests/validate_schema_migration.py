"""Validate the firm database upgrade path.

``_create_schema`` is all ``CREATE TABLE IF NOT EXISTS``, so it is a no-op
against a database that already exists. Before ``_migrate_schema`` there was no
mechanism at all: a column added to an existing table reached new databases
only, and the first query touching it on an existing vault failed with
``no such column``.

Nothing in the repository tested an upgrade, so this covers the case that
matters -- an old database opened by a new build -- as well as the properties
migrations must hold: idempotence, and not disturbing existing rows.
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from search.core import initialize_search_store  # noqa: E402
from wakilios.core import (  # noqa: E402
    SCHEMA_VERSION,
    _connect,
    _create_schema,
    _migrate_schema,
    initialize_firm_backend,
)

# Columns each migration introduces, checked against a pre-migration database.
# ``documents`` belongs to the search store, which shares this database file.
MIGRATED_COLUMNS = {
    "fee_entries": ("prn",),
    "lodgings": ("actioning_status",),
    "documents": ("filing_role",),
}

# Tables each migration creates outright.
MIGRATED_TABLES = ("matter_filing_records",)


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}


def _user_version(connection: sqlite3.Connection) -> int:
    return int(connection.execute("PRAGMA user_version").fetchone()[0])


def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        legacy_root = Path(temp_dir) / "legacy"
        legacy_path = legacy_root / "vault.sqlite"

        # A database as an earlier release left it: baseline schema from both
        # owners of this file, no user_version, and a row already present in one
        # of the tables a migration touches.
        initialize_search_store(legacy_root)
        with _connect(legacy_path) as connection:
            _create_schema(connection)
            connection.execute("PRAGMA user_version = 0")
            connection.execute(
                """
                INSERT INTO fee_entries (
                    fee_id, matter_id, fee_type, amount, currency, paid_by,
                    paid_to, status, linked_activity_id, linked_lodging_id, created_at
                ) VALUES ('FEE-1', 'MTR-1', 'Filing fee', 4000.0, 'KES', 'client',
                          'court', 'paid', '', '', '2026-04-08T09:04:45')
                """
            )

        with _connect(legacy_path) as connection:
            assert _user_version(connection) == 0
            for table, columns in MIGRATED_COLUMNS.items():
                present = _columns(connection, table)
                for column in columns:
                    assert column not in present, (
                        f"{table}.{column} already exists before migration; "
                        f"this test can no longer prove the upgrade path works"
                    )

        # Opening it with the current build must upgrade it in place.
        with _connect(legacy_path) as connection:
            _migrate_schema(connection)

        with _connect(legacy_path) as connection:
            assert _user_version(connection) == SCHEMA_VERSION
            for table, columns in MIGRATED_COLUMNS.items():
                present = _columns(connection, table)
                for column in columns:
                    assert column in present, f"{table}.{column} missing after migration"
            for table in MIGRATED_TABLES:
                assert _columns(connection, table), f"{table} was not created by migration"

            row = connection.execute(
                "SELECT fee_type, amount, prn FROM fee_entries WHERE fee_id = 'FEE-1'"
            ).fetchone()
            assert row is not None, "migration dropped an existing row"
            assert row["fee_type"] == "Filing fee"
            assert row["amount"] == 4000.0
            assert row["prn"] == "", "new column should default to empty, not NULL"

        # Re-running must be a no-op, not an error.
        with _connect(legacy_path) as connection:
            _migrate_schema(connection)
            _migrate_schema(connection)
            assert _user_version(connection) == SCHEMA_VERSION
            assert connection.execute("SELECT COUNT(*) FROM fee_entries").fetchone()[0] == 1, (
                "re-running migrations changed the data"
            )

        # A brand new backend must arrive fully migrated.
        backend = initialize_firm_backend(
            Path(temp_dir) / "fresh",
            firm_name="Fresh Firm",
            admin_username="admin",
            admin_password="admin-pass",
            vault_passphrase="fresh vault passphrase",
        )
        with _connect(backend.database_path) as connection:
            assert _user_version(connection) == SCHEMA_VERSION
            for table, columns in MIGRATED_COLUMNS.items():
                present = _columns(connection, table)
                for column in columns:
                    assert column in present, f"fresh database is missing {table}.{column}"
            for table in MIGRATED_TABLES:
                assert _columns(connection, table), f"fresh database is missing {table}"

    print(f"SCHEMA MIGRATION VALIDATION PASS: upgraded v0 -> v{SCHEMA_VERSION}")


if __name__ == "__main__":
    main()
