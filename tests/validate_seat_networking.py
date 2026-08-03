"""Validate one-user and five-seat firm networking through the HTTP boundary."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from starlette.testclient import TestClient  # noqa: E402

from wakilios.api import create_app  # noqa: E402

MATTER = {
    "internal_reference": "NET-001",
    "client_name": "Network Test Client",
    "parties": "Network Test Client v Respondent",
    "court": "High Court",
    "station": "Nairobi",
    "case_number": "HCCC E005 of 2026",
    "practice_area": "Commercial",
    "responsible_advocate": "Seat One",
    "filing_status": "filed",
    "filing_date": "2026-07-22",
    "summary": "Shared matter visibility test.",
}


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="wakilios-seat-network-") as temporary_dir:
        root = Path(temporary_dir)

        # A one-user firm can run the same HTTP service with a single allocated seat.
        solo_app = create_app(
            root=root / "solo",
            firm_name="Solo Firm",
            admin_username="admin",
            admin_password="admin-pass",
            vault_passphrase="solo-passphrase",
            max_seats=1,
        )
        solo = TestClient(solo_app)
        assert solo.get("/health").json()["status"] == "ok"
        solo_admin = _login(solo, "admin", "admin-pass")
        solo_rejected = solo.post(
            "/users",
            json={
                "username": "second",
                "password": "second-pass",
                "role": "advocate",
                "display_name": "Second User",
            },
            headers=_auth(solo_admin),
        )
        assert solo_rejected.status_code == 409

        # A five-laptop firm shares one server-side vault and database.
        firm_app = create_app(
            root=root / "five-seat-firm",
            firm_name="Five Seat Firm",
            admin_username="admin",
            admin_password="admin-pass",
            vault_passphrase="firm-passphrase",
            max_seats=5,
        )
        firm = TestClient(firm_app)
        admin = _login(firm, "admin", "admin-pass")
        users = [("admin", admin)]
        for index in range(1, 5):
            username = f"seat{index}"
            response = firm.post(
                "/users",
                json={
                    "username": username,
                    "password": f"{username}-pass",
                    "role": "advocate" if index == 1 else "clerk",
                    "display_name": f"Seat {index}",
                },
                headers=_auth(admin),
            )
            assert response.status_code == 200, response.text
            users.append((username, _login(firm, username, f"{username}-pass")))

        sixth = firm.post(
            "/users",
            json={
                "username": "seat6",
                "password": "seat6-pass",
                "role": "read_only",
                "display_name": "Seat 6",
            },
            headers=_auth(admin),
        )
        assert sixth.status_code == 409

        created = firm.post("/matters", json=MATTER, headers=_auth(users[1][1]))
        assert created.status_code == 200, created.text
        matter_id = created.json()["matter_id"]

        for username, token in users:
            listed = firm.get("/matters", headers=_auth(token))
            assert listed.status_code == 200, (username, listed.text)
            assert any(item["matter_id"] == matter_id for item in listed.json()["matters"])

        uploaded = firm.post(
            f"/matters/{matter_id}/documents",
            files={
                "file": ("filing-receipt.txt", b"Kenya Judiciary receipt NET-001", "text/plain")
            },
            data={"title": "Filing receipt", "document_type": "receipt"},
            headers=_auth(users[1][1]),
        )
        assert uploaded.status_code == 200, uploaded.text

        readonly_user = firm.post(
            "/users",
            json={
                "username": "reader",
                "password": "reader-pass",
                "role": "read_only",
                "display_name": "Read Only",
            },
            headers=_auth(admin),
        )
        assert readonly_user.status_code == 409

        print("SEAT NETWORKING VALIDATION PASS")
        print("solo_seat_limit=1; five_seat_shared_matter=True; sixth_seat_rejected=True")


def _login(client: TestClient, username: str, password: str) -> str:
    response = client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return str(response.json()["token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


if __name__ == "__main__":
    main()
