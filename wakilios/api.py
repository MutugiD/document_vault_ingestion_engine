"""FastAPI boundary for the firm-hosted WakiliOS backend."""

from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

from wakilios.core import (
    AuthenticationError,
    PermissionDeniedError,
    SeatLimitError,
    WakiliOSError,
    initialize_firm_backend,
)


class LoginRequest(BaseModel):
    username: str
    password: str


class CreateMatterRequest(BaseModel):
    internal_reference: str
    client_name: str
    parties: str
    court: str
    station: str
    case_number: str
    practice_area: str
    responsible_advocate: str
    filing_status: str
    filing_date: str
    summary: str = ""


class UpdateMatterSummaryRequest(BaseModel):
    summary: str


class ActivityRequest(BaseModel):
    activity_type: str
    title: str
    starts_at: str
    court_session: str = ""
    status: str = "scheduled"
    notes: str = ""
    calendar_visible: bool = True


class PartyRequest(BaseModel):
    name: str
    party_role: str
    contact_details: str = ""
    representative: str = ""
    notes: str = ""


class LodgingRequest(BaseModel):
    document_kind: str
    party: str = ""
    due_date: str = ""
    lodged_date: str = ""
    filing_status: str = "pending"
    linked_document_id: str = ""
    filing_reference: str = ""


class CourtDecisionRequest(BaseModel):
    decision_type: str
    decision_date: str
    court: str = ""
    decision_maker: str = ""
    outcome: str = ""
    notes: str = ""
    linked_document_id: str = ""


class FeeRequest(BaseModel):
    fee_type: str
    amount: float
    currency: str = "KES"
    paid_by: str = ""
    paid_to: str = ""
    status: str = "pending"
    linked_activity_id: str = ""
    linked_lodging_id: str = ""


class ReceiptRequest(BaseModel):
    receipt_number: str
    issuer: str = ""
    payer: str = ""
    amount: float
    currency: str = "KES"
    receipt_date: str = ""
    linked_fee_id: str = ""
    linked_document_id: str = ""


class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str
    display_name: str


class SummaryRequest(BaseModel):
    document_id: str
    question: str = Field(default="Summarize the key information in this matter.")


