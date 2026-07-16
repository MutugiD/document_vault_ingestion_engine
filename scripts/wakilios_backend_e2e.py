"""WakiliOS multi-seat backend smoke verification."""

from __future__ import annotations

import tempfile
from pathlib import Path

from wakilios import PermissionDeniedError, SeatLimitError, initialize_firm_backend


def run_wakilios_backend_e2e(workspace: Path | None = None) -> dict[str, object]:
    if workspace is None:
        temporary = tempfile.TemporaryDirectory(prefix="wakilios-backend-")
        workspace_path = Path(temporary.name)
    else:
        temporary = None
        workspace_path = workspace
    try:
        backend = initialize_firm_backend(
            workspace_path,
            firm_name="WakiliOS Test Firm",
            admin_username="admin",
            admin_password="admin-passphrase",
            vault_passphrase="wakilios backend vault passphrase",
            max_seats=4,
        )
        admin = backend.login("admin", "admin-passphrase")
        advocate = backend.create_user(
            admin.token,
            username="advocate",
            password="advocate-passphrase",
            role="advocate",
            display_name="Advocate User",
        )
        accounts = backend.create_user(
            admin.token,
            username="accounts",
            password="accounts-passphrase",
            role="accounts",
            display_name="Accounts User",
        )
        readonly = backend.create_user(
            admin.token,
            username="readonly",
            password="readonly-passphrase",
            role="read_only",
            display_name="Read Only User",
        )
        seat_limit_blocked = False
        try:
            backend.create_user(
                admin.token,
                username="extra",
                password="extra-passphrase",
                role="clerk",
                display_name="Extra User",
            )
        except SeatLimitError:
            seat_limit_blocked = True

        advocate_session = backend.login(str(advocate["username"]), "advocate-passphrase")
        accounts_session = backend.login(str(accounts["username"]), "accounts-passphrase")
        readonly_session = backend.login(str(readonly["username"]), "readonly-passphrase")

        matter = backend.create_litigation_matter(
            advocate_session.token,
            internal_reference="WAK-001",
            client_name="Example Client Ltd",
            parties="Example Client Ltd v Sample Respondent",
            court="High Court",
            station="Nairobi",
            case_number="HCCC E001 of 2026",
            practice_area="Commercial litigation",
            responsible_advocate="Advocate User",
            filing_status="filed",
            filing_date="2026-07-16",
            summary="Commercial claim pending mention.",
        )
        matter_id = str(matter["matter_id"])
        backend.add_party(
            advocate_session.token,
            matter_id,
            name="Example Client Ltd",
            party_role="Claimant",
            representative="Advocate User",
        )
        backend.add_activity(
            advocate_session.token,
            matter_id,
            activity_type="mention",
            title="Mention for directions",
            starts_at="2026-08-20T09:00:00Z",
            court_session="Virtual court",
            status="scheduled",
            notes="Confirm filing of application.",
        )
        lodging = backend.add_lodging(
            advocate_session.token,
            matter_id,
            document_kind="Notice of Motion",
            party="Claimant",
            due_date="2026-08-10",
            filing_status="pending",
            filing_reference="E-filing pending",
        )
        backend.add_court_decision(
            advocate_session.token,
            matter_id,
            decision_type="Directions",
            decision_date="2026-07-16",
            court="High Court",
            decision_maker="Duty Judge",
            outcome="Mention date allocated.",
        )
        fee = backend.add_fee(
            accounts_session.token,
            matter_id,
            fee_type="Filing fee",
            amount=1500,
            paid_by="Example Client Ltd",
            paid_to="Judiciary",
            status="paid",
            linked_lodging_id=str(lodging["lodging_id"]),
        )
        backend.add_receipt(
            accounts_session.token,
            matter_id,
            receipt_number="RCT-001",
            issuer="Judiciary",
            payer="Example Client Ltd",
            amount=1500,
            receipt_date="2026-07-16",
            linked_fee_id=str(fee["fee_id"]),
        )
        document = backend.upload_document(
            advocate_session.token,
            matter_id,
            title="Notice of Motion",
            document_type="Application",
            content=b"Notice of Motion filed for interim orders.",
            original_name="notice-of-motion.txt",
            content_type="text/plain",
            extracted_text=(
                "Notice of Motion filed by Example Client Ltd seeking interim orders. "
                "The matter has a mention for directions and filing fee receipt RCT-001."
            ),
        )
        summary = backend.generate_ai_summary(
            advocate_session.token,
            matter_id,
            document_id=str(document["document_id"]),
        )
        permission_blocked = False
        try:
            backend.add_fee(
                readonly_session.token,
                matter_id,
                fee_type="Unauthorized fee",
                amount=10,
            )
        except PermissionDeniedError:
            permission_blocked = True
        ics = backend.export_calendar_ics(advocate_session.token, matter_id)
        cache = backend.build_offline_cache(readonly_session.token)
        workspace_payload = backend.workspace(advocate_session.token, matter_id)
        audit_events = backend.audit_events(admin.token)
        return {
            "product": "WakiliOS",
            "matter_id": matter_id,
            "workspace_tabs_present": all(
                key in workspace_payload
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
            ),
            "seat_limit_blocked": seat_limit_blocked,
            "permission_blocked": permission_blocked,
            "document_uploaded": bool(document["document_id"]),
            "summary_has_citations": bool(summary["citation_ids"]),
            "ics_contains_activity": "Mention for directions" in ics,
            "ics_contains_lodging": "Lodging due: Notice of Motion" in ics,
            "offline_cache_mode": cache.mode,
            "offline_cache_matter_count": len(cache.matters),
            "audit_event_count": len(audit_events),
            "raw_document_text_in_audit": any(
                "interim orders" in str(event).lower() for event in audit_events
            ),
        }
    finally:
        if temporary is not None:
            temporary.cleanup()


if __name__ == "__main__":
    import json

    print(json.dumps(run_wakilios_backend_e2e(), indent=2, sort_keys=True))
