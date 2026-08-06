"""Validate that matter dates are storable, comparable and exportable.

Every date column in this product is ``TEXT NOT NULL`` and nothing validated
them, so a single database could hold ``2026-08-06``, ``2026-08-06T09:00:00Z``
and ``06/08/2026`` in one column. Two things follow from that, and both are
asserted here.

The first is that "what is due today" had no answer. There was no cross-matter
query at all, and had one been written it could not have compared three formats.

The second is worse, because it shipped. ``_ics_date_or_datetime`` stripped
hyphens without parsing, so a lodging whose due date read ``TBC`` emitted
``DTSTART:TBC``. That is not a bad event in a good file -- it is a malformed
file, and a calendar application rejects the whole thing. One clerk typing a
placeholder silently emptied every advocate's imported diary.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from starlette.testclient import TestClient  # noqa: E402

from search.core import initialize_search_store  # noqa: E402
from wakilios.api import create_app  # noqa: E402
from wakilios.core import (  # noqa: E402
    READ_ONLY_ROLE,
    WakiliOSError,
    _build_ics,
    _connect,
    _create_schema,
    _migrate_schema,
    initialize_firm_backend,
    normalize_matter_date,
)

# (input, canonical form). Day-first for the slashed form: that is the
# convention on every Kenyan court document, and month-first would silently
# transpose 06/08 into 8 June.
ACCEPTED = [
    ("", ""),
    ("2026-08-06", "2026-08-06"),
    ("  2026-08-06  ", "2026-08-06"),
    ("06/08/2026", "2026-08-06"),
    ("6/8/2026", "2026-08-06"),
    ("2026-08-06T09:00:00", "2026-08-06T09:00:00"),
    ("2026-08-06T09:00", "2026-08-06T09:00:00"),
    # 06:00 UTC is 09:00 in Nairobi, and must land on the same day.
    ("2026-08-06T06:00:00Z", "2026-08-06T09:00:00"),
    ("2026-08-06T09:00:00+03:00", "2026-08-06T09:00:00"),
    # 23:30 UTC is already tomorrow in Nairobi. Storing UTC would have put this
    # hearing in the wrong day's diary.
    ("2026-08-06T23:30:00Z", "2026-08-07T02:30:00"),
]

REJECTED = [
    "TBC",
    "next term",
    "2026-13-01",
    "32/01/2026",
    "08/2026",
    "2026-08-06T25:00:00",
]


def check_normaliser() -> None:
    for raw, expected in ACCEPTED:
        actual = normalize_matter_date(raw, field="due_date")
        assert actual == expected, f"{raw!r} -> {actual!r}, expected {expected!r}"

    for raw in REJECTED:
        try:
            normalize_matter_date(raw, field="due_date")
        except WakiliOSError as exc:
            # The message has to name the field and say what is accepted, or a
            # clerk sees "400" and has no way to fix their own typo.
            assert "due_date" in str(exc), exc
            assert "YYYY-MM-DD" in str(exc), exc
        else:
            raise AssertionError(f"{raw!r} was accepted as a date")


def check_ordering() -> None:
    """String order must be chronological, and a day range must catch both shapes.

    This is the property the whole storage format was chosen for. If it ever
    stops holding, every date query in the product is quietly wrong rather than
    loudly broken.
    """
    stored = [
        "2026-08-05",
        "2026-08-06",
        "2026-08-06T09:00:00",
        "2026-08-06T14:30:00",
        "2026-08-07",
        "2026-12-01",
    ]
    assert sorted(stored) == stored, "lexicographic order diverged from chronological order"

    day_start, day_end = "2026-08-06", "2026-08-07"
    on_the_day = [value for value in stored if day_start <= value < day_end]
    assert on_the_day == [
        "2026-08-06",
        "2026-08-06T09:00:00",
        "2026-08-06T14:30:00",
    ], on_the_day


def check_ics() -> None:
    events = [
        {"uid": "a1", "summary": "Mention", "date": "2026-08-06T09:00:00", "description": "Ct 3"},
        {"uid": "l1", "summary": "Lodging due", "date": "2026-08-07", "description": "REF/1"},
        # The value that used to destroy the file.
        {"uid": "x1", "summary": "Unknown", "date": "TBC", "description": ""},
        {
            "uid": "long",
            "summary": "A " + "very " * 40 + "long matter title that must be folded",
            "date": "2026-08-08",
            "description": "",
        },
    ]
    ics = _build_ics(events)

    assert "DTSTART;TZID=Africa/Nairobi:20260806T090000" in ics, ics
    assert "DTEND;TZID=Africa/Nairobi:20260806T100000" in ics, ics
    assert "DTSTART;VALUE=DATE:20260807" in ics, ics
    # All-day events end on the next day, exclusive -- how RFC 5545 spells
    # "occupies the whole of the 7th".
    assert "DTEND;VALUE=DATE:20260808" in ics, ics

    assert "TBC" not in ics, "an unparseable date reached the file and would break every event"
    assert ics.count("BEGIN:VEVENT") == 3, "the bad row should be skipped, the good rows kept"

    for line in ics.split("\r\n"):
        assert len(line.encode("utf-8")) <= 75, f"line exceeds the RFC 5545 limit: {line!r}"
    assert any(line.startswith(" ") for line in ics.split("\r\n")), (
        "the long title should have been folded onto continuation lines"
    )


def check_backfill() -> None:
    """A database written before this migration must survive it intact."""
    with tempfile.TemporaryDirectory() as temp_dir:
        legacy_root = Path(temp_dir) / "legacy"
        legacy_path = legacy_root / "vault.sqlite"
        initialize_search_store(legacy_root)
        with _connect(legacy_path) as connection:
            _create_schema(connection)
            connection.execute("PRAGMA user_version = 0")
            for index, value in enumerate(
                ["2026-08-06", "2026-08-06T09:00:00Z", "06/08/2026", "TBC"]
            ):
                connection.execute(
                    """
                    INSERT INTO lodgings (
                        lodging_id, matter_id, document_kind, party, due_date,
                        lodged_date, filing_status, linked_document_id,
                        filing_reference, created_at
                    ) VALUES (?, 'MTR-1', 'Plaint', '', ?, '', 'pending', '', '',
                              '2026-04-08T09:04:45Z')
                    """,
                    (f"LDG-{index}", value),
                )

        with _connect(legacy_path) as connection:
            _migrate_schema(connection)

        with _connect(legacy_path) as connection:
            rows = dict(connection.execute("SELECT lodging_id, due_date FROM lodgings").fetchall())
        assert len(rows) == 4, "the migration lost a row"
        assert rows["LDG-0"] == "2026-08-06"
        assert rows["LDG-1"] == "2026-08-06T12:00:00", rows["LDG-1"]
        assert rows["LDG-2"] == "2026-08-06", rows["LDG-2"]
        # Left exactly as the firm typed it. We would rather carry a value we
        # cannot parse than destroy a record we cannot recover.
        assert rows["LDG-3"] == "TBC", rows["LDG-3"]

        with _connect(legacy_path) as connection:
            reported = connection.execute(
                "SELECT COUNT(*) FROM wakilios_audit_events WHERE event_type = ?",
                ("date_backfill_unparsed",),
            ).fetchone()[0]
        assert reported >= 1, "an unparseable date was silently left without a record of it"


def check_upcoming() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "firm"
        backend = initialize_firm_backend(
            root,
            firm_name="Upcoming Firm",
            admin_username="admin",
            admin_password="admin-pass",
            vault_passphrase="upcoming vault passphrase",
        )
        token = backend.login("admin", "admin-pass").token

        matter = backend.create_litigation_matter(
            token,
            internal_reference="MTR-UP-1",
            client_name="Kiunga Holdings",
            parties="Kiunga v Republic",
            court="High Court",
            station="Meru",
            case_number="HCCC/E1/2026",
            practice_area="Commercial",
            responsible_advocate="A. Advocate",
            filing_status="filed",
            filing_date="2026-08-01",
        )
        matter_id = str(matter["matter_id"])

        backend.add_activity(
            token,
            matter_id,
            activity_type="Mention",
            title="Mention before the Deputy Registrar",
            starts_at="2026-08-06T09:00:00",
        )
        # Hidden from the calendar on purpose, so it must not appear.
        backend.add_activity(
            token,
            matter_id,
            activity_type="Internal",
            title="Internal file review",
            starts_at="2026-08-06T11:00:00",
            calendar_visible=False,
        )
        backend.add_lodging(
            token, matter_id, document_kind="Witness statement", due_date="06/08/2026"
        )
        backend.add_court_decision(
            token, matter_id, decision_type="Ruling", decision_date="2026-08-06"
        )
        backend.add_filing_record(
            token, matter_id, next_action="Serve the defence", next_action_date="2026-08-06"
        )
        # Outside the window.
        backend.add_lodging(token, matter_id, document_kind="Bundle", due_date="2026-09-01")

        entries = backend.upcoming_dates(token, start="2026-08-06", end="2026-08-07")
        kinds = sorted(entry["kind"] for entry in entries)
        assert kinds == ["decision", "hearing", "lodging_due", "next_action"], kinds
        assert all(entry["matter_reference"] == "MTR-UP-1" for entry in entries)

        hearing = next(entry for entry in entries if entry["kind"] == "hearing")
        assert hearing["time"] == "09:00", hearing
        lodging = next(entry for entry in entries if entry["kind"] == "lodging_due")
        # Written day-first, stored canonically, and found by an ISO range.
        assert lodging["time"] == "", lodging
        assert "Witness statement" in str(lodging["title"]), lodging

        assert [entry["date"] for entry in entries] == ["2026-08-06"] * 4

        empty = backend.upcoming_dates(token, start="2026-08-10", end="2026-08-11")
        assert empty == [], empty

        # A read-only seat must be able to see the diary: that is the point.
        backend.create_user(
            token,
            username="viewer",
            password="viewer-pass",
            role=READ_ONLY_ROLE,
            display_name="Viewer",
        )
        viewer_token = backend.login("viewer", "viewer-pass").token
        assert len(backend.upcoming_dates(viewer_token, start="2026-08-06", end="2026-08-07")) == 4

        # Polling must not fill the audit table.
        before = len(backend.audit_events(token))
        backend.upcoming_dates(token, start="2026-08-06", end="2026-08-07")
        backend.upcoming_dates(token, start="2026-08-06", end="2026-08-07")
        assert len(backend.audit_events(token)) == before, (
            "upcoming_dates wrote an audit row; it is polled on a timer and by every device sync"
        )


def check_route() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        app = create_app(
            root=Path(temp_dir) / "api",
            firm_name="Route Firm",
            admin_username="admin",
            admin_password="admin-pass",
            vault_passphrase="route vault passphrase",
        )
        client = TestClient(app)

        assert client.get("/calendar/upcoming?start=2026-08-06&end=2026-08-07").status_code == 401

        token = client.post(
            "/auth/login", json={"username": "admin", "password": "admin-pass"}
        ).json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/calendar/upcoming?start=2026-08-06&end=2026-08-07", headers=headers)
        assert response.status_code == 200, response.text
        assert response.json() == {"entries": []}

        # A date the range cannot mean should be refused, not silently empty.
        bad = client.get("/calendar/upcoming?start=TBC&end=2026-08-07", headers=headers)
        assert bad.status_code == 400, bad.text


def main() -> None:
    check_normaliser()
    check_ordering()
    check_ics()
    check_backfill()
    check_upcoming()
    check_route()
    print("CALENDAR DATE VALIDATION PASS")


if __name__ == "__main__":
    main()
