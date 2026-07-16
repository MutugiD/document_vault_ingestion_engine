"""HTTP client for WakiliOS backend API."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass
class WakiliOSClientConfig:
    """Configuration for connecting to a WakiliOS backend."""

    base_url: str = "http://localhost:8000"
    session_token: str = ""


@dataclass
class WakiliOSClient:
    """Synchronous HTTP client for the WakiliOS backend API.

    Uses only the Python standard library (urllib) so the Windows desktop
    client does not need additional HTTP dependencies beyond what PySide6
    ships with.
    """

    config: WakiliOSClientConfig

    def _headers(self, include_auth: bool = True) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if include_auth and self.config.session_token:
            headers["Authorization"] = f"Bearer {self.config.session_token}"
        return headers

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        include_auth: bool = True,
    ) -> dict[str, Any]:
        url = f"{self.config.base_url.rstrip('/')}{path}"
        data = json.dumps(body).encode("utf-8") if body else None
        req = Request(url, data=data, headers=self._headers(include_auth), method=method)
        try:
            with urlopen(req) as response:
                raw = response.read().decode("utf-8")
                if raw:
                    return json.loads(raw)
                return {}
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(detail)
                raise WakiliOSClientError(exc.code, parsed.get("detail", detail)) from exc
            except json.JSONDecodeError:
                raise WakiliOSClientError(exc.code, detail) from exc
        except URLError as exc:
            raise WakiliOSConnectionError(str(exc)) from exc

    def _get(self, path: str) -> dict[str, Any]:
        return self._request("GET", path)

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", path, body)

    def _put(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return self._request("PUT", path, body)

    def health(self) -> dict[str, str]:
        return self._request("GET", "/health", include_auth=False)

    def login(self, username: str, password: str) -> dict[str, Any]:
        result = self._request(
            "POST", "/auth/login", {"username": username, "password": password}, include_auth=False
        )
        self.config.session_token = str(result.get("token", ""))
        return result

    def create_user(
        self, username: str, password: str, role: str, display_name: str
    ) -> dict[str, Any]:
        return self._post(
            "/users",
            {
                "username": username,
                "password": password,
                "role": role,
                "display_name": display_name,
            },
        )

    def list_matters(self) -> list[dict[str, Any]]:
        result = self._get("/matters")
        return list(result.get("matters", []))

    def create_matter(self, **fields: str) -> dict[str, Any]:
        return self._post("/matters", fields)

    def get_matter(self, matter_id: str) -> dict[str, Any]:
        return self._get(f"/matters/{matter_id}")

    def update_matter_summary(self, matter_id: str, summary: str) -> dict[str, Any]:
        return self._put(f"/matters/{matter_id}/summary", {"summary": summary})

    def workspace(self, matter_id: str) -> dict[str, Any]:
        return self._get(f"/matters/{matter_id}/workspace")

    def add_party(self, matter_id: str, **fields: str) -> dict[str, Any]:
        return self._post(f"/matters/{matter_id}/parties", fields)

    def add_activity(self, matter_id: str, **fields: object) -> dict[str, Any]:
        return self._post(
            f"/matters/{matter_id}/activities", {k: str(v) for k, v in fields.items()}
        )

    def add_lodging(self, matter_id: str, **fields: str) -> dict[str, Any]:
        return self._post(f"/matters/{matter_id}/lodgings", fields)

    def add_court_decision(self, matter_id: str, **fields: str) -> dict[str, Any]:
        return self._post(f"/matters/{matter_id}/court-decisions", fields)

    def add_fee(self, matter_id: str, **fields: object) -> dict[str, Any]:
        return self._post(f"/matters/{matter_id}/fees", {k: str(v) for k, v in fields.items()})

    def add_receipt(self, matter_id: str, **fields: object) -> dict[str, Any]:
        return self._post(f"/matters/{matter_id}/receipts", {k: str(v) for k, v in fields.items()})

    def export_calendar(self, matter_id: str) -> str:
        url = f"{self.config.base_url.rstrip('/')}/matters/{matter_id}/calendar.ics"
        req = Request(url, headers=self._headers())
        with urlopen(req) as response:
            return response.read().decode("utf-8")

    def offline_cache(self) -> dict[str, Any]:
        return self._get("/offline-cache")

    def upload_document(
        self, matter_id: str, file_path: str, title: str = "", document_type: str = "general"
    ) -> dict[str, Any]:
        """Upload a document to a matter using multipart form-data."""
        import mimetypes
        import uuid
        from pathlib import Path as PPath
        from urllib.request import Request

        path = PPath(file_path)
        filename = path.name
        mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        content = path.read_bytes()

        boundary = uuid.uuid4().hex
        lines: list[bytes] = []
        lines.append(f"--{boundary}".encode())
        lines.append(b'Content-Disposition: form-data; name="title"')
        lines.append(b"")
        lines.append(title.encode() or filename.encode())
        lines.append(f"--{boundary}".encode())
        lines.append(b'Content-Disposition: form-data; name="document_type"')
        lines.append(b"")
        lines.append(document_type.encode())
        lines.append(f"--{boundary}".encode())
        lines.append(f'Content-Disposition: form-data; name="file"; filename="{filename}"'.encode())
        lines.append(f"Content-Type: {mime}".encode())
        lines.append(b"")
        lines.append(content)
        lines.append(f"--{boundary}--".encode())
        body = b"\r\n".join(lines)

        url = f"{self.config.base_url.rstrip('/')}/matters/{matter_id}/documents"
        headers = self._headers()
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        headers["Content-Length"] = str(len(body))
        req = Request(url, data=body, headers=headers, method="POST")
        try:
            with urlopen(req) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(detail)
                raise WakiliOSClientError(exc.code, parsed.get("detail", detail)) from exc
            except json.JSONDecodeError:
                raise WakiliOSClientError(exc.code, detail) from exc
        except URLError as exc:
            raise WakiliOSConnectionError(str(exc)) from exc

    def download_document(self, matter_id: str, document_id: str) -> dict[str, Any]:
        """Download a document's metadata from a matter."""
        return self._get(f"/matters/{matter_id}/documents/{document_id}")

    def list_fees(self, matter_id: str) -> list[dict[str, Any]]:
        result = self._get(f"/matters/{matter_id}/workspace")
        return list(result.get("fees", []))

    def list_receipts(self, matter_id: str) -> list[dict[str, Any]]:
        result = self._get(f"/matters/{matter_id}/workspace")
        return list(result.get("receipts", []))

    def audit_log(self) -> dict[str, Any]:
        return self._get("/audit")


class WakiliOSClientError(Exception):
    """Raised when the backend returns an HTTP error."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"HTTP {status_code}: {detail}")


class WakiliOSConnectionError(Exception):
    """Raised when the backend cannot be reached."""