def create_app(
    *,
    root: Path,
    firm_name: str,
    admin_username: str,
    admin_password: str,
    vault_passphrase: str,
    max_seats: int = 5,
) -> FastAPI:
    backend = initialize_firm_backend(
        root,
        firm_name=firm_name,
        admin_username=admin_username,
        admin_password=admin_password,
        vault_passphrase=vault_passphrase,
        max_seats=max_seats,
    )
    app = FastAPI(title="WakiliOS Firm Backend", version="0.1.0")

    def token_from_header(authorization: str | None = Header(default=None)) -> str:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="missing bearer token")
        return authorization.split(" ", 1)[1]

    def handle_error(exc: Exception) -> HTTPException:
        if isinstance(exc, AuthenticationError):
            return HTTPException(status_code=401, detail=str(exc))
        if isinstance(exc, PermissionDeniedError):
            return HTTPException(status_code=403, detail=str(exc))
        if isinstance(exc, SeatLimitError):
            return HTTPException(status_code=409, detail=str(exc))
        if isinstance(exc, WakiliOSError):
            return HTTPException(status_code=400, detail=str(exc))
        return HTTPException(status_code=500, detail="wakilios backend error")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "product": "WakiliOS"}

    @app.post("/auth/login")
    def login(request: LoginRequest) -> dict[str, object]:
        try:
            return backend.login(request.username, request.password).__dict__
        except Exception as exc:
            raise handle_error(exc) from exc

    @app.post("/users")
    def create_user(
        request: CreateUserRequest,
        token: str = Depends(token_from_header),
    ) -> dict[str, object]:
        try:
            return backend.create_user(
                token,
                username=request.username,
                password=request.password,
                role=request.role,
                display_name=request.display_name,
            )
        except Exception as exc:
            raise handle_error(exc) from exc

    @app.post("/matters")
    def create_matter_endpoint(
        request: CreateMatterRequest,
        token: str = Depends(token_from_header),
    ) -> dict[str, object]:
        try:
            return backend.create_litigation_matter(token, **request.model_dump())
        except Exception as exc:
            raise handle_error(exc) from exc

    @app.get("/matters")
    def list_matters(
        token: str = Depends(token_from_header),
    ) -> dict[str, object]:
        try:
            cache = backend.build_offline_cache(token)
            return {"matters": list(cache.matters)}
        except Exception as exc:
            raise handle_error(exc) from exc

    @app.get("/matters/{matter_id}")
    def get_matter(
        matter_id: str,
        token: str = Depends(token_from_header),
    ) -> dict[str, object]:
        try:
            return backend.get_matter(token, matter_id)
        except Exception as exc:
            raise handle_error(exc) from exc

    @app.put("/matters/{matter_id}/summary")
    def update_matter_summary(
        matter_id: str,
        request: UpdateMatterSummaryRequest,
        token: str = Depends(token_from_header),
    ) -> dict[str, object]:
        try:
            return backend.update_matter_summary(token, matter_id, request.summary)
        except Exception as exc:
            raise handle_error(exc) from exc

    @app.get("/matters/{matter_id}/workspace")
    def workspace(
        matter_id: str,
        token: str = Depends(token_from_header),
    ) -> dict[str, object]:
        try:
            return backend.workspace(token, matter_id)
        except Exception as exc:
            raise handle_error(exc) from exc

    @app.post("/matters/{matter_id}/parties")
    def add_party(
        matter_id: str,
        request: PartyRequest,
        token: str = Depends(token_from_header),
    ) -> dict[str, object]:
        try:
            return backend.add_party(token, matter_id, **request.model_dump())
        except Exception as exc:
            raise handle_error(exc) from exc

    @app.post("/matters/{matter_id}/activities")
    def add_activity(
        matter_id: str,
        request: ActivityRequest,
        token: str = Depends(token_from_header),
    ) -> dict[str, object]:
        try:
            return backend.add_activity(token, matter_id, **request.model_dump())
        except Exception as exc:
            raise handle_error(exc) from exc

    @app.post("/matters/{matter_id}/lodgings")
    def add_lodging(
        matter_id: str,
        request: LodgingRequest,
        token: str = Depends(token_from_header),
    ) -> dict[str, object]:
        try:
            return backend.add_lodging(token, matter_id, **request.model_dump())
        except Exception as exc:
            raise handle_error(exc) from exc

    @app.post("/matters/{matter_id}/court-decisions")
    def add_court_decision(
        matter_id: str,
        request: CourtDecisionRequest,
        token: str = Depends(token_from_header),
    ) -> dict[str, object]:
        try:
            return backend.add_court_decision(token, matter_id, **request.model_dump())
        except Exception as exc:
            raise handle_error(exc) from exc

    @app.post("/matters/{matter_id}/fees")
    def add_fee(
        matter_id: str,
        request: FeeRequest,
        token: str = Depends(token_from_header),
    ) -> dict[str, object]:
        try:
            return backend.add_fee(token, matter_id, **request.model_dump())
        except Exception as exc:
            raise handle_error(exc) from exc

    @app.post("/matters/{matter_id}/receipts")
    def add_receipt(
        matter_id: str,
        request: ReceiptRequest,
        token: str = Depends(token_from_header),
    ) -> dict[str, object]:
        try:
            return backend.add_receipt(token, matter_id, **request.model_dump())
        except Exception as exc:
            raise handle_error(exc) from exc

    @app.post("/matters/{matter_id}/documents")
    async def upload_document(
        matter_id: str,
        token: str = Depends(token_from_header),
        title: str = "",
        document_type: str = "general",
        file: UploadFile | None = None,
    ) -> dict[str, object]:
        try:
            content = b""
            if file is not None:
                content = await file.read()
            extracted_text = content.decode("utf-8", errors="replace")
            original_name = file.filename if file else "upload.txt"
            content_type = (
                file.content_type if file and file.content_type else "application/octet-stream"
            )
            return backend.upload_document(
                token,
                matter_id,
                title=title or original_name,
                document_type=document_type,
                content=content,
                original_name=original_name,
                content_type=content_type,
                extracted_text=extracted_text,
            )
        except Exception as exc:
            raise handle_error(exc) from exc

    @app.post("/matters/{matter_id}/summaries")
    def generate_summary(
        matter_id: str,
        request: SummaryRequest,
        token: str = Depends(token_from_header),
    ) -> dict[str, object]:
        try:
            return backend.generate_ai_summary(token, matter_id, **request.model_dump())
        except Exception as exc:
            raise handle_error(exc) from exc

    @app.get("/matters/{matter_id}/calendar.ics")
    def calendar(
        matter_id: str,
        token: str = Depends(token_from_header),
    ) -> str:
        try:
            return backend.export_calendar_ics(token, matter_id)
        except Exception as exc:
            raise handle_error(exc) from exc

    @app.get("/offline-cache")
    def offline_cache(
        token: str = Depends(token_from_header),
    ) -> dict[str, object]:
        try:
            cache = backend.build_offline_cache(token)
            return cache.to_mapping()
        except Exception as exc:
            raise handle_error(exc) from exc

    @app.get("/audit")
    def audit_log(
        token: str = Depends(token_from_header),
    ) -> dict[str, object]:
        try:
            events = backend.audit_events(token)
            return {"events": events}
        except Exception as exc:
            raise handle_error(exc) from exc

    app.state.wakilios_backend = backend
    return app
