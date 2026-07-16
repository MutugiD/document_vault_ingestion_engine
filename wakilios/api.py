"""FastAPI boundary for the firm-hosted WakiliOS backend."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
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


class ActivityRequest(BaseModel):
    activity_type: str
    title: str
    starts_at: str
    court_session: str = ""
    status: str = "scheduled"
    notes: str = ""
    calendar_visible: bool = True


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

    def token_from_header(
        authorization: Annotated[str | None, Header()] = None,
    ) -> str:
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
        except Exception as exc:  # pragma: no cover - exercised through FastAPI
            raise handle_error(exc) from exc

    @app.post("/matters")
    def create_matter_endpoint(
        request: CreateMatterRequest,
        token: Annotated[str, Depends(token_from_header)],
    ) -> dict[str, object]:
        try:
            return backend.create_litigation_matter(token, **request.model_dump())
        except Exception as exc:  # pragma: no cover - exercised through FastAPI
            raise handle_error(exc) from exc

    @app.get("/matters/{matter_id}/workspace")
    def workspace(
        matter_id: str,
        token: Annotated[str, Depends(token_from_header)],
    ) -> dict[str, object]:
        try:
            return backend.workspace(token, matter_id)
        except Exception as exc:  # pragma: no cover - exercised through FastAPI
            raise handle_error(exc) from exc

    @app.post("/matters/{matter_id}/activities")
    def add_activity(
        matter_id: str,
        request: ActivityRequest,
        token: Annotated[str, Depends(token_from_header)],
    ) -> dict[str, object]:
        try:
            return backend.add_activity(token, matter_id, **request.model_dump())
        except Exception as exc:  # pragma: no cover - exercised through FastAPI
            raise handle_error(exc) from exc

    @app.post("/matters/{matter_id}/summaries")
    def generate_summary(
        matter_id: str,
        request: SummaryRequest,
        token: Annotated[str, Depends(token_from_header)],
    ) -> dict[str, object]:
        try:
            return backend.generate_ai_summary(token, matter_id, **request.model_dump())
        except Exception as exc:  # pragma: no cover - exercised through FastAPI
            raise handle_error(exc) from exc

    @app.get("/matters/{matter_id}/calendar.ics")
    def calendar(
        matter_id: str,
        token: Annotated[str, Depends(token_from_header)],
    ) -> str:
        try:
            return backend.export_calendar_ics(token, matter_id)
        except Exception as exc:  # pragma: no cover - exercised through FastAPI
            raise handle_error(exc) from exc

    app.state.wakilios_backend = backend
    return app
