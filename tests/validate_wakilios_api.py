"""Validate WakiliOS FastAPI HTTP endpoints via TestClient."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from starlette.testclient import TestClient  # noqa: E402

from wakilios.api import create_app  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary_dir:
        root = Path(temporary_dir)
        app = create_app(
            root=root,
            firm_name="Test Firm",
            admin_username="admin",
            admin_password="admin-pass",
            vault_passphrase="test vault passphrase",
            max_seats=5,
        )
        client = TestClient(app)

        # Health
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["product"] == "WakiliOS"

        # Auth: bad login
        resp = client.post("/auth/login", json={"username": "admin", "password": "wrong"})
        assert resp.status_code == 401

        # Auth: valid login
        resp = client.post("/auth/login", json={"username": "admin", "password": "admin-pass"})
        assert resp.status_code == 200
        token = resp.json()["token"]

        # Create user
        resp = client.post(
            "/users",
            json={
                "username": "advocate1",
                "password": "pass123",
                "role": "advocate",
                "display_name": "Advocate One",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "advocate"

        # Login as advocate
        resp = client.post("/auth/login", json={"username": "advocate1", "password": "pass123"})
        assert resp.status_code == 200
        advocate_token = resp.json()["token"]

        # List matters (empty initially)
        resp = client.get("/matters", headers={"Authorization": f"Bearer {advocate_token}"})
        assert resp.status_code == 200
        assert isinstance(resp.json()["matters"], list)

        # Create matter
        resp = client.post(
            "/matters",
            json={
                "internal_reference": "API-001",
                "client_name": "Test Client",
                "parties": "Test Client v Respondent",
                "court": "High Court",
                "station": "Nairobi",
                "case_number": "HCCC E002 of 2026",
                "practice_area": "Commercial",
                "responsible_advocate": "Advocate One",
                "filing_status": "filed",
                "filing_date": "2026-07-16",
            },
            headers={"Authorization": f"Bearer {advocate_token}"},
        )
        assert resp.status_code == 200
        matter_id = resp.json()["matter_id"]

        # Get matter
        resp = client.get(
            f"/matters/{matter_id}", headers={"Authorization": f"Bearer {advocate_token}"}
        )
        assert resp.status_code == 200
        assert resp.json()["internal_reference"] == "API-001"

        # Update summary
        resp = client.put(
            f"/matters/{matter_id}/summary",
            json={"summary": "Updated via API"},
            headers={"Authorization": f"Bearer {advocate_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["summary"] == "Updated via API"

        # Add party
        resp = client.post(
            f"/matters/{matter_id}/parties",
            json={
                "name": "Test Client",
                "party_role": "Claimant",
                "representative": "Advocate One",
            },
            headers={"Authorization": f"Bearer {advocate_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Test Client"

        # Add activity
        resp = client.post(
            f"/matters/{matter_id}/activities",
            json={
                "activity_type": "mention",
                "title": "Directions hearing",
                "starts_at": "2026-08-01T10:00:00Z",
            },
            headers={"Authorization": f"Bearer {advocate_token}"},
        )
        assert resp.status_code == 200

        # Add lodging
        resp = client.post(
            f"/matters/{matter_id}/lodgings",
            json={
                "document_kind": "Notice of Motion",
                "party": "Claimant",
                "due_date": "2026-08-10",
            },
            headers={"Authorization": f"Bearer {advocate_token}"},
        )
        assert resp.status_code == 200

        # Add court decision
        resp = client.post(
            f"/matters/{matter_id}/court-decisions",
            json={
                "decision_type": "Ruling",
                "decision_date": "2026-07-20",
                "outcome": "Application allowed",
            },
            headers={"Authorization": f"Bearer {advocate_token}"},
        )
        assert resp.status_code == 200

        # Create accounts user
        resp = client.post(
            "/users",
            json={
                "username": "accounts1",
                "password": "pass123",
                "role": "accounts",
                "display_name": "Accounts One",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

        # Login as accounts
        resp = client.post("/auth/login", json={"username": "accounts1", "password": "pass123"})
        assert resp.status_code == 200
        accounts_token = resp.json()["token"]

        # Add fee
        resp = client.post(
            f"/matters/{matter_id}/fees",
            json={
                "fee_type": "Filing fee",
                "amount": 2000,
                "paid_by": "Client",
                "paid_to": "Court",
                "status": "paid",
            },
            headers={"Authorization": f"Bearer {accounts_token}"},
        )
        assert resp.status_code == 200
        fee_id = resp.json()["fee_id"]

        # Add receipt linked to fee
        resp = client.post(
            f"/matters/{matter_id}/receipts",
            json={
                "receipt_number": "RCT-API-001",
                "issuer": "Court",
                "payer": "Client",
                "amount": 2000,
                "receipt_date": "2026-07-16",
                "linked_fee_id": fee_id,
            },
            headers={"Authorization": f"Bearer {accounts_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["linked_fee_id"] == fee_id

        # Workspace endpoint
        resp = client.get(
            f"/matters/{matter_id}/workspace", headers={"Authorization": f"Bearer {advocate_token}"}
        )
        assert resp.status_code == 200
        workspace = resp.json()
        assert all(
            key in workspace
            for key in (
                "matter",
                "parties",
                "activities",
                "lodgings",
                "court_decisions",
                "fees",
                "receipts",
                "documents",
                "summaries",
            )
        )
        assert len(workspace["parties"]) >= 1
        assert len(workspace["activities"]) >= 1

        # Calendar export
        resp = client.get(
            f"/matters/{matter_id}/calendar.ics",
            headers={"Authorization": f"Bearer {advocate_token}"},
        )
        assert resp.status_code == 200
        assert "VCALENDAR" in resp.text
        assert "Directions hearing" in resp.text

        # Offline cache
        resp = client.get("/offline-cache", headers={"Authorization": f"Bearer {advocate_token}"})
        assert resp.status_code == 200
        assert resp.json()["mode"] == "read_only"

        # Audit log (admin only)
        resp = client.get("/audit", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert len(resp.json()["events"]) >= 5

        # Audit log (non-admin should fail)
        resp = client.get("/audit", headers={"Authorization": f"Bearer {advocate_token}"})
        assert resp.status_code == 403

        # Permission denied: read_only user cannot create fees
        resp = client.post(
            "/users",
            json={
                "username": "readonly1",
                "password": "pass123",
                "role": "read_only",
                "display_name": "Read Only",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        resp = client.post("/auth/login", json={"username": "readonly1", "password": "pass123"})
        assert resp.status_code == 200
        readonly_token = resp.json()["token"]

        resp = client.post(
            f"/matters/{matter_id}/fees",
            json={"fee_type": "Bad fee", "amount": 1},
            headers={"Authorization": f"Bearer {readonly_token}"},
        )
        assert resp.status_code == 403

        # Seat limit enforcement
        seat_limit_hit = False
        for i in range(5, 100):
            resp = client.post(
                "/users",
                json={
                    "username": f"extra{i}",
                    "password": "pass123",
                    "role": "clerk",
                    "display_name": f"Extra {i}",
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 409:
                seat_limit_hit = True
                break
        assert seat_limit_hit, "seat limit was never reached"

        # Document upload
        resp = client.post(
            f"/matters/{matter_id}/documents",
            data={"title": "Test Document", "document_type": "Application"},
            files={"file": ("test.txt", b"Test document content for upload", "text/plain")},
            headers={"Authorization": f"Bearer {advocate_token}"},
        )
        assert resp.status_code == 200
        assert "document_id" in resp.json()

        # List matters now has entries
        resp = client.get("/matters", headers={"Authorization": f"Bearer {advocate_token}"})
        assert resp.status_code == 200
        assert len(resp.json()["matters"]) >= 1

        print("WAKILIOS API VALIDATION PASS")


if __name__ == "__main__":
    main()
