"""Validate pairing a phone, what it can reach, and taking it away again.

A device token is the only long-lived credential in this product. A session
token expires in ninety minutes and needs no withdrawal path; a phone that syncs
weekly cannot re-authenticate that often, so its token lasts months. Two things
follow, and both are asserted here rather than assumed.

**It must be revocable.** A long-lived credential with no way to withdraw it is
an unbounded one, and the phone is the piece of hardware most likely to be lost
with the credential still on it. Revocation has to take effect on the next
request, not at expiry.

**It must not carry the whole person.** The advocate can create matters and, if
an administrator, read the audit log. Their phone must not. ``allow_device`` is
opt-in on ``require_authenticated``, so a capability added later is denied to
devices until someone decides otherwise -- which is the safe way for that
decision to be forgotten.

There is also a size assertion on the snapshot. It excludes documents and
extracted text today; the assertion is what stops that being eroded one field at
a time by someone who only needed "just this one thing" on the phone.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from starlette.testclient import TestClient  # noqa: E402

from wakilios.api import create_app  # noqa: E402
from wakilios.core import (  # noqa: E402
    ADVOCATE_ROLE,
    DEVICE_TOKEN_TYPE,
    PAIRING_CODE_TTL_MINUTES,
    AuthenticationError,
    PermissionDeniedError,
    _connect,
    _datetime_to_text,
    _utc_now,
    initialize_firm_backend,
)
from wakilios.core import timedelta as _timedelta  # noqa: E402


def build_firm(root: Path):
    backend = initialize_firm_backend(
        root,
        firm_name="Device Firm",
        admin_username="admin",
        admin_password="admin-pass",
        vault_passphrase="device vault passphrase",
        max_seats=5,
    )
    admin = backend.login("admin", "admin-pass").token
    backend.create_user(
        admin,
        username="advocate",
        password="advocate-pass",
        role=ADVOCATE_ROLE,
        display_name="Senior Advocate",
    )
    advocate = backend.login("advocate", "advocate-pass").token
    return backend, admin, advocate


def check_pairing_lifecycle() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        backend, _admin, advocate = build_firm(Path(temp_dir) / "firm")

        offer = backend.create_pairing_code(advocate)
        code = str(offer["pairing_code"])
        assert len(code) == 8, offer
        assert offer["expires_in_minutes"] == PAIRING_CODE_TTL_MINUTES
        # Read off a screen and typed into a phone, so no character may be
        # confusable with another.
        assert not set(code) & set("IL01O"), f"ambiguous characters in {code}"

        claimed = backend.claim_pairing_code(code, device_name="Senior Advocate's phone")
        assert claimed["device_token"], claimed
        assert claimed["username"] == "advocate", claimed

        # Single use.
        try:
            backend.claim_pairing_code(code, device_name="A second phone")
        except AuthenticationError as exc:
            assert "already been used" in str(exc), exc
        else:
            raise AssertionError("a pairing code was redeemed twice")

        try:
            backend.claim_pairing_code("ZZZZZZZZ", device_name="Unknown")
        except AuthenticationError:
            pass
        else:
            raise AssertionError("an unknown pairing code was accepted")

        # An expired code is refused. Written directly rather than waited for.
        expired = backend.create_pairing_code(advocate)
        with _connect(backend.database_path) as connection:
            connection.execute(
                "UPDATE device_pairings SET expires_at = ? WHERE pairing_code = ?",
                (_datetime_to_text(_utc_now() - _timedelta(minutes=1)), expired["pairing_code"]),
            )
        try:
            backend.claim_pairing_code(str(expired["pairing_code"]), device_name="Late phone")
        except AuthenticationError as exc:
            assert "expired" in str(exc), exc
        else:
            raise AssertionError("an expired pairing code was accepted")


def check_device_capabilities() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        backend, admin, advocate = build_firm(Path(temp_dir) / "firm")
        device = str(
            backend.claim_pairing_code(
                str(backend.create_pairing_code(advocate)["pairing_code"]),
                device_name="Field phone",
            )["device_token"]
        )

        matter = backend.create_litigation_matter(
            advocate,
            internal_reference="MTR-DEV-1",
            client_name="Kiunga Holdings",
            parties="Kiunga v Republic",
            court="High Court",
            station="Meru",
            case_number="HCCC/E4/2026",
            practice_area="Commercial",
            responsible_advocate="Senior Advocate",
            filing_status="filed",
            filing_date="2026-08-01",
        )
        backend.add_activity(
            advocate,
            str(matter["matter_id"]),
            activity_type="Mention",
            title="Mention before the Deputy Registrar",
            starts_at="2026-08-06T09:00:00",
        )

        # Permitted: the diary, the snapshot, the roster, and reminders both
        # ways. That is the whole of what a phone out of the office needs.
        assert backend.upcoming_dates(device, start="2026-08-06", end="2026-08-07")
        snapshot = backend.build_device_snapshot(device)
        assert snapshot["matters"], snapshot
        assert backend.list_firm_users(device)
        assert backend.list_reminders(device) == []

        admin_id = next(
            person["user_id"]
            for person in backend.list_firm_users(advocate)
            if person["username"] == "admin"
        )
        sent = backend.send_reminder(
            device, recipient_ids=[str(admin_id)], subject="Adjourn Thursday's mention"
        )
        assert len(sent) == 1, sent

        # Refused: everything else. A phone left in a taxi must not be able to
        # create a matter, upload a document or read the audit log.
        for description, call in (
            (
                "create a matter",
                lambda: backend.create_litigation_matter(
                    device,
                    internal_reference="MTR-DEV-2",
                    client_name="X",
                    parties="X v Y",
                    court="High Court",
                    station="Meru",
                    case_number="HCCC/E5/2026",
                    practice_area="Civil",
                    responsible_advocate="Senior Advocate",
                    filing_status="draft",
                    filing_date="2026-08-01",
                ),
            ),
            (
                "read a matter workspace",
                lambda: backend.workspace(device, str(matter["matter_id"])),
            ),
            (
                "add an activity",
                lambda: backend.add_activity(
                    device,
                    str(matter["matter_id"]),
                    activity_type="Mention",
                    title="Sneaked in",
                    starts_at="2026-08-07",
                ),
            ),
            ("pair another device", lambda: backend.create_pairing_code(device)),
        ):
            try:
                call()
            except PermissionDeniedError:
                pass
            else:
                raise AssertionError(f"a paired device was able to {description}")

        # The audit log needs an administrator's own device to prove anything.
        # An advocate's phone failing on /audit proves only that advocates
        # cannot read it, which was already true and says nothing about
        # devices. Pair the administrator's phone and check the restriction
        # holds for someone who *does* have the role.
        admin_device = str(
            backend.claim_pairing_code(
                str(backend.create_pairing_code(admin)["pairing_code"]),
                device_name="Administrator's phone",
            )["device_token"]
        )
        try:
            backend.audit_events(admin_device)
        except PermissionDeniedError:
            pass
        else:
            raise AssertionError("an administrator's phone could read the firm audit log")

        # ...while the same person on a desktop seat is unaffected.
        assert backend.audit_events(admin), "an admin session must still read the audit log"


def check_revocation() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        backend, admin, advocate = build_firm(Path(temp_dir) / "firm")
        claimed = backend.claim_pairing_code(
            str(backend.create_pairing_code(advocate)["pairing_code"]),
            device_name="Lost phone",
        )
        device = str(claimed["device_token"])
        device_id = str(claimed["device_id"])

        assert backend.build_device_snapshot(device)["matters"] == []

        devices = backend.list_paired_devices(advocate)
        assert len(devices) == 1 and devices[0]["device_name"] == "Lost phone", devices
        assert devices[0]["last_seen_at"], "a device that has synced should record when"

        backend.revoke_device(advocate, device_id)

        # Immediately, not at expiry. That is the whole point.
        try:
            backend.build_device_snapshot(device)
        except AuthenticationError as exc:
            assert "unpaired" in str(exc), exc
        else:
            raise AssertionError("a revoked device could still sync")

        assert backend.list_paired_devices(advocate)[0]["revoked"] is True

        # An administrator can cut off a stolen phone they do not own. Unlike
        # reading a colleague's reminders, this is a security action with no
        # confidentiality cost, and a firm whose administrator cannot do it is
        # worse off.
        second = backend.claim_pairing_code(
            str(backend.create_pairing_code(advocate)["pairing_code"]), device_name="Second phone"
        )
        backend.revoke_device(admin, str(second["device_id"]))
        try:
            backend.build_device_snapshot(str(second["device_token"]))
        except AuthenticationError:
            pass
        else:
            raise AssertionError("an administrator could not revoke a device")


def check_snapshot_contents_and_size() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        backend, _admin, advocate = build_firm(Path(temp_dir) / "firm")
        for index in range(12):
            matter = backend.create_litigation_matter(
                advocate,
                internal_reference=f"MTR-S-{index}",
                client_name=f"Client {index}",
                parties=f"Client {index} v Respondent",
                court="High Court",
                station="Meru",
                case_number=f"HCCC/E{index}/2026",
                practice_area="Commercial",
                responsible_advocate="Senior Advocate",
                filing_status="filed",
                filing_date="2026-08-01",
                summary="A very long summary. " * 80,
            )
            backend.add_lodging(
                advocate,
                str(matter["matter_id"]),
                document_kind="Witness statement",
                due_date="2026-08-20",
            )

        device = str(
            backend.claim_pairing_code(
                str(backend.create_pairing_code(advocate)["pairing_code"]),
                device_name="Sizing phone",
            )["device_token"]
        )
        snapshot = backend.build_device_snapshot(device)

        assert len(snapshot["matters"]) == 12, len(snapshot["matters"])
        assert snapshot["calendar"], "the diary must reach the phone"
        assert snapshot["complete"] is True
        assert snapshot["users"], "the phone needs a roster to address a reminder"
        assert snapshot["user"]["username"] == "advocate"

        serialised = json.dumps(snapshot)
        # Documents and extracted text are excluded, and this is what keeps it
        # that way: adding either would fail here long before it reached a phone.
        for forbidden in ("extracted_text", "object_id", "document_id", "content"):
            assert forbidden not in serialised, f"the snapshot carries {forbidden}"
        for matter_row in snapshot["matters"]:
            assert len(str(matter_row["summary"])) <= 500, matter_row["summary"][:80]
        assert len(serialised) < 512_000, (
            f"snapshot is {len(serialised) // 1024} KiB for 12 matters; "
            f"something document-sized has been added to it"
        )

        # since returns appends only, which is a real limit and named as one.
        cutoff = _datetime_to_text(_utc_now())
        later = backend.build_device_snapshot(device, since=cutoff)
        assert later["matters"] == [], later["matters"]
        assert later["complete"] is False


def check_routes() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        app = create_app(
            root=Path(temp_dir) / "api",
            firm_name="Route Firm",
            admin_username="admin",
            admin_password="admin-pass",
            vault_passphrase="route vault passphrase",
            max_seats=5,
        )
        client = TestClient(app)
        admin = client.post(
            "/auth/login", json={"username": "admin", "password": "admin-pass"}
        ).json()["token"]
        admin_headers = {"Authorization": f"Bearer {admin}"}

        assert client.post("/devices/pairing").status_code == 401
        assert client.get("/sync/snapshot").status_code == 401

        code = client.post("/devices/pairing", headers=admin_headers).json()["pairing_code"]

        # Claiming carries no Authorization header at all: the short-lived code
        # is the credential.
        claimed = client.post(
            "/devices/claim", json={"pairing_code": code, "device_name": "Test phone"}
        )
        assert claimed.status_code == 200, claimed.text
        device_token = claimed.json()["device_token"]
        device_headers = {"Authorization": f"Bearer {device_token}"}

        snapshot = client.get("/sync/snapshot", headers=device_headers)
        assert snapshot.status_code == 200, snapshot.text
        assert snapshot.json()["schema_version"], snapshot.json()

        # 403 over the wire, not merely in-process.
        refused = client.post(
            "/matters",
            json={
                "internal_reference": "X",
                "client_name": "X",
                "parties": "X",
                "court": "High Court",
                "station": "Meru",
                "case_number": "X",
                "practice_area": "Civil",
                "responsible_advocate": "X",
                "filing_status": "draft",
                "filing_date": "2026-08-01",
            },
            headers=device_headers,
        )
        assert refused.status_code == 403, refused.text
        assert client.get("/audit", headers=device_headers).status_code == 403

        devices = client.get("/devices", headers=admin_headers).json()["devices"]
        assert len(devices) == 1, devices
        revoked = client.delete(f"/devices/{devices[0]['device_id']}", headers=admin_headers)
        assert revoked.status_code == 200, revoked.text
        assert client.get("/sync/snapshot", headers=device_headers).status_code == 401


def main() -> None:
    check_pairing_lifecycle()
    check_device_capabilities()
    check_revocation()
    check_snapshot_contents_and_size()
    check_routes()
    assert DEVICE_TOKEN_TYPE == "device"
    print("DEVICE SYNC VALIDATION PASS")


if __name__ == "__main__":
    main()
