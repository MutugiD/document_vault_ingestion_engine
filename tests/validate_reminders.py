"""Validate reminders between colleagues.

This is the first user-to-user surface in a product that has only ever been one
user per session, so it is the first place a permission question has a real
answer rather than a conventional one. Three of those answers are load-bearing
and are asserted here rather than left to review:

* **A clerk may send.** The person who spots a filing deadline is usually not
  the advocate, and restricting sending to advocates would remove the main use
  of the feature while looking like good practice.
* **An administrator may not read someone else's inbox.** In a law firm that is
  a confidentiality problem, and there is no consent model that would make it
  defensible, so the capability does not exist at all -- not for admin, not for
  anyone.
* **Only the recipient can acknowledge.** Otherwise "acknowledged" means
  nothing.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from starlette.testclient import TestClient  # noqa: E402

from wakilios.api import create_app  # noqa: E402
from wakilios.core import (  # noqa: E402
    ACCOUNTS_ROLE,
    ADVOCATE_ROLE,
    CLERK_ROLE,
    READ_ONLY_ROLE,
    REMINDER_DAILY_LIMIT,
    REMINDER_UNREAD,
    PermissionDeniedError,
    WakiliOSError,
    initialize_firm_backend,
)


def build_firm(root: Path):
    backend = initialize_firm_backend(
        root,
        firm_name="Reminder Firm",
        admin_username="admin",
        admin_password="admin-pass",
        vault_passphrase="reminder vault passphrase",
        max_seats=8,
    )
    admin = backend.login("admin", "admin-pass").token
    people = {}
    for username, role in (
        ("advocate", ADVOCATE_ROLE),
        ("clerk", CLERK_ROLE),
        ("accounts", ACCOUNTS_ROLE),
        ("viewer", READ_ONLY_ROLE),
    ):
        created = backend.create_user(
            admin,
            username=username,
            password=f"{username}-pass",
            role=role,
            display_name=username.title(),
        )
        people[username] = {
            "user_id": str(created["user_id"]),
            "token": backend.login(username, f"{username}-pass").token,
        }
    return backend, admin, people


def check_roles_and_confidentiality() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        backend, admin_token, people = build_firm(Path(temp_dir) / "firm")
        advocate, clerk, accounts, viewer = (
            people["advocate"],
            people["clerk"],
            people["accounts"],
            people["viewer"],
        )

        users = backend.list_firm_users(viewer["token"])
        assert len(users) == 5, users
        # A roster is now visible to every seat. That is a deliberate exposure,
        # but password material must never travel with it.
        for user in users:
            assert "password_hash" not in user and "password_salt_b64" not in user, user

        # A clerk noticing a deadline is exactly who needs to prompt an advocate.
        sent = backend.send_reminder(
            clerk["token"],
            recipient_ids=[advocate["user_id"]],
            subject="Defence due Friday",
            body="The response has not been lodged.",
            due_date="06/08/2026",
            priority="urgent",
        )
        assert len(sent) == 1, sent
        assert sent[0]["state"] == REMINDER_UNREAD, sent
        assert sent[0]["due_date"] == "2026-08-06", "the due date was not normalised"

        # Accounts too: an unpaid fee is a reason to prompt someone.
        backend.send_reminder(
            accounts["token"],
            recipient_ids=[advocate["user_id"]],
            subject="Filing fee unreconciled",
        )

        # A read-only seat may not.
        try:
            backend.send_reminder(
                viewer["token"], recipient_ids=[advocate["user_id"]], subject="Nope"
            )
        except PermissionDeniedError:
            pass
        else:
            raise AssertionError("a read-only seat sent a reminder")

        inbox = backend.list_reminders(advocate["token"])
        assert len(inbox) == 2, inbox
        assert {str(item["subject"]) for item in inbox} == {
            "Defence due Friday",
            "Filing fee unreconciled",
        }
        assert inbox[0]["sender_name"], "the recipient must be able to see who sent it"

        # Nobody else's inbox is reachable -- including the administrator's view
        # of a colleague's. There is no parameter for it, and the caller is
        # always the recipient.
        assert backend.list_reminders(clerk["token"]) == []
        assert backend.list_reminders(admin_token) == []

        # The sender can see whether it was acted on.
        outbox = backend.list_sent_reminders(clerk["token"])
        assert len(outbox) == 1 and outbox[0]["recipient_name"] == "Advocate", outbox

        # Explicitly the clerk's, not inbox[0]: the inbox is newest-first, and
        # this assertion is about who may acknowledge, not about ordering.
        reminder_id = str(
            next(item for item in inbox if item["subject"] == "Defence due Friday")["reminder_id"]
        )
        try:
            backend.acknowledge_reminder(clerk["token"], reminder_id)
        except PermissionDeniedError:
            pass
        else:
            raise AssertionError("a non-recipient acknowledged a reminder")

        acknowledged = backend.acknowledge_reminder(advocate["token"], reminder_id)
        assert acknowledged["state"] == "acknowledged", acknowledged
        assert acknowledged["acknowledged_at"], "acknowledgement recorded no time"
        assert len(backend.list_reminders(advocate["token"], state="unread")) == 1

        # ...and the sender now sees it.
        assert backend.list_sent_reminders(clerk["token"])[0]["state"] == "acknowledged"


def check_validation_and_limits() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        backend, _admin, people = build_firm(Path(temp_dir) / "firm")
        clerk, advocate = people["clerk"], people["advocate"]

        for kwargs, reason in (
            ({"recipient_ids": [advocate["user_id"]], "subject": "  "}, "empty subject"),
            ({"recipient_ids": [], "subject": "No one"}, "no recipients"),
            ({"recipient_ids": ["not-a-user"], "subject": "Ghost"}, "unknown recipient"),
            (
                {
                    "recipient_ids": [advocate["user_id"]],
                    "subject": "S",
                    "priority": "screaming",
                },
                "unsupported priority",
            ),
            (
                {"recipient_ids": [advocate["user_id"]], "subject": "S", "due_date": "next term"},
                "unparseable due date",
            ),
        ):
            try:
                backend.send_reminder(clerk["token"], **kwargs)
            except WakiliOSError:
                pass
            else:
                raise AssertionError(f"{reason} was accepted")

        # One row per recipient, so read state is per person by construction
        # rather than by convention.
        broadcast = backend.send_reminder(
            clerk["token"],
            recipient_ids=[advocate["user_id"], people["accounts"]["user_id"]],
            subject="Court is closed on Monday",
        )
        assert len(broadcast) == 2, broadcast
        assert len({row["reminder_id"] for row in broadcast}) == 2

        # A stuck button or a looping integration must not fill every inbox
        # before anyone notices.
        for index in range(REMINDER_DAILY_LIMIT):
            try:
                backend.send_reminder(
                    clerk["token"], recipient_ids=[advocate["user_id"]], subject=f"Note {index}"
                )
            except WakiliOSError as exc:
                assert "limit" in str(exc).lower(), exc
                break
        else:
            raise AssertionError("the daily send limit never applied")


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

        assert client.get("/reminders").status_code == 401
        assert client.post(
            "/reminders", json={"recipient_ids": [], "subject": "x"}
        ).status_code == (401)

        advocate = client.post(
            "/users",
            json={
                "username": "advocate",
                "password": "advocate-pass",
                "role": "advocate",
                "display_name": "Advocate",
            },
            headers=admin_headers,
        ).json()
        advocate_token = client.post(
            "/auth/login", json={"username": "advocate", "password": "advocate-pass"}
        ).json()["token"]
        advocate_headers = {"Authorization": f"Bearer {advocate_token}"}

        roster = client.get("/firm/users", headers=advocate_headers)
        assert roster.status_code == 200, roster.text
        assert len(roster.json()["users"]) == 2

        response = client.post(
            "/reminders",
            json={
                "recipient_ids": [advocate["user_id"]],
                "subject": "Mention on Thursday",
                "due_date": "2026-08-06",
            },
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text
        reminder_id = response.json()["reminders"][0]["reminder_id"]

        inbox = client.get("/reminders", headers=advocate_headers).json()["reminders"]
        assert len(inbox) == 1, inbox
        # The administrator sent it and still cannot read the recipient's inbox.
        assert client.get("/reminders", headers=admin_headers).json()["reminders"] == []

        acknowledged = client.post(
            f"/reminders/{reminder_id}/acknowledge",
            json={"state": "acknowledged"},
            headers=advocate_headers,
        )
        assert acknowledged.status_code == 200, acknowledged.text
        assert acknowledged.json()["state"] == "acknowledged"

        # The sender sees the acknowledgement on their own outbox.
        sent = client.get("/reminders/sent", headers=admin_headers).json()["reminders"]
        assert len(sent) == 1 and sent[0]["state"] == "acknowledged", sent

        refused = client.post(
            f"/reminders/{reminder_id}/acknowledge",
            json={"state": "acknowledged"},
            headers=admin_headers,
        )
        assert refused.status_code == 403, refused.text


def main() -> None:
    check_roles_and_confidentiality()
    check_validation_and_limits()
    check_routes()
    print("REMINDERS VALIDATION PASS")


if __name__ == "__main__":
    main()
