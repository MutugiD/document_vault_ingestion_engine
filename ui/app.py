"""WakiliOS desktop shell with in-process and multi-seat connectivity."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ai import configured_provider_statuses, provider_env_var, supported_providers
from core import ManualAppSession
from ui.automation import automation_enabled, queued_selection, write_state
from ui.reminders import (
    DEFAULT_HORIZON_DAYS,
    DEFAULT_HOUR,
    DEFAULT_MINUTE,
    ReminderSettings,
    due_now,
    load_settings,
    mark_shown,
    save_settings,
    settings_path,
)
from ui.reminders import summarise as summarise_reminders
from wakilios.client import (
    WakiliOSClient,
    WakiliOSClientConfig,
    WakiliOSClientError,
    WakiliOSConnectionError,
)
from wakilios.core import (
    NAIROBI,
    SCHEMA_VERSION,
    WakiliOSBackend,
    WakiliOSError,
    initialize_firm_backend,
    normalize_matter_date,
)

DEV_UNLOCK_ENV_VAR = "JURISNURU_DEV_UNLOCK"
# Paid features, and the controls each one governs. A licence carries these
# switches; until now they were parsed, displayed and ignored, so every plan
# behaved like enterprise.
ENTITLEMENT_CONTROLS: dict[str, tuple[str, ...]] = {
    "document_intake": (
        "addFilesButton",
        "runOcrButton",
        "uploadDocumentButton",
    ),
    "cloud_backup": ("createBackupButton",),
    "managed_restore": ("restoreDrillButton",),
    "matter_rag": ("askRagButton", "generateSummaryButton", "matterAiAskButton"),
    "hosted_ai": ("saveProviderSettingsButton",),
}

ENTITLEMENT_LABELS: dict[str, str] = {
    "document_intake": "Document intake",
    "cloud_backup": "Cloud backup",
    "managed_restore": "Managed restore",
    "matter_rag": "Matter search and RAG",
    "hosted_ai": "Hosted AI",
}


def _extracted_text_for(source: Path) -> str:
    """The document's text, for search and RAG.

    Decoding the raw bytes was indexing PDF internals -- xref tables and stream
    dictionaries -- so every uploaded document was unsearchable and any answer
    drawn from one cited gibberish. Run the extraction pipeline instead, which
    also means a scanned upload goes through OCR.
    """
    from core.manual_app import resolve_ocr_engine
    from intake.extraction import ExtractionError, extract_text

    try:
        return extract_text(source, ocr_engine=resolve_ocr_engine(source)).text
    except (ExtractionError, Exception):
        # An unreadable document is still worth storing; it simply has no text
        # to search. Never fall back to raw bytes.
        return ""


def _choose_file(parent, caption: str, filters: str) -> str:
    """A single file, from the automation queue or the native picker."""
    queued = queued_selection()
    if queued:
        return queued[0]
    selected, _ = QFileDialog.getOpenFileName(parent, caption, "", filters)
    return selected


def _choose_files(parent, caption: str, filters: str) -> list[str]:
    """Several files, from the automation queue or the native picker."""
    queued = queued_selection()
    if queued:
        return queued
    selected, _ = QFileDialog.getOpenFileNames(parent, caption, "", filters)
    return list(selected)


def _choose_save_path(parent, caption: str, filters: str) -> str:
    """A destination path, from the automation queue or the native picker."""
    queued = queued_selection()
    if queued:
        return queued[0]
    return QFileDialog.getSaveFileName(parent, caption, "", filters)[0]


def _joined(*parts: object) -> str:
    """Join the non-empty parts of a row summary."""
    return " | ".join(str(part) for part in parts if str(part).strip())


@dataclass(frozen=True)
class FormField:
    """One input on a matter record form.

    ``choices`` renders a combo box; the portal's vocabularies (party type,
    activity type, filing status) are suggestions rather than enums, because
    they were read off one firm's account at a subset of stations.
    """

    name: str
    label: str
    placeholder: str = ""
    choices: tuple[str, ...] = ()
    numeric: bool = False
    required: bool = False
    is_date: bool = False
    """Validated against the backend's own date rules before the form closes.

    The backend refuses a date it cannot parse, which is right -- an
    unparseable due date used to corrupt the whole calendar export. But a
    rejection that arrives as a status-bar error after the dialog has closed
    loses the user's typing and does not say which field was wrong. Checking
    here means the message names the field while it is still on screen.
    """


class MatterRecordDialog(QDialog):
    """Collect one matter record from the user.

    Replaces the fixed placeholder rows the Add buttons used to write. Built
    from the field spec on ``MatterTabView`` so a tab cannot gain an input the
    backend does not accept.
    """

    def __init__(self, view: MatterTabView, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName(f"{view.object_name}Dialog")
        self.setWindowTitle(f"Add {view.singular}")
        self.setMinimumWidth(420)
        self._view = view
        self._inputs: dict[str, QWidget] = {}

        layout = QVBoxLayout(self)
        form = QFormLayout()
        for field in view.fields:
            widget: QWidget
            if field.choices:
                widget = QComboBox()
                widget.setEditable(True)
                widget.addItems(field.choices)
                widget.setCurrentText("")
            else:
                widget = QLineEdit()
                if field.placeholder:
                    widget.setPlaceholderText(field.placeholder)
            widget.setObjectName(f"{view.object_name}Field_{field.name}")
            self._inputs[field.name] = widget
            form.addRow(f"{field.label}*" if field.required else field.label, widget)
        layout.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setObjectName(f"{view.object_name}DialogError")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.setObjectName(f"{view.object_name}DialogButtons")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _field_specs(self) -> tuple[FormField, ...]:
        return self._view.fields

    def _value(self, field: FormField) -> str:
        widget = self._inputs[field.name]
        text = widget.currentText() if isinstance(widget, QComboBox) else widget.text()
        return text.strip()

    def _on_accept(self) -> None:
        for field in self._view.fields:
            value = self._value(field)
            if field.required and not value:
                self.error_label.setText(f"{field.label} is required.")
                return
            if field.numeric and value:
                try:
                    float(value)
                except ValueError:
                    self.error_label.setText(f"{field.label} must be a number.")
                    return
            if field.is_date and value:
                try:
                    normalize_matter_date(value, field=field.label)
                except WakiliOSError:
                    self.error_label.setText(
                        f"{field.label} must be a date: 2026-08-06 or 06/08/2026."
                    )
                    return
        self.accept()

    def values(self) -> dict[str, object]:
        """Field values, with blanks omitted so backend defaults still apply."""
        collected: dict[str, object] = {}
        for field in self._view.fields:
            value = self._value(field)
            if not value:
                continue
            collected[field.name] = float(value) if field.numeric else value
        return collected


MATTER_FIELDS: tuple[FormField, ...] = (
    FormField("internal_reference", "Firm reference", "left blank, one is generated"),
    FormField("client_name", "Client", required=True),
    FormField("parties", "Parties", "e.g. Abdi Yusuf vs Faith Kinya Kiaira"),
    FormField("case_number", "Case number", "e.g. HCCOMM/E214/2026"),
    FormField(
        "court",
        "Court",
        choices=(
            "High Court",
            "Court of Appeal",
            "Supreme Court",
            "Employment and Labour Relations Court",
            "Environment and Land Court",
            "Chief Magistrate's Court",
            "Principal Magistrate's Court",
            "Resident Magistrate's Court",
        ),
    ),
    FormField("station", "Station", "e.g. Meru, Milimani, Maua"),
    FormField(
        "practice_area",
        "Practice area",
        choices=(
            "Civil",
            "Commercial",
            "Criminal",
            "Employment",
            "Succession",
            "Environment and Land",
            "Family",
            "Constitutional",
            "Judicial Review",
        ),
    ),
    FormField("filing_status", "Filing status", choices=("draft", "filed", "served", "closed")),
    FormField("filing_date", "Filing date", "YYYY-MM-DD", is_date=True),
)


def _draft_matter_summary(workspace: dict) -> str:
    """Compose a matter summary from recorded facts only."""
    matter = workspace.get("matter") or {}
    lines: list[str] = []

    parties = str(matter.get("parties") or "").strip()
    case_number = str(matter.get("case_number") or "").strip()
    court = str(matter.get("court") or "").strip()
    station = str(matter.get("station") or "").strip()

    opening = parties or str(matter.get("client_name") or "").strip() or "This matter"
    venue = " at ".join(part for part in (court, station) if part)
    if case_number and venue:
        lines.append(f"{opening} - {case_number}, {venue}.")
    elif case_number:
        lines.append(f"{opening} - {case_number}.")
    elif venue:
        lines.append(f"{opening} - {venue}.")
    else:
        lines.append(f"{opening}.")

    def count(key: str) -> int:
        return len(workspace.get(key) or [])

    holdings = [
        f"{count('documents')} document(s)",
        f"{count('parties')} part(y/ies)",
        f"{count('activities')} activity/activities",
        f"{count('lodgings')} lodging(s)",
    ]
    lines.append("On record: " + ", ".join(holdings) + ".")

    fees = workspace.get("fees") or []
    receipts = workspace.get("receipts") or []
    if fees or receipts:
        raised = sum(float(item.get("amount") or 0) for item in fees)
        paid = sum(float(item.get("amount") or 0) for item in receipts)
        lines.append(
            f"Fees: KES {raised:,.2f} raised, KES {paid:,.2f} receipted, "
            f"balance KES {raised - paid:,.2f}."
        )

    decisions = workspace.get("court_decisions") or []
    if decisions:
        latest = decisions[-1]
        detail = " ".join(
            str(latest.get(key) or "").strip()
            for key in ("decision_date", "decision_type", "outcome")
        ).strip()
        lines.append(f"Latest decision: {detail}.")

    filings = workspace.get("filing_records") or []
    if filings:
        latest = filings[-1]
        filed = str(latest.get("what_was_filed") or "").strip()
        when = str(latest.get("filed_at") or "").strip()
        tracking = str(latest.get("tracking_number") or "").strip()
        parts = [
            p for p in (filed, when and f"filed {when}", tracking and f"tracking {tracking}") if p
        ]
        if parts:
            lines.append("Filing: " + ", ".join(parts) + ".")
        served = str(latest.get("what_was_served") or "").strip()
        if served:
            lines.append(f"Service: {served}.")
        next_action = str(latest.get("next_action") or "").strip()
        next_date = str(latest.get("next_action_date") or "").strip()
        if next_action or next_date:
            lines.append(f"Next action: {' '.join(p for p in (next_action, next_date) if p)}.")

    upcoming = [
        item
        for item in (workspace.get("activities") or [])
        if str(item.get("starts_at") or "").strip()
    ]
    if upcoming:
        # Sorting is chronological because starts_at is stored as Nairobi local
        # wall time (see wakilios.core.CALENDAR_DATE_COLUMNS). This used to take
        # [-1] into a variable named "soonest" under a label reading "Recorded
        # activity" -- three different intentions, and the one that shipped was
        # the furthest-away date.
        ordered = sorted(upcoming, key=lambda item: str(item.get("starts_at")))
        today = _today_iso()
        future = [item for item in ordered if str(item.get("starts_at")) >= today]
        entry = future[0] if future else ordered[-1]
        label = "Next activity" if future else "Last recorded activity"
        lines.append(
            f"{label}: {entry.get('activity_type', '')} {entry.get('starts_at', '')}".strip() + "."
        )

    lines.append("")
    lines.append("Drafted from the matter record. Verify before relying on it.")
    return "\n".join(lines)


def _settings_dir() -> Path:
    """Where per-installation settings live.

    The licence is bound to the installation identity stored here, so this path
    cannot move without a migration -- see the pending WakiliOS -> JurisNuru
    rename.
    """
    return Path(os.environ.get("APPDATA", tempfile.gettempdir())) / "WakiliOS" / "settings"


def _today_iso() -> str:
    """Today in Nairobi, as stored dates are written.

    Not ``date.today()``: that follows the machine's clock, and an advocate
    travelling would see yesterday's diary.
    """
    return datetime.now(NAIROBI).date().isoformat()


def _tomorrow_iso() -> str:
    """The exclusive end of today's half-open range."""
    return (datetime.now(NAIROBI).date() + timedelta(days=1)).isoformat()


def _next_reference() -> str:
    """A firm reference when none was given, ordered and readable."""
    from datetime import UTC, datetime

    return f"MTR-{datetime.now(UTC):%Y%m%d-%H%M%S}"


class MatterDialog(QDialog):
    """Open a matter, optionally prefilled from a document.

    Fields read from a document are marked, because a value the computer
    supplied deserves a second look before it becomes the firm's record.
    """

    def __init__(
        self,
        prefill: dict[str, str],
        *,
        source: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("matterDialog")
        self.setWindowTitle("Open a matter")
        self.setMinimumWidth(560)
        self._inputs: dict[str, QWidget] = {}

        layout = QVBoxLayout(self)
        if source:
            banner = QLabel(
                f"Prefilled from <b>{Path(source).name}</b>. Check each value before saving."
            )
            banner.setObjectName("dialogHint")
            banner.setWordWrap(True)
            layout.addWidget(banner)

        form = QFormLayout()
        for field_spec in MATTER_FIELDS:
            widget: QWidget
            value = prefill.get(field_spec.name, "")
            if field_spec.choices:
                widget = QComboBox()
                widget.setEditable(True)
                widget.addItems(field_spec.choices)
                widget.setCurrentText(value)
            else:
                widget = QLineEdit(value)
                if field_spec.placeholder:
                    widget.setPlaceholderText(field_spec.placeholder)
            widget.setObjectName(f"matterField_{field_spec.name}")
            self._inputs[field_spec.name] = widget
            label = f"{field_spec.label}*" if field_spec.required else field_spec.label
            if field_spec.name in prefill:
                label = f"{label}  (read)"
            form.addRow(label, widget)
        layout.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setObjectName("matterDialogError")
        self.error_label.setProperty("error", True)
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.setObjectName("matterDialogButtons")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _field_specs(self) -> tuple[FormField, ...]:
        return MATTER_FIELDS

    def _value(self, name: str) -> str:
        widget = self._inputs[name]
        text = widget.currentText() if isinstance(widget, QComboBox) else widget.text()
        return text.strip()

    def _on_accept(self) -> None:
        for field_spec in MATTER_FIELDS:
            if field_spec.required and not self._value(field_spec.name):
                self.error_label.setText(f"{field_spec.label} is required.")
                return
        self.accept()

    def values(self) -> dict[str, str]:
        return {name: self._value(name) for name in self._inputs}


@dataclass(frozen=True)
class MatterTabView:
    """One matter sub-tab: how it is built, and how its rows are rendered.

    Construction and refresh read the same table so a tab cannot be added to
    the workspace without a formatter, or formatted without existing.
    """

    object_name: str
    label: str
    singular: str
    workspace_key: str
    empty_text: str
    format_row: Callable[[dict[str, object]], str]
    # Documents arrive by upload, not by a generic Add. Giving that tab an Add
    # button produced a control with nothing connected to it.
    addable: bool = True
    # Inputs shown when Add is pressed. Field names are the keyword arguments
    # the matching backend method accepts.
    fields: tuple[FormField, ...] = ()


MATTER_TAB_VIEWS: tuple[MatterTabView, ...] = (
    MatterTabView(
        "partiesTab",
        "Parties",
        "party",
        "parties",
        "Parties involved",
        lambda row: _joined(
            row.get("party_role", ""),
            row.get("name", ""),
            row.get("representative", ""),
        ),
        fields=(
            FormField("name", "Party name", "e.g. Angela Wambui Nderito", required=True),
            FormField(
                "party_role",
                "Party type",
                choices=(
                    "1st Plaintiff",
                    "1st Defendant",
                    "1st Respondent",
                    "1st Interested Party",
                    "Applicant",
                ),
                required=True,
            ),
            FormField("representative", "Firm / agent", "e.g. Kiriinya and Achieng Advocates"),
            FormField("contact_details", "Contact"),
            FormField("notes", "Notes"),
        ),
    ),
    MatterTabView(
        "activitiesTab",
        "Activities",
        "activity",
        "activities",
        "Mentions and applications",
        lambda row: _joined(
            row.get("starts_at", "") or "no date",
            row.get("activity_type", ""),
            row.get("title", ""),
            row.get("court_session", ""),
            row.get("status", ""),
        ),
        fields=(
            FormField(
                "activity_type",
                "Activity",
                choices=("Mention", "Directions", "Hearing", "Ruling", "Judgment"),
                required=True,
            ),
            FormField("title", "Title", "what this activity is", required=True),
            FormField("starts_at", "Date", "YYYY-MM-DD", is_date=True),
            FormField("court_session", "Court room", "e.g. Courtroom 32, 2nd Floor"),
            FormField("status", "Actioned to", "e.g. Hon. Justice Peter Mulwa"),
            FormField("notes", "Outcome"),
        ),
    ),
    MatterTabView(
        "lodgingsTab",
        "Lodgings",
        "lodging",
        "lodgings",
        "Documents for lodging",
        lambda row: _joined(
            row.get("lodged_date", "") or row.get("due_date", "") or "not lodged",
            row.get("document_kind", ""),
            row.get("party", ""),
            row.get("filing_status", ""),
            f"ref {row['filing_reference']}" if row.get("filing_reference") else "",
        ),
        fields=(
            FormField("document_kind", "Document", "what is being lodged", required=True),
            FormField("party", "Created by"),
            FormField("due_date", "Due date", "YYYY-MM-DD", is_date=True),
            FormField("lodged_date", "Lodged date", "YYYY-MM-DD", is_date=True),
            FormField(
                "filing_status",
                "Fee status",
                choices=("Not Payable", "Payable", "Paid", "pending"),
            ),
            FormField("actioning_status", "Portal status", choices=("Not Actioned", "Actioned")),
            FormField("filing_reference", "Tracking number", "e.g. AERJ2026"),
        ),
    ),
    MatterTabView(
        "courtDecisionsTab",
        "Court Decisions",
        "court decision",
        "court_decisions",
        "Decisions so far",
        lambda row: _joined(
            row.get("decision_date", "") or "no date",
            row.get("decision_type", ""),
            row.get("decision_maker", ""),
            row.get("outcome", ""),
        ),
        fields=(
            FormField(
                "decision_type",
                "Decision",
                choices=("Ruling", "Judgment", "Order", "Direction"),
                required=True,
            ),
            FormField("decision_date", "Date", "YYYY-MM-DD", is_date=True),
            FormField("court", "Court", "e.g. Milimani High Court"),
            FormField("decision_maker", "Decision maker", "e.g. Hon. Justice Francis Gikonyo"),
            FormField("outcome", "Outcome"),
            FormField("notes", "Notes"),
        ),
    ),
    MatterTabView(
        "feesTab",
        "Fees",
        "fee",
        "fees",
        "Court filing fees",
        lambda row: _joined(
            f"[{row.get('fee_id', '?')}]",
            row.get("fee_type", "Fee"),
            f"{row.get('currency', 'KES')} {row.get('amount', 0)}",
            row.get("status", ""),
        ),
        fields=(
            FormField("fee_type", "Payment type", "e.g. Fees", required=True),
            FormField("amount", "Amount", "0.00", numeric=True, required=True),
            FormField("prn", "PRN", "e.g. E6EWRY6F"),
            FormField("currency", "Currency", choices=("KES", "USD")),
            FormField("status", "Status", choices=("pending", "paid", "Not Payable")),
            FormField("paid_by", "Paid by"),
        ),
    ),
    MatterTabView(
        "receiptsTab",
        "Receipts",
        "receipt",
        "receipts",
        "Court and client receipts",
        lambda row: _joined(
            f"[{row.get('receipt_number', '?')}]",
            row.get("receipt_date", ""),
            f"{row.get('currency', 'KES')} {row.get('amount', 0)}",
            f"fee {row['linked_fee_id']}" if row.get("linked_fee_id") else "",
        ),
        fields=(
            FormField("receipt_number", "Customer ref#", "e.g. E6EWRY6F", required=True),
            FormField("amount", "Amount paid", "0.00", numeric=True, required=True),
            FormField("receipt_date", "Date", "YYYY-MM-DD", is_date=True),
            FormField("issuer", "Channel", choices=("PYBL", "MPESA", "KCB", "Cash")),
            FormField("payer", "Payer"),
            FormField("linked_fee_id", "Against fee", "fee id, optional"),
        ),
    ),
    MatterTabView(
        "matterDocumentsTab",
        "Documents",
        "document",
        "documents",
        "Matter document vault",
        lambda row: _joined(
            row.get("title", "") or row.get("document_type", "Document"),
            row.get("lifecycle_status", ""),
            row.get("filing_role", ""),
            f"id {row.get('document_id', '?')}",
        ),
        addable=False,
    ),
    MatterTabView(
        "filingRecordTab",
        "Filing record",
        "filing record",
        "filing_records",
        "What was filed, served, received, and what happens next",
        lambda row: _joined(
            row.get("filed_at", "") or "not filed",
            row.get("tracking_number", ""),
            row.get("what_was_filed", ""),
            row.get("portal_status", ""),
            f"next: {row['next_action']} {row.get('next_action_date', '')}".strip()
            if row.get("next_action")
            else "",
        ),
        fields=(
            FormField("tracking_number", "Tracking number", "e.g. AERJ2026", required=True),
            FormField("what_was_filed", "What was filed", required=True),
            FormField("filed_at", "Filed on", "YYYY-MM-DD", is_date=True),
            FormField("station", "Station", "e.g. Milimani High Court"),
            FormField("case_number", "Case number", "e.g. HCCOMM/E214/2026"),
            FormField("what_was_served", "What was served"),
            FormField("what_was_received", "What came back", "e.g. filing receipt"),
            FormField("next_action", "Next action"),
            FormField("next_action_date", "Next action date", "YYYY-MM-DD", is_date=True),
            FormField("portal_status", "Portal status", choices=("Not Actioned", "Actioned")),
        ),
    ),
)


def _dev_unlock_requested() -> bool:
    """Whether to open the license gate for local development.

    This is a UI-layer bypass only: it flips the same gate state a real
    activation produces, and leaves every licensing check, widget and code
    path instantiated and reachable. Nothing in ``licensing/`` consults it,
    so the compiled trust anchor in ``licensing/core.pyd`` is untouched.

    It is inert in packaged builds -- PyInstaller sets ``sys.frozen`` -- so a
    shipped executable gates regardless of the environment it runs in.
    """
    if getattr(sys, "frozen", False):
        return False
    return os.environ.get(DEV_UNLOCK_ENV_VAR) == "1"


@dataclass(frozen=True)
class ModuleStatus:
    name: str
    status: str


DEFAULT_MODULES = (
    ModuleStatus("Firm backend", "Ready"),
    ModuleStatus("Multi-seat roles", "Ready"),
    ModuleStatus("Licensing", "Ready"),
    ModuleStatus("Encrypted vault", "Ready"),
    ModuleStatus("Document intake", "Ready"),
    ModuleStatus("Matter workspace", "Ready"),
    ModuleStatus("Matter search", "Ready"),
    ModuleStatus("Calendar export", "Ready"),
    ModuleStatus("AI summaries", "Ready"),
)


class WorkerSignals(QObject):
    completed = Signal(object)
    failed = Signal(str)


class BackgroundWorker(QRunnable):
    """Run a callable outside the UI thread and emit completion/failure."""

    def __init__(self, task: Callable[[], object]) -> None:
        super().__init__()
        self.task = task
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            self.signals.completed.emit(self.task())
        except Exception as exc:  # pragma: no cover - UI worker safety net
            self.signals.failed.emit(str(exc))


class BackendConnectionDialog(QFrame):
    """Login dialog for connecting to WakiliOS backend or starting in solo mode."""

    login_succeeded = Signal(str, str, str)  # token, username, role
    solo_mode_started = Signal(str, str)  # username, role

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("backendConnectionDialog")
        layout = QFormLayout(self)

        self.server_url = QLineEdit("http://localhost:8000")
        self.server_url.setObjectName("serverUrlInput")
        self.username_input = QLineEdit()
        self.username_input.setObjectName("backendUsernameInput")
        self.password_input = QLineEdit()
        self.password_input.setObjectName("backendPasswordInput")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.status_label = QLabel("Not connected")
        self.status_label.setObjectName("backendStatusLabel")
        self.connect_button = QPushButton("Connect to server")
        self.connect_button.setObjectName("connectButton")
        self.solo_button = QPushButton("Start solo")
        self.solo_button.setObjectName("startSoloButton")

        layout.addRow("Server URL", self.server_url)
        layout.addRow("Username", self.username_input)
        layout.addRow("Password", self.password_input)
        layout.addRow("Status", self.status_label)
        solo_layout = QHBoxLayout()
        solo_layout.addWidget(self.connect_button)
        solo_layout.addWidget(self.solo_button)
        layout.addRow("", solo_layout)

        self.connect_button.clicked.connect(self._attempt_login)
        self.solo_button.clicked.connect(self._attempt_solo)

    def _attempt_login(self) -> None:
        url = self.server_url.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text()
        if not url or not username or not password:
            self.status_label.setText("Enter server URL, username, and password")
            return
        try:
            client = WakiliOSClient(WakiliOSClientConfig(base_url=url))
            result = client.login(username, password)
            role = str(result.get("role", ""))
            self.status_label.setText(f"Connected as {username} ({role})")
            self.login_succeeded.emit(client.config.session_token, username, role)
        except WakiliOSClientError as exc:
            self.status_label.setText(f"Login failed: {exc.detail}")
        except WakiliOSConnectionError as exc:
            self.status_label.setText(f"Connection failed: {exc}")

    def _attempt_solo(self) -> None:
        username = self.username_input.text().strip() or "admin"
        self.status_label.setText(f"Starting solo mode as {username} (admin)")
        self.solo_mode_started.emit(username, "admin")


class MainWindow(QMainWindow):
    """Production-oriented V1 desktop workbench."""

    def __init__(
        self,
        modules: tuple[ModuleStatus, ...] = DEFAULT_MODULES,
        *,
        workspace: Path | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("JurisNuru")
        self.setMinimumSize(920, 620)

        self._backend_client: WakiliOSClient | None = None
        self._backend_local: WakiliOSBackend | None = None
        self._entitlements: dict[str, bool] = {}
        self._workspace_root = workspace
        self._current_role: str = ""
        self._current_username: str = ""
        self._current_matter_id: str = ""
        self._license_active = False
        self._reminder_settings = ReminderSettings()
        self._reminder_entries: list[dict[str, object]] = []
        self._tray_icon = None

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(12)

        heading = QLabel("JurisNuru")
        heading.setObjectName("heading")
        heading.setAlignment(Qt.AlignmentFlag.AlignLeft)
        root_layout.addWidget(heading)

        subtitle = QLabel(
            "Multi-seat litigation management, encrypted custody, search, and firm workflows."
        )
        subtitle.setObjectName("subtitle")
        root_layout.addWidget(subtitle)

        self.application_stack = QStackedWidget()
        self.application_stack.setObjectName("applicationStack")
        self.license_gate = _scroll_page(_license_page())
        self.license_gate.setObjectName("licenseGate")
        self.application_stack.addWidget(self.license_gate)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("workflowTabs")
        # Navigation follows the product brief: the matter is the centre, the
        # filing record is first-class, and search is its own destination
        # rather than a box inside settings.
        self.tabs.addTab(_scroll_page(_workspace_page()), "Matters")
        self.tabs.addTab(_scroll_page(_documents_page()), "Documents")
        self.tabs.addTab(_scroll_page(_filing_record_page()), "Filing record")
        self.tabs.addTab(_scroll_page(_search_page()), "Search")
        self.tabs.addTab(_scroll_page(_reports_page()), "Reports")
        self.tabs.addTab(_scroll_page(_settings_page(modules)), "Settings")
        # The sidebar goes inside the stack, not around it, so a locked
        # application shows the gate alone and never the navigation.
        self.application_stack.addWidget(self._build_workbench())
        root_layout.addWidget(self.application_stack, stretch=1)

        footer = QHBoxLayout()
        footer.setSpacing(10)
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("statusLabel")
        footer.addWidget(self.status_label, stretch=1)

        self.selftest_button = QPushButton("Run selftest")
        self.selftest_button.setObjectName("runSelftestButton")
        self.selftest_button.clicked.connect(self.run_worker_selftest)
        footer.addWidget(self.selftest_button)

        self.workflow_button = QPushButton("Run workflow check")
        self.workflow_button.setObjectName("runNativeWorkflowButton")
        self.workflow_button.clicked.connect(self.run_native_workflow_check)
        footer.addWidget(self.workflow_button)
        root_layout.addLayout(footer)

        self.setCentralWidget(root)
        self.thread_pool = QThreadPool.globalInstance()
        self.provider_environment = _provider_environment_from_os()
        self._initialize_license_identity()
        self.manual_session = ManualAppSession(
            workspace or Path(tempfile.gettempdir()) / "document-vault-manual-app-session"
        )
        self._connect_workflow_controls()
        self._connect_backend_controls()
        self._report_ocr_availability()
        self._reminder_settings = self._load_reminder_settings()
        self._apply_reminder_settings_to_form()
        self._start_reminder_timer()
        self._start_connection_health_timer()
        self._refresh_connection_health()
        self._start_state_publishing()
        self._set_license_state(False, "Not activated")
        if _dev_unlock_requested():
            self._set_license_state(True, "DEVELOPMENT BUILD - license gate bypassed")

    def _build_workbench(self) -> QWidget:
        """Sidebar navigation beside the tab content.

        The tab bar itself is hidden: the sidebar drives it, and the two are
        kept in sync in both directions so programmatic ``setCurrentIndex``
        calls -- which the evidence runners and several handlers make -- still
        move the visible selection.
        """
        workbench = QWidget()
        workbench.setObjectName("workbench")
        layout = QHBoxLayout(workbench)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebarFrame")
        sidebar.setFixedWidth(200)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 12, 0, 12)
        sidebar_layout.setSpacing(4)

        branding = QLabel("JurisNuru")
        branding.setObjectName("sidebarBranding")
        branding.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sidebar_layout.addWidget(branding)

        subtitle = QLabel("Matter records for Kenyan legal practice")
        subtitle.setObjectName("sidebarSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        sidebar_layout.addWidget(subtitle)

        # Driven off the tabs so the two can never disagree about what exists.
        self._sidebar_buttons: list[QPushButton] = []
        for index in range(self.tabs.count()):
            button = QPushButton(self.tabs.tabText(index))
            button.setObjectName("sidebarNavButton")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked, i=index: self.tabs.setCurrentIndex(i))
            self._sidebar_buttons.append(button)
            sidebar_layout.addWidget(button)

        sidebar_layout.addStretch(1)

        # Imported here rather than at module scope: ui/__init__ defines
        # APP_VERSION and then imports this module, so a top-level import
        # would be circular.
        from ui import APP_VERSION

        version_label = QLabel(f"JurisNuru {APP_VERSION}")
        version_label.setObjectName("sidebarVersionLabel")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sidebar_layout.addWidget(version_label)

        layout.addWidget(sidebar)

        self.tabs.tabBar().setVisible(False)
        self.tabs.currentChanged.connect(self._sync_sidebar_selection)
        self._sync_sidebar_selection(self.tabs.currentIndex())
        layout.addWidget(self.tabs, stretch=1)
        return workbench

    def _sync_sidebar_selection(self, index: int) -> None:
        for position, button in enumerate(self._sidebar_buttons):
            button.setChecked(position == index)
        self._publish_state()

    def _initialize_license_identity(self) -> None:
        from licensing.installation import ensure_installation_identity

        identity_path = _settings_dir() / "installation.json"
        identity = ensure_installation_identity(identity_path)
        installation_label = self.findChild(QLabel, "licenseInstallationLabel")
        if installation_label is not None:
            installation_label.setText(f"Installation ID: {identity.installation_id}")

    def _apply_entitlements(self) -> None:
        """Disable the controls this licence does not pay for.

        A withheld feature is disabled and says why, rather than being hidden.
        A firm that cannot find a feature raises a support ticket; a firm that
        can see it greyed out with the reason knows what to buy.

        Local data is never gated. Reading, searching by name and exporting the
        matter record stay available regardless, because a firm's own record
        must not become unreadable when a licence lapses.
        """
        if not self._entitlements:
            return
        for name, controls in ENTITLEMENT_CONTROLS.items():
            granted = self._entitlements.get(name, False)
            for object_name in controls:
                widget = self.findChild(QPushButton, object_name)
                if widget is None:
                    continue
                widget.setEnabled(granted)
                widget.setToolTip(
                    "" if granted else f"{ENTITLEMENT_LABELS[name]} is not included in this licence"
                )
        self._publish_state()

    def _report_ocr_availability(self) -> None:
        """Say plainly whether scanned documents can be read.

        Without an engine, OCR does not fail -- it produces empty text and an
        ``ocr_status`` nobody reads, so a firm believes a scanned receipt was
        imported when nothing was captured. Silence is the failure; this makes
        it visible before anything is imported.
        """
        from core.manual_app import describe_ocr_availability

        available, detail = describe_ocr_availability()
        label = self.findChild(QLabel, "ocrStatusLabel")
        if label is not None:
            label.setText(f"OCR: {detail}" if available else f"OCR unavailable - {detail}")
        if not available:
            self.status_label.setText(
                "No OCR engine found: scanned documents will import with no text"
            )

    # ── Daily reminders ──────────────────────────────────────────────────

    def _reminder_settings_file(self) -> Path:
        return settings_path(_settings_dir())

    def _load_reminder_settings(self) -> ReminderSettings:
        return load_settings(self._reminder_settings_file())

    def _store_reminder_settings(self, settings: ReminderSettings) -> None:
        self._reminder_settings = settings
        save_settings(self._reminder_settings_file(), settings)

    def _apply_reminder_settings_to_form(self) -> None:
        """Show what is stored, so the form is not lying on first open."""
        enabled = self.findChild(QCheckBox, "dailyReminderEnabledCheckbox")
        if enabled is not None:
            enabled.setChecked(self._reminder_settings.enabled)
        time_input = self.findChild(QLineEdit, "dailyReminderTimeInput")
        if time_input is not None:
            time_input.setText(
                f"{self._reminder_settings.hour:02d}:{self._reminder_settings.minute:02d}"
            )
        horizon = self.findChild(QLineEdit, "dailyReminderHorizonInput")
        if horizon is not None:
            horizon.setText(str(self._reminder_settings.horizon_days))

    def _start_connection_health_timer(self) -> None:
        """Poll the firm backend so an outage is visible, not inferred.

        Without this, a server that has gone away shows up as an operation
        failing for no stated reason, and the firm concludes the product is
        broken rather than that the office machine is off.
        """
        self._health_timer = QTimer(self)
        self._health_timer.setInterval(30_000)
        self._health_timer.timeout.connect(self._refresh_connection_health)
        self._health_timer.start()

    def _refresh_connection_health(self) -> None:
        label = self.findChild(QLabel, "connectionHealthLabel")
        if label is None:
            return
        if self._backend_local is not None:
            label.setText("Solo - this machine")
            return
        if self._backend_client is None:
            label.setText("Not connected")
            return
        try:
            health = self._backend_client.health()
        except (WakiliOSClientError, WakiliOSConnectionError) as exc:
            label.setText("Firm backend unreachable")
            label.setToolTip(str(exc))
            return
        firm = str(health.get("firm_name") or "firm backend")
        schema = health.get("schema_version")
        label.setText(f"Connected - {firm}")
        # A seat running an older build against a migrated vault does not fail
        # to connect; it fails later, on a column it has never heard of.
        if schema is not None and int(schema) != SCHEMA_VERSION:
            label.setText(
                f"Connected - {firm} (schema {schema}, this seat expects {SCHEMA_VERSION})"
            )
        label.setToolTip("")

    def _start_reminder_timer(self) -> None:
        """Check once a minute whether today's digest is owed.

        A minute, not the automation timer's 400ms: the question is what day it
        is and whether 08:00 has passed, and nothing about that needs sub-minute
        resolution.
        """
        self._reminder_timer = QTimer(self)
        self._reminder_timer.setInterval(60_000)
        self._reminder_timer.timeout.connect(self._maybe_show_daily_reminder)
        self._reminder_timer.start()

    def _maybe_show_daily_reminder(self) -> None:
        if self._backend_local is None and self._backend_client is None:
            return
        if not due_now(self._reminder_settings, now=datetime.now(NAIROBI)):
            return
        self._show_daily_reminder()

    def _on_show_reminder_now(self) -> None:
        """Raise the digest whatever the schedule says.

        Present for support calls and for the packaged evidence run: without it
        the only way to see this surface is to wait for a wall clock.
        """
        if self._backend_local is None and self._backend_client is None:
            self.status_label.setText("Start solo mode or connect to a server first")
            return
        self._show_daily_reminder()

    def _show_daily_reminder(self) -> None:
        horizon = max(1, self._reminder_settings.horizon_days)
        start = _today_iso()
        end = (datetime.now(NAIROBI).date() + timedelta(days=horizon)).isoformat()
        try:
            entries = self._backend_upcoming(start, end)
        except (WakiliOSError, WakiliOSClientError, WakiliOSConnectionError) as exc:
            # Do not mark the day shown: a server that was down at 08:00 should
            # still produce a digest once it is reachable.
            self.status_label.setText(f"Could not read today's matters: {exc}")
            return

        self._reminder_entries = entries
        self._store_reminder_settings(
            mark_shown(self._reminder_settings, now=datetime.now(NAIROBI))
        )
        self.status_label.setText(summarise_reminders(entries))
        self._notify_tray(summarise_reminders(entries))
        self._publish_state()

        dialog = DailyReminderDialog(entries, self)
        dialog.exec()
        if dialog.snoozed:
            from ui.reminders import snooze as snooze_settings

            self._store_reminder_settings(
                snooze_settings(self._reminder_settings, now=datetime.now(NAIROBI))
            )
            self.status_label.setText("Reminder snoozed for an hour.")
        elif dialog.selected_matter_id:
            self._open_matter_by_id(dialog.selected_matter_id)
        self._publish_state()

    def _notify_tray(self, message: str) -> None:
        """Nudge through the system tray where the platform has one.

        Secondary to the dialog by design: there is no tray at all under the
        offscreen platform, and Windows Focus Assist drops toasts without
        telling anyone.
        """
        from PySide6.QtWidgets import QSystemTrayIcon

        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        if getattr(self, "_tray_icon", None) is None:
            from PySide6.QtWidgets import QStyle

            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation)
            self._tray_icon = QSystemTrayIcon(icon, self)
            self._tray_icon.setToolTip("JurisNuru")
            self._tray_icon.show()
        if self._tray_icon.supportsMessages():
            self._tray_icon.showMessage("JurisNuru", message)

    def _on_save_reminder_settings(self) -> None:
        enabled = self.findChild(QCheckBox, "dailyReminderEnabledCheckbox")
        time_input = self.findChild(QLineEdit, "dailyReminderTimeInput")
        horizon_input = self.findChild(QLineEdit, "dailyReminderHorizonInput")
        raw_time = time_input.text().strip() if time_input else ""
        hour, _, minute = raw_time.partition(":")
        try:
            parsed_hour, parsed_minute = int(hour), int(minute or 0)
            if not (0 <= parsed_hour <= 23 and 0 <= parsed_minute <= 59):
                raise ValueError(raw_time)
        except ValueError:
            self.status_label.setText("Reminder time must be HH:MM, for example 08:00.")
            return
        try:
            horizon = max(1, int(horizon_input.text().strip())) if horizon_input else 1
        except ValueError:
            self.status_label.setText("Days ahead must be a whole number.")
            return
        # Changing the schedule clears "already shown today", so moving the time
        # forward takes effect now rather than tomorrow.
        self._store_reminder_settings(
            ReminderSettings(
                enabled=bool(enabled.isChecked()) if enabled else True,
                hour=parsed_hour,
                minute=parsed_minute,
                horizon_days=horizon,
                snooze_minutes=self._reminder_settings.snooze_minutes,
            )
        )
        self.status_label.setText(
            f"Daily reminders {'on' if self._reminder_settings.enabled else 'off'}, "
            f"from {parsed_hour:02d}:{parsed_minute:02d}."
        )
        self._publish_state()

    def _open_matter_by_id(self, matter_id: str) -> None:
        """Jump to a matter named in the digest."""
        if not matter_id:
            return
        self._current_matter_id = matter_id
        self.tabs.setCurrentIndex(0)
        self._refresh_matter_workspace()

    def _start_state_publishing(self) -> None:
        """Publish state on a timer while an automated harness is driving.

        Hand-placing a publish call in every handler misses the ones nobody
        thought about, and a harness then asserts against a stale snapshot --
        reading "Reports refreshed" while looking at the selftest, or a review
        queue that never appears to grow. A timer covers every handler,
        including ones added later.

        Off unless automation is enabled, so a normal session does no extra
        work.
        """
        if not automation_enabled():
            return
        self._state_timer = QTimer(self)
        self._state_timer.setInterval(400)
        self._state_timer.timeout.connect(self._publish_state)
        self._state_timer.start()

    def _publish_state(self) -> None:
        """Publish what the window currently holds, for an automated harness.

        A harness that scrapes label text is reading prose written for humans
        and inferring state from it. This reports the state directly, so a test
        asserts on what the application believes rather than on how it phrased
        it.
        """
        if not automation_enabled():
            return
        # Publishing is wired to widget signals, some of which fire while the
        # window is still being built.
        if not hasattr(self, "status_label") or not hasattr(self, "application_stack"):
            return

        def rows(object_name: str) -> list[str]:
            listing = self.findChild(QListWidget, object_name)
            if listing is None:
                return []
            return [listing.item(i).text() for i in range(listing.count())]

        tabs = {view.object_name: rows(f"{view.object_name}List") for view in MATTER_TAB_VIEWS}
        summary = self.findChild(QTextEdit, "aiMatterSummaryOutput")
        write_state(
            {
                "license_active": self._license_active,
                "ocr_available": __import__(
                    "core.manual_app", fromlist=["describe_ocr_availability"]
                ).describe_ocr_availability()[0],
                "entitlements": dict(self._entitlements),
                "gate_index": self.application_stack.currentIndex(),
                "destination": self.tabs.tabText(self.tabs.currentIndex()),
                "destination_index": self.tabs.currentIndex(),
                "destinations": [self.tabs.tabText(i) for i in range(self.tabs.count())],
                "backend": (
                    "solo"
                    if self._backend_local is not None
                    else ("firm" if self._backend_client is not None else "none")
                ),
                "role": self._current_role,
                "username": self._current_username,
                "current_matter_id": self._current_matter_id,
                "matters": rows("matterList"),
                "matter_tabs": tabs,
                "filing_record_page": rows("filingRecordPageList"),
                "review_queue": rows("documentReviewQueue"),
                "audit_events": len(rows("auditLogList")),
                "matter_summary": summary.toPlainText() if summary is not None else "",
                "daily_reminder": {
                    "enabled": self._reminder_settings.enabled,
                    "hour": self._reminder_settings.hour,
                    "minute": self._reminder_settings.minute,
                    "horizon_days": self._reminder_settings.horizon_days,
                    "last_shown_date": self._reminder_settings.last_shown_date,
                    "snoozed_until": self._reminder_settings.snoozed_until,
                    "due": due_now(self._reminder_settings, now=datetime.now(NAIROBI)),
                    "entry_count": len(self._reminder_entries),
                    "entries": [_reminder_row(entry) for entry in self._reminder_entries],
                },
                "matter_ai_sources": (
                    sources.text()
                    if (sources := self.findChild(QLabel, "matterAiSourcesLabel"))
                    else ""
                ),
                "status": self.status_label.text(),
            }
        )

    def _set_license_state(self, active: bool, status: str) -> None:
        self._license_active = active
        status_label = self.findChild(QLabel, "licenseStatusLabel")
        if status_label is not None:
            status_label.setText(status)
        self.application_stack.setCurrentIndex(1 if active else 0)
        if active:
            self.tabs.setCurrentIndex(0)
        self._publish_state()

    @Slot()
    def activate_license(self) -> None:
        from licensing.core import (
            embedded_public_key_pem,
            read_license_file,
            verify_license_document,
        )
        from licensing.installation import ensure_installation_identity

        license_input = self.findChild(QLineEdit, "licenseFileInput")
        license_path = Path(license_input.text().strip()) if license_input else Path()
        if not license_path.is_file():
            message = "License file not found. Select a signed license.key file."
            self._set_license_state(False, message)
            self.status_label.setText(message)
            return
        try:
            identity_path = _settings_dir() / "installation.json"
            identity = ensure_installation_identity(identity_path)
            raw_license = license_path.read_bytes()
            if license_path.suffix.lower() == ".pem" or b"BEGIN PUBLIC KEY" in raw_license:
                message = (
                    "This is the public verification key, not a license. "
                    "Select a vendor-issued signed license.key file."
                )
                self._set_license_state(False, message)
                self.status_label.setText(message)
                return
            try:
                license_payload = json.loads(raw_license.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                license_payload = None
            if (
                isinstance(license_payload, dict)
                and "installation_id" in license_payload
                and "signature" not in license_payload
            ):
                message = (
                    "This is the installation identity, not a license. "
                    "Select a vendor-issued signed license.key file."
                )
                self._set_license_state(False, message)
                self.status_label.setText(message)
                return
            document = read_license_file(license_path)
            result = verify_license_document(
                document,
                embedded_public_key_pem(),
                identity.installation_id,
            )
        except json.JSONDecodeError:
            message = "License file is not valid JSON. Select a vendor-issued signed license.key."
            self._set_license_state(False, message)
            self.status_label.setText(message)
            return
        except (KeyError, TypeError, ValueError):
            message = "License file is malformed. Select a vendor-issued signed license.key."
            self._set_license_state(False, message)
            self.status_label.setText(message)
            return
        except Exception:
            message = "License could not be read. Select a vendor-issued signed license.key."
            self._set_license_state(False, message)
            self.status_label.setText(message)
            return
        if not result.is_active:
            messages = {
                "bad_signature": "Invalid license - contact the license issuer.",
                "installation_mismatch": (
                    "This license is already bound to another installation. "
                    "Request a license for this Installation ID."
                ),
                "expired": "Invalid license - contact the license issuer.",
                "disabled": "This license is inactive or disabled. Contact the license issuer.",
                "malformed": "Invalid license - contact the license issuer.",
            }
            message = messages.get(
                result.status,
                "Invalid license - contact the license issuer.",
            )
            self._set_license_state(False, message)
            self.status_label.setText(message)
            return
        self._entitlements = {
            name: bool(getattr(document.features, name, False)) for name in ENTITLEMENT_CONTROLS
        }
        self._set_license_state(True, f"Active: {document.firm_display_name} ({document.plan})")
        self._apply_entitlements()
        withheld = [
            ENTITLEMENT_LABELS[name]
            for name, granted in sorted(self._entitlements.items())
            if not granted
        ]
        self.status_label.setText(
            f"License activated ({document.plan}); not included: {', '.join(withheld)}"
            if withheld
            else f"License activated; {document.plan} plan includes every feature"
        )

    @Slot()
    def copy_installation_id(self) -> None:
        """Put the installation ID on the clipboard, ready to send to the supplier."""
        label = self.findChild(QLabel, "licenseInstallationLabel")
        if label is None:
            return
        identity = label.text().replace("Installation ID:", "").strip()
        if not identity:
            self.status_label.setText("Installation identity is not ready yet")
            return
        QApplication.clipboard().setText(identity)
        self.status_label.setText(f"Installation ID copied: {identity}")

    def browse_for_license(self) -> None:
        selected = _choose_file(
            self, "Select signed license", "License files (*.key *.json);;All files (*)"
        )
        if selected:
            license_input = self.findChild(QLineEdit, "licenseFileInput")
            if license_input is not None:
                license_input.setText(selected)
            self.status_label.setText("License file selected; click Activate license")

    def _connect_workflow_controls(self) -> None:
        """Wire up the existing workflow control buttons."""
        button_actions = {
            "completeSetupButton": "Setup complete",
            "initializeVaultButton": "Vault initialization checked",
            "newMatterButton": "JurisNuru matter workflow checked",
            "exportCalendarButton": "Matter calendar export checked",
            "runOcrButton": "OCR workflow checked",
        }
        for object_name, message in button_actions.items():
            button = self.findChild(QPushButton, object_name)
            if button is not None:
                button.clicked.connect(
                    lambda _checked=False, text=message: self.status_label.setText(text)
                )

        activate_button = self.findChild(QPushButton, "activateLicenseButton")
        if activate_button is not None:
            activate_button.clicked.connect(self.activate_license)

        copy_button = self.findChild(QPushButton, "copyInstallationIdButton")
        if copy_button is not None:
            copy_button.clicked.connect(self.copy_installation_id)

        browse_button = self.findChild(QPushButton, "browseLicenseButton")
        if browse_button is not None:
            browse_button.clicked.connect(self.browse_for_license)

        save_provider_button = self.findChild(QPushButton, "saveProviderSettingsButton")
        if save_provider_button is not None:
            save_provider_button.clicked.connect(self._save_provider_settings)

        add_files_button = self.findChild(QPushButton, "addFilesButton")
        if add_files_button is not None:
            add_files_button.clicked.connect(self.choose_and_import_files)
        ask_button = self.findChild(QPushButton, "askRagButton")
        if ask_button is not None:
            ask_button.clicked.connect(self.ask_current_question)
        backup_button = self.findChild(QPushButton, "createBackupButton")
        if backup_button is not None:
            backup_button.clicked.connect(self.create_backup_and_restore)
        restore_button = self.findChild(QPushButton, "restoreDrillButton")
        if restore_button is not None:
            restore_button.clicked.connect(self.create_backup_and_restore)
        admin_sync_button = self.findChild(QPushButton, "adminSyncButton")
        if admin_sync_button is not None:
            admin_sync_button.clicked.connect(self.check_admin_license_payment_status)

    def _connect_backend_controls(self) -> None:
        """Wire up the backend connection and matter workspace controls."""
        connect_button = self.findChild(QPushButton, "connectButton")
        if connect_button is not None:
            dialog = self.findChild(BackendConnectionDialog)
            if dialog is not None:
                dialog.login_succeeded.connect(self._on_backend_login)
                dialog.solo_mode_started.connect(self._on_solo_mode_started)

        for _tab_name, button_name, handler in [
            ("Matters", "newMatterButton", self._on_new_matter),
            ("Matters", "exportCalendarButton", self._on_export_calendar),
            ("Matters", "refreshMatterListButton", self._on_refresh_matters),
        ]:
            button = self.findChild(QPushButton, button_name)
            if button is not None:
                button.clicked.connect(handler)

        for view in MATTER_TAB_VIEWS:
            if not view.addable:
                continue
            button = self.findChild(QPushButton, f"{view.object_name}AddButton")
            if button is not None:
                button.clicked.connect(lambda _checked=False, v=view: self._on_add_record(v))

        filing_view = next(v for v in MATTER_TAB_VIEWS if v.object_name == "filingRecordTab")
        page_add = self.findChild(QPushButton, "filingRecordPageAddButton")
        if page_add is not None:
            page_add.clicked.connect(lambda _=False, v=filing_view: self._on_add_record(v))
        page_refresh = self.findChild(QPushButton, "filingRecordPageRefreshButton")
        if page_refresh is not None:
            page_refresh.clicked.connect(self._refresh_matter_workspace)
        page_export = self.findChild(QPushButton, "filingRecordPageExportButton")
        if page_export is not None:
            page_export.clicked.connect(self._on_export_calendar)

        from_document_button = self.findChild(QPushButton, "newMatterFromDocumentButton")
        if from_document_button is not None:
            from_document_button.clicked.connect(self._on_new_matter_from_document)

        matter_ai_button = self.findChild(QPushButton, "matterAiAskButton")
        if matter_ai_button is not None:
            matter_ai_button.clicked.connect(self._on_ask_matter_ai)

        for button_name, reminder_handler in (
            ("saveReminderSettingsButton", self._on_save_reminder_settings),
            ("testDailyReminderButton", self._on_show_reminder_now),
        ):
            reminder_button = self.findChild(QPushButton, button_name)
            if reminder_button is not None:
                reminder_button.clicked.connect(reminder_handler)

        generate_button = self.findChild(QPushButton, "generateSummaryButton")
        if generate_button is not None:
            generate_button.clicked.connect(self._on_generate_summary)

        reports_button = self.findChild(QPushButton, "refreshReportsButton")
        if reports_button is not None:
            reports_button.clicked.connect(self._on_refresh_reports)

        matter_list = self.findChild(QListWidget, "matterList")
        if matter_list is not None:
            matter_list.currentItemChanged.connect(
                lambda current, _previous: self._on_matter_selected(current)
            )

        # Document upload
        upload_btn = self.findChild(QPushButton, "uploadDocumentButton")
        if upload_btn is not None:
            upload_btn.clicked.connect(self._on_upload_document)

        # Audit log refresh
        audit_btn = self.findChild(QPushButton, "refreshAuditLogButton")
        if audit_btn is not None:
            audit_btn.clicked.connect(self._on_refresh_audit_log)

    @Slot(str, str, str)
    def _on_backend_login(self, token: str, username: str, role: str) -> None:
        url_input = self.findChild(QLineEdit, "serverUrlInput")
        url = url_input.text().strip() if url_input else "http://localhost:8000"
        self._backend_client = WakiliOSClient(
            WakiliOSClientConfig(base_url=url, session_token=token)
        )
        self._backend_local = None
        self._current_role = role
        self._current_username = username
        role_label = self.findChild(QLabel, "roleStatusLabel")
        if role_label is not None:
            role_label.setText(f"Role: {role}")
        self.status_label.setText(f"Connected to backend as {username} ({role})")
        self._apply_role_permissions(role)
        self._publish_state()

    @Slot(str, str)
    def _on_solo_mode_started(self, username: str, role: str) -> None:
        """Handle solo mode: initialize local backend directly, no HTTP needed."""
        # Keep the solo backend out of the shared temp directory. A fixed path
        # under gettempdir() is world-writable and survives between runs, so a
        # second launch reopened a database another process still held.
        if self._workspace_root is not None:
            solo_root = self._workspace_root / "solo-backend"
        else:
            app_data = Path(os.environ.get("APPDATA", tempfile.gettempdir()))
            solo_root = app_data / "WakiliOS" / "solo-backend"
        self._backend_local = initialize_firm_backend(
            solo_root,
            firm_name="Solo Practice",
            admin_username=username,
            admin_password="admin-pass",
            vault_passphrase="solo vault passphrase",
            max_seats=1,
        )
        self._backend_client = None  # No HTTP client in solo mode
        self._current_role = role
        self._current_username = username
        role_label = self.findChild(QLabel, "roleStatusLabel")
        if role_label is not None:
            role_label.setText(f"Role: {role} (solo)")
        self.status_label.setText(f"Running in solo mode as {username} ({role})")
        self._apply_role_permissions(role)
        self._publish_state()

    def _apply_role_permissions(self, role: str) -> None:
        """Enable/disable controls based on user role."""
        from wakilios.core import ACCOUNTS_ROLES, SUMMARY_ROLES, WRITE_ROLES

        can_write = role in WRITE_ROLES
        can_manage_fees = role in ACCOUNTS_ROLES
        can_summarize = role in SUMMARY_ROLES

        fee_add = self.findChild(QPushButton, "feesAddButton")
        if fee_add is not None:
            fee_add.setEnabled(can_manage_fees)
        receipt_add = self.findChild(QPushButton, "receiptsAddButton")
        if receipt_add is not None:
            receipt_add.setEnabled(can_manage_fees)
        for tab_name in ["partiesAddButton", "activitiesAddButton", "lodgingsAddButton"]:
            button = self.findChild(QPushButton, tab_name)
            if button is not None:
                button.setEnabled(can_write)
        summary_add = self.findChild(QPushButton, "summaryAddButton")
        if summary_add is not None:
            summary_add.setEnabled(can_summarize)
        new_matter = self.findChild(QPushButton, "newMatterButton")
        if new_matter is not None:
            new_matter.setEnabled(can_write)
        # A role may narrow what a licence grants; it may never widen it.
        self._apply_entitlements()

    def _solo_token(self) -> str:
        """Get a session token for solo mode operations."""
        if self._backend_local is not None:
            session = self._backend_local.login(self._current_username, "admin-pass")
            return session.token
        return ""

    def _backend_create_matter(self, **fields: str) -> dict:
        """Create a matter via local backend or HTTP client."""
        if self._backend_local is not None:
            return self._backend_local.create_litigation_matter(
                self._solo_token(),
                **fields,
            )
        if self._backend_client is not None:
            return self._backend_client.create_matter(**fields)
        return {}

    def _backend_list_matters(self) -> list:
        """List matters via local backend or HTTP client."""
        if self._backend_local is not None:
            token = self._solo_token()
            cache = self._backend_local.build_offline_cache(token)
            return list(cache.matters)
        if self._backend_client is not None:
            return self._backend_client.list_matters()
        return []

    def _backend_workspace(self, matter_id: str) -> dict:
        """Get workspace via local backend or HTTP client."""
        if self._backend_local is not None:
            return self._backend_local.workspace(self._solo_token(), matter_id)
        if self._backend_client is not None:
            return self._backend_client.workspace(matter_id)
        return {}

    def _backend_add_party(self, matter_id: str, **fields: str) -> dict:
        if self._backend_local is not None:
            return self._backend_local.add_party(self._solo_token(), matter_id, **fields)
        if self._backend_client is not None:
            return self._backend_client.add_party(matter_id, **fields)
        return {}

    def _backend_add_activity(self, matter_id: str, **fields: object) -> dict:
        if self._backend_local is not None:
            return self._backend_local.add_activity(self._solo_token(), matter_id, **fields)
        if self._backend_client is not None:
            return self._backend_client.add_activity(matter_id, **fields)
        return {}

    def _backend_add_lodging(self, matter_id: str, **fields: str) -> dict:
        if self._backend_local is not None:
            return self._backend_local.add_lodging(self._solo_token(), matter_id, **fields)
        if self._backend_client is not None:
            return self._backend_client.add_lodging(matter_id, **fields)
        return {}

    def _backend_add_court_decision(self, matter_id: str, **fields: str) -> dict:
        if self._backend_local is not None:
            return self._backend_local.add_court_decision(self._solo_token(), matter_id, **fields)
        if self._backend_client is not None:
            return self._backend_client.add_court_decision(matter_id, **fields)
        return {}

    def _backend_firm_overview(self) -> dict:
        if self._backend_local is not None:
            return self._backend_local.firm_overview(self._solo_token())
        if self._backend_client is not None:
            return self._backend_client.firm_overview()
        return {}

    def _backend_add_filing_record(self, matter_id: str, **fields: str) -> dict:
        if self._backend_local is not None:
            return self._backend_local.add_filing_record(self._solo_token(), matter_id, **fields)
        if self._backend_client is not None:
            return self._backend_client.add_filing_record(matter_id, **fields)
        return {}

    def _backend_add_fee(self, matter_id: str, **fields: object) -> dict:
        if self._backend_local is not None:
            return self._backend_local.add_fee(self._solo_token(), matter_id, **fields)
        if self._backend_client is not None:
            return self._backend_client.add_fee(matter_id, **fields)
        return {}

    def _backend_add_receipt(self, matter_id: str, **fields: object) -> dict:
        if self._backend_local is not None:
            return self._backend_local.add_receipt(self._solo_token(), matter_id, **fields)
        if self._backend_client is not None:
            return self._backend_client.add_receipt(matter_id, **fields)
        return {}

    def _backend_update_summary(self, matter_id: str, summary: str) -> dict:
        if self._backend_local is not None:
            return self._backend_local.update_matter_summary(self._solo_token(), matter_id, summary)
        if self._backend_client is not None:
            return self._backend_client.update_matter_summary(matter_id, summary)
        return {}

    def _backend_export_calendar(self, matter_id: str) -> str:
        if self._backend_local is not None:
            return self._backend_local.export_calendar_ics(self._solo_token(), matter_id)
        if self._backend_client is not None:
            return self._backend_client.export_calendar(matter_id)
        return ""

    def _backend_upcoming(
        self, start: str, end: str, matter_id: str = "", limit: int = 500
    ) -> list[dict]:
        """Dated obligations across every matter, ``start`` inclusive, ``end`` exclusive."""
        if self._backend_local is not None:
            return self._backend_local.upcoming_dates(
                self._solo_token(), start=start, end=end, matter_id=matter_id, limit=limit
            )
        if self._backend_client is not None:
            return self._backend_client.upcoming(start, end, matter_id=matter_id, limit=limit)
        return []

    def _backend_audit_log(self) -> dict:
        if self._backend_local is not None:
            events = self._backend_local.audit_events(self._solo_token())
            return {"events": events}
        if self._backend_client is not None:
            return self._backend_client.audit_log()
        return {"events": []}

    def _on_new_matter(self) -> None:
        """Open a matter, with the form blank."""
        self._create_matter_from(prefill={}, source="")

    def _on_new_matter_from_document(self) -> None:
        """Open a matter by reading its heading off a filing.

        The case number, parties, court and station are printed on the first
        page of every filing. Retyping them is the tax the product exists to
        remove.
        """
        if self._backend_local is None and self._backend_client is None:
            self.status_label.setText("Start solo mode or connect to a server first")
            return
        selected = _choose_file(
            self, "Open a matter from a document", "Documents (*.pdf *.docx);;All files (*)"
        )
        if not selected:
            return

        from core.manual_app import resolve_ocr_engine
        from intake.extraction import ExtractionError, extract_text
        from intake.matter_details import extract_matter_details

        source = Path(selected)
        try:
            extraction = extract_text(source, ocr_engine=resolve_ocr_engine(source))
        except ExtractionError as exc:
            self.status_label.setText(f"Could not read {source.name}: {exc}")
            return

        details = extract_matter_details(extraction.text)
        if details.is_empty:
            self.status_label.setText(
                f"No court heading found in {source.name}; opening a blank matter"
            )
        else:
            self.status_label.setText(
                f"Read {len(details.found)} field(s) from {source.name}: {', '.join(details.found)}"
            )
        self._create_matter_from(prefill=details.as_fields(), source=str(source))

    def _create_matter_from(self, *, prefill: dict[str, str], source: str) -> None:
        if self._backend_local is None and self._backend_client is None:
            self.status_label.setText("Start solo mode or connect to a server first")
            return

        dialog = MatterDialog(prefill, source=source, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        fields = dialog.values()
        try:
            result = self._backend_create_matter(
                internal_reference=fields.get("internal_reference", "") or _next_reference(),
                client_name=fields.get("client_name", ""),
                parties=fields.get("parties", ""),
                court=fields.get("court", ""),
                station=fields.get("station", ""),
                case_number=fields.get("case_number", ""),
                practice_area=fields.get("practice_area", ""),
                responsible_advocate=self._current_username,
                filing_status=fields.get("filing_status", "draft"),
                filing_date=fields.get("filing_date", ""),
            )
            self._current_matter_id = str(result.get("matter_id", ""))
            self.status_label.setText(
                f"Created matter: {result.get('internal_reference', self._current_matter_id)}"
            )
            self._on_refresh_matters()
            self._refresh_matter_workspace()
        except (WakiliOSClientError, WakiliOSConnectionError, Exception) as exc:
            self.status_label.setText(f"Failed to create matter: {exc}")
        self._publish_state()

    def _on_export_calendar(self) -> None:
        if self._backend_local is None and self._backend_client is None:
            self.status_label.setText("Start solo mode or connect to a server first")
            return
        if not self._current_matter_id:
            self.status_label.setText("Select a matter first")
            return
        try:
            ics = self._backend_export_calendar(self._current_matter_id)
            dest = _choose_save_path(self, "Save Calendar", "Calendar Files (*.ics)")
            if dest:
                Path(dest).write_text(ics, encoding="utf-8")
                self.status_label.setText(f"Calendar exported to {dest}")
        except (WakiliOSClientError, WakiliOSConnectionError, Exception) as exc:
            self.status_label.setText(f"Calendar export failed: {exc}")

    def _on_refresh_matters(self) -> None:
        if self._backend_local is None and self._backend_client is None:
            self.status_label.setText("Start solo mode or connect to a server first")
            return
        try:
            matters = self._backend_list_matters()
            matter_list = self.findChild(QListWidget, "matterList")
            if matter_list is not None:
                matter_list.clear()
                for m in matters:
                    ref = m.get("internal_reference", "")
                    client = m.get("client_name", "")
                    item = QListWidgetItem(f"{ref} - {client}")
                    # Carry the id so selecting a row can open that matter.
                    item.setData(Qt.ItemDataRole.UserRole, str(m.get("matter_id", "")))
                    matter_list.addItem(item)
        except (WakiliOSClientError, WakiliOSConnectionError, Exception) as exc:
            self.status_label.setText(f"Failed to list matters: {exc}")
        self._publish_state()

    def _on_matter_selected(self, item: QListWidgetItem | None) -> None:
        """Open the selected matter in the workspace tabs."""
        if item is None:
            return
        matter_id = item.data(Qt.ItemDataRole.UserRole)
        if not matter_id:
            return
        self._current_matter_id = str(matter_id)
        self.status_label.setText(f"Opened matter: {item.text()}")
        self._refresh_matter_workspace()

    def _on_ask_matter_ai(self) -> None:
        """Answer a question from this matter's documents, or decline.

        Scoped to the open matter, and refuses rather than guessing when the
        matter has nothing to answer from. An answer with no source is the
        failure this panel exists to prevent, so it is never rendered as one.
        """
        question_box = self.findChild(QTextEdit, "matterAiQuestionInput")
        answer_box = self.findChild(QTextEdit, "matterAiAnswerOutput")
        sources_label = self.findChild(QLabel, "matterAiSourcesLabel")
        if question_box is None or answer_box is None or sources_label is None:
            return
        if not self._current_matter_id:
            answer_box.setPlainText("")
            sources_label.setText("Open a matter first")
            return
        question = question_box.toPlainText().strip()
        if not question:
            sources_label.setText("Type a question about this matter")
            return

        from rag import build_answer_packet, build_rag_index

        # The matter's documents live in the backend's vault, not the manual
        # session's. Indexing the wrong one answers every question with
        # "no source", which reads like a careful refusal and is really a bug.
        if self._backend_local is None:
            answer_box.setPlainText("")
            sources_label.setText(
                "Matter search runs against the local vault; connect in solo mode to use it"
            )
            return

        try:
            vault_root = self._backend_local.vault_root
            build_rag_index(vault_root, matter_id=self._current_matter_id)
            packet = build_answer_packet(vault_root, question, matter_id=self._current_matter_id)
        except Exception as exc:
            answer_box.setPlainText("")
            sources_label.setText(f"Could not search this matter: {exc}")
            return

        citations = tuple(getattr(packet, "citations", ()) or ())
        if not citations:
            answer_box.setPlainText(
                "No document in this matter supports an answer to that question."
            )
            sources_label.setText("Sources: none - nothing was answered")
            self._publish_state()
            return

        # The packet is retrieval, not generation: it carries the passages that
        # support an answer and a safety notice, not prose. Rendering it as an
        # "answer" would claim more than the system did.
        passages = str(getattr(packet, "grounded_context", "") or "").strip()
        notice = str(getattr(packet, "safety_notice", "") or "").strip()
        answer_box.setPlainText("\n\n".join(part for part in (passages, notice) if part))
        confidence = float(getattr(packet, "confidence", 0.0) or 0.0)
        titles = []
        for citation in citations:
            title = str(getattr(citation, "document_title", "") or getattr(citation, "title", ""))
            if title and title not in titles:
                titles.append(title)
        sources_label.setText(
            f"Sources: {len(citations)} passage(s) from {len(titles)} document(s) "
            f"in this matter (confidence {confidence:.2f})"
        )
        self._publish_state()

    def _on_generate_summary(self) -> None:
        """Draft a matter summary from what the matter already holds.

        Deliberately built from the recorded facts -- parties, court, filing
        record, next action, document and fee counts -- rather than free
        generation. A summary that invents a next hearing date is worse than no
        summary, and this one can be checked line by line against the tabs.
        """
        if (
            self._backend_local is None and self._backend_client is None
        ) or not self._current_matter_id:
            self.status_label.setText("Open a matter first")
            return
        summary_box = self.findChild(QTextEdit, "aiMatterSummaryOutput")
        if summary_box is None:
            return
        try:
            workspace = self._backend_workspace(self._current_matter_id)
        except (WakiliOSClientError, WakiliOSConnectionError, Exception) as exc:
            self.status_label.setText(f"Could not read the matter: {exc}")
            return

        summary = _draft_matter_summary(workspace)
        summary_box.setPlainText(summary)
        self.status_label.setText("Summary drafted from the matter record; review before saving")
        self._publish_state()

    def _on_update_summary(self) -> None:
        if (
            self._backend_local is None and self._backend_client is None
        ) or not self._current_matter_id:
            return
        summary_box = self.findChild(QTextEdit, "aiMatterSummaryOutput")
        if summary_box is None:
            return
        try:
            self._backend_update_summary(self._current_matter_id, summary_box.toPlainText())
            self.status_label.setText("Summary updated")
        except (WakiliOSClientError, WakiliOSConnectionError, Exception) as exc:
            self.status_label.setText(f"Summary update failed: {exc}")

    def _on_upload_document(self) -> None:
        if self._backend_local is None and self._backend_client is None:
            self.status_label.setText("Start solo mode or connect to a server first")
            return
        if not self._current_matter_id:
            self.status_label.setText("Select a matter first")
            return
        file_paths = _choose_files(
            self,
            "Upload document to matter",
            "Documents (*.pdf *.docx *.doc *.png *.jpg *.jpeg *.tif *.tiff *.txt);;All files (*)",
        )
        if not file_paths:
            return
        for file_path in file_paths:
            try:
                if self._backend_local is not None:
                    token = self._backend_local.login(self._current_username, "admin-pass").token
                    source = Path(file_path)
                    content = source.read_bytes()
                    result = self._backend_local.upload_document(
                        token,
                        self._current_matter_id,
                        title=source.name,
                        document_type="general",
                        content=content,
                        original_name=source.name,
                        content_type="application/octet-stream",
                        extracted_text=_extracted_text_for(source),
                    )
                elif self._backend_client is not None:
                    result = self._backend_client.upload_document(
                        self._current_matter_id, file_path
                    )
                else:
                    continue
                doc_id = result.get("document_id", "?")
                self.status_label.setText(f"Uploaded document: {doc_id}")
            except (WakiliOSClientError, WakiliOSConnectionError, Exception) as exc:
                self.status_label.setText(f"Document upload failed: {exc}")
                return
        # Refresh document list
        self._refresh_matter_workspace()

    _ADD_DISPATCH: dict[str, str] = {
        "partiesTab": "_backend_add_party",
        "activitiesTab": "_backend_add_activity",
        "lodgingsTab": "_backend_add_lodging",
        "courtDecisionsTab": "_backend_add_court_decision",
        "feesTab": "_backend_add_fee",
        "receiptsTab": "_backend_add_receipt",
        "filingRecordTab": "_backend_add_filing_record",
    }

    def _on_add_record(self, view: MatterTabView) -> None:
        """Collect a record from the user and store it against the matter.

        These handlers used to write a fixed placeholder row -- "New Party",
        "NEW-RCT", amount 0 -- which demonstrated the round trip but could not
        record anything real.
        """
        if self._backend_local is None and self._backend_client is None:
            self.status_label.setText("Start solo mode or connect to a server first")
            return
        if not self._current_matter_id:
            self.status_label.setText("Open a matter first")
            return

        dialog = MatterRecordDialog(view, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        fields = dialog.values()
        if not fields:
            self.status_label.setText(f"Nothing entered; no {view.label.lower()} added")
            return

        method = getattr(self, self._ADD_DISPATCH[view.object_name])
        try:
            method(self._current_matter_id, **fields)
            self.status_label.setText(f"{view.label} record added")
            self._refresh_matter_workspace()
        except (WakiliOSClientError, WakiliOSConnectionError, Exception) as exc:
            self.status_label.setText(f"Add {view.label.lower()} failed: {exc}")

    def _on_refresh_fee_receipt_view(self) -> None:
        """Backwards-compatible alias for the full workspace refresh."""
        self._refresh_matter_workspace()

    def _refresh_matter_workspace(self) -> None:
        """Repopulate every matter sub-tab from the backend.

        ``workspace()`` already returns all eight collections in one call, so
        each tab is a formatter over the payload rather than its own request.
        """
        if (
            self._backend_local is None and self._backend_client is None
        ) or not self._current_matter_id:
            return
        try:
            workspace = self._backend_workspace(self._current_matter_id)
        except (WakiliOSClientError, WakiliOSConnectionError, Exception) as exc:
            self.status_label.setText(f"Failed to refresh matter workspace: {exc}")
            return

        # The Filing record destination shows the same records as the matter
        # sub-tab, so a user who navigates there sees the open matter rather
        # than a permanent placeholder.
        page_list = self.findChild(QListWidget, "filingRecordPageList")
        if page_list is not None:
            page_list.clear()
            records = workspace.get("filing_records") or []
            filing_view = next(v for v in MATTER_TAB_VIEWS if v.object_name == "filingRecordTab")
            if records:
                for row in records:
                    page_list.addItem(filing_view.format_row(row))
            else:
                page_list.addItem("No filing recorded for this matter yet")
        self._publish_state()
        matter_label = self.findChild(QLabel, "filingRecordMatterLabel")
        if matter_label is not None:
            matter = workspace.get("matter") or {}
            reference = str(matter.get("internal_reference") or self._current_matter_id)
            case_number = str(matter.get("case_number") or "")
            matter_label.setText(f"{reference} - {case_number}" if case_number else str(reference))

        for view in MATTER_TAB_VIEWS:
            listing = self.findChild(QListWidget, f"{view.object_name}List")
            if listing is None:
                continue
            listing.clear()
            rows = workspace.get(view.workspace_key) or []
            if not rows:
                listing.addItem(view.empty_text)
                continue
            for row in rows:
                listing.addItem(view.format_row(row))

    def _on_refresh_reports(self) -> None:
        """Fill the Reports destination from the firm-wide aggregate."""
        if self._backend_local is None and self._backend_client is None:
            self.status_label.setText("Start solo mode or connect to a server first")
            return
        try:
            overview = self._backend_firm_overview()
        except (WakiliOSClientError, WakiliOSConnectionError, Exception) as exc:
            self.status_label.setText(f"Failed to load reports: {exc}")
            return
        currency = "KES"
        for object_name, text in (
            ("reportMattersLabel", str(overview.get("matters", 0))),
            ("reportDocumentsLabel", str(overview.get("documents", 0))),
            ("reportFilingRecordsLabel", str(overview.get("filing_records", 0))),
            ("reportFeesLabel", f"{currency} {overview.get('fees_raised', 0):,.2f}"),
            ("reportReceiptsLabel", f"{currency} {overview.get('receipts_total', 0):,.2f}"),
            ("reportBalanceLabel", f"{currency} {overview.get('balance', 0):,.2f}"),
        ):
            target = self.findChild(QLabel, object_name)
            if target is not None:
                target.setText(text)
        stations = self.findChild(QListWidget, "reportStationsList")
        if stations is not None:
            stations.clear()
            rows = overview.get("by_station") or []
            if not rows:
                stations.addItem("No matters yet")
            for row in rows:
                stations.addItem(f"{row.get('station', '?')}: {row.get('matters', 0)}")
        self.status_label.setText("Reports refreshed")

    def _on_refresh_audit_log(self) -> None:
        if self._backend_local is None and self._backend_client is None:
            self.status_label.setText("Start solo mode or connect to a server first")
            return
        try:
            result = self._backend_audit_log()
            audit_list = self.findChild(QListWidget, "auditLogList")
            if audit_list is not None:
                audit_list.clear()
                for event in result.get("events", []):
                    timestamp = event.get("created_at", event.get("timestamp", ""))
                    action = event.get("event_type", event.get("action", ""))
                    actor = event.get("actor_id", event.get("username", ""))
                    audit_list.addItem(f"{timestamp} | {actor} | {action}")
            self.status_label.setText(f"Audit log: {len(result.get('events', []))} events")
        except (WakiliOSClientError, WakiliOSConnectionError, Exception) as exc:
            self.status_label.setText(f"Failed to load audit log: {exc}")

    def run_worker_selftest(self) -> None:
        self.selftest_button.setEnabled(False)
        self.status_label.setText("Running worker selftest")
        worker = BackgroundWorker(lambda: "Worker selftest pass")
        worker.signals.completed.connect(self._on_worker_completed)
        worker.signals.failed.connect(self._on_worker_failed)
        self.thread_pool.start(worker)

    @Slot()
    def run_native_workflow_check(self) -> None:
        self.workflow_button.setEnabled(False)
        self.status_label.setText("Running native workflow check")

        def task() -> object:
            from core import run_native_app_workflow

            with tempfile.TemporaryDirectory(prefix="dv-ui-workflow-") as temporary_dir:
                return run_native_app_workflow(
                    Path(temporary_dir),
                    provider_environment=self.provider_environment,
                )

        worker = BackgroundWorker(task)
        worker.signals.completed.connect(self._on_native_workflow_completed)
        worker.signals.failed.connect(self._on_native_workflow_failed)
        self.thread_pool.start(worker)

    @Slot()
    def _save_provider_settings(self) -> None:
        field_map = {
            "openai": "openaiApiKeyInput",
            "anthropic": "anthropicApiKeyInput",
            "google": "googleApiKeyInput",
            "azure_openai": "azureOpenaiApiKeyInput",
            "mistral": "mistralApiKeyInput",
        }
        environment = _provider_environment_from_os()
        for provider, object_name in field_map.items():
            field = self.findChild(QLineEdit, object_name)
            if field is not None and field.text():
                env_var = provider_env_var(provider)
                environment[env_var] = field.text()
                field.clear()
        self.provider_environment = environment
        statuses = configured_provider_statuses(self.provider_environment)
        configured = [status.provider for status in statuses if status.configured]
        status_label = self.findChild(QLabel, "providerKeyStatusLabel")
        if status_label is not None:
            if configured:
                status_label.setText(f"Configured: {', '.join(configured)}")
            else:
                status_label.setText("No providers configured")

    @Slot()
    def choose_and_import_files(self) -> None:
        selected = _choose_files(
            self,
            "Add legal documents",
            "Legal documents (*.pdf *.docx *.doc *.png *.jpg *.jpeg *.tif *.tiff);;All files (*)",
        )
        self.import_files([Path(item) for item in selected])

    def import_files(self, paths: list[Path]) -> None:
        queue = self.findChild(QListWidget, "documentReviewQueue")
        duplicate_status = self.findChild(QLabel, "duplicateStatusLabel")
        ocr_status = self.findChild(QLabel, "ocrStatusLabel")
        if queue is not None and queue.count() == 1 and queue.item(0).text() == "Queue empty":
            queue.clear()
        duplicate_count = 0
        latest_ocr_status = "idle"
        for path in paths:
            result = self.manual_session.import_file(path)
            duplicate_count += 1 if result.status == "duplicate" else 0
            latest_ocr_status = result.extraction_status
            if queue is not None:
                queue.addItem(result.summary())
        if duplicate_status is not None:
            duplicate_status.setText(f"Duplicates: {duplicate_count}")
        if ocr_status is not None:
            ocr_status.setText(f"OCR: {latest_ocr_status}")
        self.status_label.setText(f"Imported {len(paths)} file(s)")

    @Slot()
    def ask_current_question(self) -> None:
        ask_box = self.findChild(QTextEdit, "ragQuestionInput")
        output = self.findChild(QTextEdit, "ragCitationPacketOutput")
        question = ask_box.toPlainText().strip() if ask_box is not None else ""
        if not question:
            question = "What public legal context is available in this matter?"
        result = self.manual_session.ask(question)
        if output is not None:
            titles = "; ".join(result.citation_titles) if result.citation_titles else "none"
            output.setPlainText(
                f"Question: {question}\n"
                f"Confidence: {result.confidence}\n"
                f"Citations: {result.citation_count}\n"
                f"Titles: {titles}\n"
                f"Elapsed ms: {result.elapsed_ms}"
            )
        self.status_label.setText(
            f"RAG checked: citations={result.citation_count}, confidence={result.confidence}"
        )

    @Slot()
    def create_backup_and_restore(self) -> None:
        result = self.manual_session.backup_and_restore()
        backup_status = self.findChild(QLabel, "backupStatusLabel")
        restore_status = self.findChild(QLabel, "restoreStatusLabel")
        if backup_status is not None:
            backup_status.setText(f"Backup bytes: {result.package_size_bytes}")
        if restore_status is not None:
            restore_status.setText(
                "Restore verified: "
                f"{result.restore_verified}; wrong key failed: {result.wrong_key_failed}"
            )
        self.status_label.setText("Backup and restore drill complete")

    @Slot()
    def check_admin_license_payment_status(self) -> None:
        from scripts.admin_license_payment_e2e import run_admin_license_payment_e2e

        report = run_admin_license_payment_e2e()
        active_decision = report["active_decision"]
        installation_status = self.findChild(QLabel, "installationStatusLabel")
        entitlement_status = self.findChild(QLabel, "entitlementStatusLabel")
        if isinstance(active_decision, dict):
            if installation_status is not None:
                installation_status.setText(str(active_decision["installation_status"]))
            if entitlement_status is not None:
                entitlement_status.setText(
                    "paid="
                    f"{active_decision['paid_features_enabled']}; "
                    f"cloud={active_decision['cloud_backup_enabled']}; "
                    f"rag={active_decision['matter_rag_enabled']}; "
                    f"hosted_ai={active_decision['hosted_ai_enabled']}"
                )
        self.status_label.setText("Admin/license/payment boundary checked")

    @Slot(object)
    def _on_worker_completed(self, result: object) -> None:
        self.status_label.setText(str(result))
        self.selftest_button.setEnabled(True)

    @Slot(str)
    def _on_worker_failed(self, message: str) -> None:
        self.status_label.setText(f"Worker selftest failed: {message}")
        self.selftest_button.setEnabled(True)

    @Slot(object)
    def _on_native_workflow_completed(self, result: object) -> None:
        report = result.to_mapping()
        self.status_label.setText(
            "Native workflow pass: "
            f"citations={report['rag_citations']}, confidence={report['rag_confidence']}"
        )
        output = self.findChild(QTextEdit, "ragCitationPacketOutput")
        if output is not None:
            output.setPlainText(
                "Native workflow pass\n"
                f"Search results: {report['search_results']}\n"
                f"RAG citations: {report['rag_citations']}\n"
                f"RAG confidence: {report['rag_confidence']}\n"
                f"Restore verified: {report['restore_verified']}"
            )
        self.workflow_button.setEnabled(True)

    @Slot(str)
    def _on_native_workflow_failed(self, message: str) -> None:
        self.status_label.setText(f"Native workflow failed: {message}")
        self.workflow_button.setEnabled(True)


def create_app(argv: list[str] | None = None) -> QApplication:
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    app = QApplication.instance()
    if isinstance(app, QApplication):
        return app
    app = QApplication(list(sys.argv if argv is None else argv))
    # Load professional stylesheet
    stylesheet_path = Path(__file__).parent / "jurisnuru.qss"
    if stylesheet_path.exists():
        app.setStyleSheet(stylesheet_path.read_text(encoding="utf-8"))
    return app


def run_gui(argv: list[str] | None = None, *, smoke_ms: int | None = None) -> int:
    try:
        app = create_app(argv)
        window = MainWindow()
        window.showNormal()
        window.raise_()
        window.activateWindow()
        if smoke_ms is not None:
            result_path = Path(tempfile.gettempdir()) / "WakiliOS_gui_smoke.txt"
            result_path.write_text(
                "GUI START PASS\n"
                f"visible={window.isVisible()}\n"
                f"window_id={int(window.winId())}\n"
                f"platform={app.platformName()}\n",
                encoding="utf-8",
            )
            QTimer.singleShot(smoke_ms, app.quit)
        return app.exec()
    except Exception as exc:
        result_path = Path(tempfile.gettempdir()) / "WakiliOS_gui_smoke.txt"
        try:
            result_path.write_text(
                f"GUI START FAIL\n{type(exc).__name__}: {exc}\n",
                encoding="utf-8",
            )
        except OSError:
            pass
        return 1


def _module_card(module: ModuleStatus) -> QFrame:
    frame = QFrame()
    frame.setObjectName("moduleCard")
    frame.setFrameShape(QFrame.Shape.StyledPanel)
    layout = QVBoxLayout(frame)
    name = QLabel(module.name)
    name.setObjectName("moduleName")
    status = QLabel(module.status)
    status.setObjectName("moduleStatus")
    layout.addWidget(name)
    layout.addWidget(status)
    return frame


def _scroll_page(page: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setObjectName(f"{page.objectName()}ScrollArea")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setWidget(page)
    return scroll


def _license_page() -> QWidget:
    page = QWidget()
    page.setObjectName("licensePage")
    layout = QVBoxLayout(page)
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(16)

    title = QLabel("Activate JurisNuru")
    title.setObjectName("licensePageTitle")
    layout.addWidget(title)
    explanation = QLabel(
        "A valid signed license is required before JurisNuru can open the dashboard. "
        "Licenses are issued per machine, so this installation needs its own file."
    )
    explanation.setObjectName("licensePageExplanation")
    explanation.setWordWrap(True)
    layout.addWidget(explanation)

    # Without this, a firm that has just installed JurisNuru sees a file picker,
    # an installation ID and no indication of where a license comes from.
    steps = QLabel(
        "<b>To obtain a license</b><br>"
        "1. Copy the Installation ID below and send it to your JurisNuru supplier.<br>"
        "2. You will receive a <code>license.key</code> file issued for this machine.<br>"
        "3. Choose <b>Browse</b>, select that file, then <b>Activate license</b>."
    )
    steps.setObjectName("licensePageSteps")
    steps.setWordWrap(True)
    steps.setTextFormat(Qt.TextFormat.RichText)
    layout.addWidget(steps)

    license_group = QFrame()
    license_group.setObjectName("licenseGroup")
    license_layout = QFormLayout(license_group)
    license_file = QLineEdit()
    license_file.setObjectName("licenseFileInput")
    license_file.setPlaceholderText("Path to license.key")
    browse = QPushButton("Browse")
    browse.setObjectName("browseLicenseButton")
    installation = QLabel("Preparing installation identity...")
    installation.setObjectName("licenseInstallationLabel")
    installation.setWordWrap(True)
    status = QLabel("Not activated")
    status.setObjectName("licenseStatusLabel")
    status.setWordWrap(True)
    activate = QPushButton("Activate license")
    activate.setObjectName("activateLicenseButton")
    license_file_row = QHBoxLayout()
    license_file_row.addWidget(license_file, stretch=1)
    license_file_row.addWidget(browse)
    license_layout.addRow("License file", license_file_row)
    copy_identity = QPushButton("Copy ID")
    copy_identity.setObjectName("copyInstallationIdButton")
    copy_identity.setToolTip("Copy this machine's Installation ID to the clipboard")
    installation_row = QHBoxLayout()
    installation_row.addWidget(installation, stretch=1)
    installation_row.addWidget(copy_identity)
    license_layout.addRow("Installation", installation_row)
    license_layout.addRow("Status", status)
    license_layout.addRow("", activate)
    layout.addWidget(license_group)

    locked = QLabel("JurisNuru is locked until license activation")
    locked.setObjectName("licenseLockMessage")
    layout.addWidget(locked)

    # Say plainly what the two files that are NOT a license look like, because
    # both sit in the installation directory and both get tried.
    note = QLabel(
        "Note: neither the public verification key (license_public_key.pem) nor the "
        "installation identity (installation.json) is a license. Both live alongside "
        "JurisNuru and are rejected here."
    )
    note.setObjectName("licenseFileNote")
    note.setWordWrap(True)
    layout.addWidget(note)
    layout.addStretch(1)
    return page


def _dashboard_page() -> QWidget:
    """Dashboard: setup, connection, and vault in one view after activation."""
    page = QWidget()
    page.setObjectName("dashboardPage")
    layout = QVBoxLayout(page)

    # --- Connection section ---
    connection_group = QFrame()
    connection_group.setObjectName("connectionGroup")
    connection_layout = QVBoxLayout(connection_group)
    connection_label = QLabel("Connect to JurisNuru")
    connection_label.setObjectName("connectionGroupLabel")
    connection_layout.addWidget(connection_label)
    backend_connection = BackendConnectionDialog()
    backend_connection.setObjectName("backendConnectionDialog")
    connection_layout.addWidget(backend_connection)
    layout.addWidget(connection_group)

    # --- Setup section ---
    setup_group = QFrame()
    setup_group.setObjectName("setupGroup")
    setup_layout = QFormLayout(setup_group)
    firm_name = QLineEdit()
    firm_name.setObjectName("firmNameInput")
    primary_user = QLineEdit()
    primary_user.setObjectName("primaryUserInput")
    device_name = QLineEdit()
    device_name.setObjectName("deviceNicknameInput")
    recovery_confirmed = QCheckBox("Recovery key recorded")
    recovery_confirmed.setObjectName("recoveryKeyConfirmedCheck")
    setup_button = QPushButton("Setup complete")
    setup_button.setObjectName("completeSetupButton")
    setup_layout.addRow("Firm", firm_name)
    setup_layout.addRow("Primary user", primary_user)
    setup_layout.addRow("Device", device_name)
    setup_layout.addRow("", recovery_confirmed)
    setup_layout.addRow("", setup_button)
    layout.addWidget(setup_group)

    # --- Vault section ---
    vault_group = QFrame()
    vault_group.setObjectName("vaultGroup")
    vault_layout = QFormLayout(vault_group)
    vault_path = QLineEdit()
    vault_path.setObjectName("vaultPathInput")
    recovery_key = QLineEdit()
    recovery_key.setObjectName("recoveryKeyInput")
    recovery_key.setEchoMode(QLineEdit.EchoMode.Password)
    initialize = QPushButton("Initialize vault")
    initialize.setObjectName("initializeVaultButton")
    vault_layout.addRow("Vault path", vault_path)
    vault_layout.addRow("Recovery key", recovery_key)
    vault_layout.addRow("", initialize)
    layout.addWidget(vault_group)

    layout.addStretch(1)
    return page


def _workspace_page() -> QWidget:
    """Workspace: matters, import, and search/RAG in one view with sub-tabs."""
    page = QWidget()
    page.setObjectName("workspacePage")
    layout = QVBoxLayout(page)

    # Matter header with role status and actions
    header = QHBoxLayout()
    role_status = QLabel("Role: not connected")
    role_status.setObjectName("roleStatusLabel")
    connection_health = QLabel("Not connected")
    connection_health.setObjectName("connectionHealthLabel")
    connection_health.setToolTip("Whether the firm backend is answering")
    export_calendar = QPushButton("Export calendar")
    export_calendar.setObjectName("exportCalendarButton")
    add_matter = QPushButton("New matter")
    add_matter.setObjectName("newMatterButton")
    from_document = QPushButton("From document")
    from_document.setObjectName("newMatterFromDocumentButton")
    from_document.setToolTip("Read the case number, parties, court and station off a filing")
    refresh_matters = QPushButton("Refresh")
    refresh_matters.setObjectName("refreshMatterListButton")
    header.addWidget(role_status)
    header.addWidget(connection_health)
    header.addStretch(1)
    header.addWidget(refresh_matters)
    header.addWidget(export_calendar)
    header.addWidget(from_document)
    header.addWidget(add_matter)

    # Matter list
    matter_list = QListWidget()
    matter_list.setObjectName("matterList")
    matter_list.addItems(["Connect to backend to load matters"])

    # Workspace sub-tabs (parties, activities, etc.)
    workspace_tabs = QTabWidget()
    workspace_tabs.setObjectName("matterWorkspaceTabs")
    workspace_tabs.addTab(_matter_summary_tab(), "Summary")
    for view in MATTER_TAB_VIEWS:
        workspace_tabs.addTab(
            _matter_text_list_tab(view.object_name, view.empty_text, addable=view.addable),
            view.label,
        )
    # Document upload button (separate from the generic Add)
    doc_upload_btn = QPushButton("Upload document")
    doc_upload_btn.setObjectName("uploadDocumentButton")
    workspace_tabs.findChild(QWidget, "matterDocumentsTab").layout().addWidget(doc_upload_btn)

    layout.addLayout(header)
    layout.addWidget(matter_list)

    # Matter content on the left, the AI layer beside it -- the brief's
    # product map, rather than an AI box in a settings page.
    split = QHBoxLayout()
    split.addWidget(workspace_tabs, stretch=3)
    split.addWidget(_matter_ai_context_panel(), stretch=1)
    layout.addLayout(split, stretch=1)
    return page


def _import_group() -> QFrame:
    import_group = QFrame()
    import_group.setObjectName("importGroup")
    import_layout = QVBoxLayout(import_group)
    import_label = QLabel("Document Import")
    import_label.setObjectName("importGroupLabel")
    import_layout.addWidget(import_label)
    queue = QListWidget()
    queue.setObjectName("documentReviewQueue")
    queue.addItems(["Queue empty"])
    controls = QHBoxLayout()
    add_files = QPushButton("Add files")
    add_files.setObjectName("addFilesButton")
    run_ocr = QPushButton("Run OCR")
    run_ocr.setObjectName("runOcrButton")
    duplicate_status = QLabel("Duplicates: none")
    duplicate_status.setObjectName("duplicateStatusLabel")
    ocr_status = QLabel("OCR: idle")
    ocr_status.setObjectName("ocrStatusLabel")
    controls.addWidget(add_files)
    controls.addWidget(run_ocr)
    controls.addWidget(duplicate_status)
    controls.addWidget(ocr_status)
    controls.addStretch(1)
    import_layout.addWidget(queue)
    import_layout.addLayout(controls)
    return import_group


def _search_group() -> QFrame:
    search_group = QFrame()
    search_group.setObjectName("searchGroup")
    search_layout = QVBoxLayout(search_group)
    search_label = QLabel("Search & RAG")
    search_label.setObjectName("searchGroupLabel")
    search_layout.addWidget(search_label)
    search_box = QLineEdit()
    search_box.setObjectName("matterSearchInput")
    search_box.setPlaceholderText("Search documents...")
    ask_box = QTextEdit()
    ask_box.setObjectName("ragQuestionInput")
    ask_box.setFixedHeight(80)
    ask_box.setPlaceholderText("Ask a question about your documents...")
    answer_box = QTextEdit()
    answer_box.setObjectName("ragCitationPacketOutput")
    answer_box.setReadOnly(True)
    answer_box.setPlaceholderText("Answers and citations will appear here...")
    ask_button = QPushButton("Ask")
    ask_button.setObjectName("askRagButton")
    search_layout.addWidget(search_box)
    search_layout.addWidget(ask_box)
    search_layout.addWidget(ask_button)
    search_layout.addWidget(answer_box)
    return search_group


def _ai_keys_group() -> QFrame:
    ai_group = QFrame()
    ai_group.setObjectName("aiKeysGroup")
    ai_layout = QFormLayout(ai_group)
    providers = (
        ("OpenAI", "openaiApiKeyInput"),
        ("Anthropic", "anthropicApiKeyInput"),
        ("Google", "googleApiKeyInput"),
        ("Azure OpenAI", "azureOpenaiApiKeyInput"),
        ("Mistral", "mistralApiKeyInput"),
    )
    for label, object_name in providers:
        field = QLineEdit()
        field.setObjectName(object_name)
        field.setEchoMode(QLineEdit.EchoMode.Password)
        ai_layout.addRow(label, field)
    ai_status = QLabel("Provider keys are local settings")
    ai_status.setObjectName("providerKeyStatusLabel")
    save = QPushButton("Save provider settings")
    save.setObjectName("saveProviderSettingsButton")
    ai_layout.addRow("Status", ai_status)
    ai_layout.addRow("", save)
    return ai_group


def _backup_group() -> QFrame:
    backup_group = QFrame()
    backup_group.setObjectName("backupGroup")
    backup_layout = QFormLayout(backup_group)
    backup_status = QLabel("No backup yet")
    backup_status.setObjectName("backupStatusLabel")
    restore_status = QLabel("No restore drill yet")
    restore_status.setObjectName("restoreStatusLabel")
    backup_button = QPushButton("Create backup")
    backup_button.setObjectName("createBackupButton")
    restore_button = QPushButton("Restore drill")
    restore_button.setObjectName("restoreDrillButton")
    backup_layout.addRow("Backup", backup_status)
    backup_layout.addRow("Restore", restore_status)
    backup_layout.addRow("", backup_button)
    backup_layout.addRow("", restore_button)
    return backup_group


def _admin_group() -> QFrame:
    admin_group = QFrame()
    admin_group.setObjectName("adminGroup")
    admin_layout = QVBoxLayout(admin_group)
    admin_form = QFormLayout()
    installation = QLabel("Installation not synced")
    installation.setObjectName("installationStatusLabel")
    entitlement = QLabel("Entitlement unknown")
    entitlement.setObjectName("entitlementStatusLabel")
    sync_button = QPushButton("Check status")
    sync_button.setObjectName("adminSyncButton")
    admin_form.addRow("Installation", installation)
    admin_form.addRow("Entitlement", entitlement)
    admin_form.addRow("", sync_button)
    admin_layout.addLayout(admin_form)

    admin_layout.addWidget(QLabel("Audit Log"))
    audit_list = QListWidget()
    audit_list.setObjectName("auditLogList")
    audit_list.addItem("No audit events loaded")
    refresh_audit = QPushButton("Refresh audit log")
    refresh_audit.setObjectName("refreshAuditLogButton")
    admin_layout.addWidget(audit_list)
    admin_layout.addWidget(refresh_audit)
    return admin_group


def _documents_page() -> QWidget:
    """Intake and review queue for documents entering the vault."""
    page = QWidget()
    page.setObjectName("documentsPage")
    layout = QVBoxLayout(page)
    layout.addWidget(_import_group())
    layout.addStretch(1)
    return page


def _filing_record_page() -> QWidget:
    """The firm's own account of what was filed, served and received."""
    page = QWidget()
    page.setObjectName("filingRecordPage")
    layout = QVBoxLayout(page)

    group = QFrame()
    group.setObjectName("filingRecordGroup")
    group_layout = QVBoxLayout(group)
    heading = QLabel("Filing record for this matter")
    heading.setObjectName("filingRecordGroupLabel")
    caption = QLabel(
        "A portal submission proves a filing was made. This is the firm's "
        "independent record of what was filed, when, by whom, what was served, "
        "what came back, and what happens next."
    )
    caption.setObjectName("filingRecordCaption")
    caption.setWordWrap(True)
    matter_label = QLabel("No matter open")
    matter_label.setObjectName("filingRecordMatterLabel")
    listing = QListWidget()
    listing.setObjectName("filingRecordPageList")
    listing.addItem("Open a matter in Matters to see its filing record")

    controls = QHBoxLayout()
    add_filing = QPushButton("Record a filing")
    add_filing.setObjectName("filingRecordPageAddButton")
    refresh_filing = QPushButton("Refresh")
    refresh_filing.setObjectName("filingRecordPageRefreshButton")
    export_filing = QPushButton("Export next actions")
    export_filing.setObjectName("filingRecordPageExportButton")
    export_filing.setToolTip("Write the recorded next actions to a calendar file")
    controls.addWidget(add_filing)
    controls.addWidget(refresh_filing)
    controls.addWidget(export_filing)
    controls.addStretch(1)

    group_layout.addWidget(heading)
    group_layout.addWidget(caption)
    group_layout.addWidget(matter_label)
    group_layout.addWidget(listing)
    group_layout.addLayout(controls)

    layout.addWidget(group)
    layout.addStretch(1)
    return page


def _search_page() -> QWidget:
    """Grounded search and RAG over the firm's own record."""
    page = QWidget()
    page.setObjectName("searchPage")
    layout = QVBoxLayout(page)
    layout.addWidget(_search_group())
    layout.addStretch(1)
    return page


def _reports_page() -> QWidget:
    """Firm-level counts across matters, filings and payments."""
    page = QWidget()
    page.setObjectName("reportsPage")
    layout = QVBoxLayout(page)

    group = QFrame()
    group.setObjectName("reportsGroup")
    form = QFormLayout(group)
    for label, object_name in (
        ("Matters", "reportMattersLabel"),
        ("Documents in vault", "reportDocumentsLabel"),
        ("Filing records", "reportFilingRecordsLabel"),
        ("Fees raised", "reportFeesLabel"),
        ("Receipts recorded", "reportReceiptsLabel"),
        ("Balance", "reportBalanceLabel"),
    ):
        value = QLabel("-")
        value.setObjectName(object_name)
        form.addRow(label, value)
    stations = QListWidget()
    stations.setObjectName("reportStationsList")
    stations.addItem("Refresh to load matters by station")
    form.addRow("By station", stations)
    refresh = QPushButton("Refresh reports")
    refresh.setObjectName("refreshReportsButton")
    form.addRow("", refresh)

    layout.addWidget(group)
    layout.addStretch(1)
    return page


def _settings_page(modules: tuple[ModuleStatus, ...] = DEFAULT_MODULES) -> QWidget:
    """Connection, firm setup, vault, provider keys, backup, admin, about.

    The brief's navigation has no About destination, so the release and module
    status cards live at the bottom of Settings.
    """
    page = QWidget()
    page.setObjectName("settingsPage")
    layout = QVBoxLayout(page)
    layout.addWidget(_dashboard_page())
    layout.addWidget(_reminder_settings_group())
    layout.addWidget(_ai_keys_group())
    layout.addWidget(_backup_group())
    layout.addWidget(_admin_group())
    layout.addWidget(_about_page(modules))
    layout.addStretch(1)
    return page


KIND_LABELS = {
    "hearing": "Hearing",
    "lodging_due": "Lodging due",
    "decision": "Decision",
    "next_action": "Next action",
}


class DailyReminderDialog(QDialog):
    """The day's matters, shown once a day.

    Deliberately a dialog rather than only a tray balloon. Under
    ``QT_QPA_PLATFORM=offscreen`` there is no tray at all, so a balloon-only
    design could never be tested; and on a real desktop Windows Focus Assist
    swallows toasts silently, which is the worst possible failure for a
    reminder -- the firm believes it is covered and never learns otherwise. The
    balloon is an extra nudge where the platform offers one.

    Modal, and once a day. A digest that can be missed is not a reminder, and
    one click dismisses it.
    """

    def __init__(self, entries: list[dict[str, object]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dailyReminderDialog")
        self.setWindowTitle("Today's matters")
        self.setMinimumWidth(520)
        self.selected_matter_id = ""
        self.snoozed = False

        layout = QVBoxLayout(self)

        heading = QLabel("Today's matters")
        heading.setObjectName("dailyReminderHeading")
        layout.addWidget(heading)

        summary = QLabel(summarise_reminders(entries))
        summary.setObjectName("dailyReminderSummaryLabel")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        self.listing = QListWidget()
        self.listing.setObjectName("dailyReminderList")
        for entry in entries:
            self.listing.addItem(QListWidgetItem(_reminder_row(entry)))
        layout.addWidget(self.listing)

        buttons = QHBoxLayout()
        open_matter = QPushButton("Open matter")
        open_matter.setObjectName("dailyReminderOpenButton")
        open_matter.clicked.connect(lambda: self._on_open(entries))
        snooze_button = QPushButton("Snooze 1 hour")
        snooze_button.setObjectName("dailyReminderSnoozeButton")
        snooze_button.clicked.connect(self._on_snooze)
        dismiss = QPushButton("Dismiss")
        dismiss.setObjectName("dailyReminderDismissButton")
        dismiss.clicked.connect(self.accept)
        for widget in (open_matter, snooze_button, dismiss):
            buttons.addWidget(widget)
        layout.addLayout(buttons)

    def _on_open(self, entries: list[dict[str, object]]) -> None:
        row = self.listing.currentRow()
        if row < 0 and entries:
            row = 0
        if 0 <= row < len(entries):
            self.selected_matter_id = str(entries[row].get("matter_id", ""))
        self.accept()

    def _on_snooze(self) -> None:
        self.snoozed = True
        self.accept()


def _reminder_row(entry: dict[str, object]) -> str:
    """One line an advocate can act on without opening anything."""
    kind = KIND_LABELS.get(str(entry.get("kind", "")), str(entry.get("kind", "")))
    clock = str(entry.get("time") or "all day")
    reference = str(entry.get("case_number") or entry.get("matter_reference") or "")
    title = str(entry.get("title", ""))
    return f"{clock}  {kind}  -  {title}" + (f"  [{reference}]" if reference else "")


def _reminder_settings_group() -> QWidget:
    group = QFrame()
    group.setObjectName("dailyReminderGroup")
    layout = QFormLayout(group)

    heading = QLabel("Daily reminders")
    heading.setObjectName("dailyReminderSettingsHeading")
    layout.addRow(heading)

    enabled = QCheckBox("Show the day's matters when I open JurisNuru")
    enabled.setObjectName("dailyReminderEnabledCheckbox")
    enabled.setChecked(True)
    layout.addRow("Enabled", enabled)

    time_input = QLineEdit(f"{DEFAULT_HOUR:02d}:{DEFAULT_MINUTE:02d}")
    time_input.setObjectName("dailyReminderTimeInput")
    time_input.setPlaceholderText("HH:MM")
    layout.addRow("Show from", time_input)

    horizon = QLineEdit(str(DEFAULT_HORIZON_DAYS))
    horizon.setObjectName("dailyReminderHorizonInput")
    horizon.setPlaceholderText("days ahead to include")
    layout.addRow("Days ahead", horizon)

    save = QPushButton("Save reminder settings")
    save.setObjectName("saveReminderSettingsButton")
    layout.addRow(save)

    show_now = QPushButton("Show today's matters now")
    show_now.setObjectName("testDailyReminderButton")
    show_now.setToolTip("Raise the digest immediately, whatever the schedule says")
    layout.addRow(show_now)

    caption = QLabel(
        "The digest appears the first time you open JurisNuru at or after this "
        "time each day. It is a digest on first sight, not an alarm: JurisNuru "
        "does not run in the background."
    )
    caption.setObjectName("dailyReminderCaption")
    caption.setWordWrap(True)
    layout.addRow(caption)
    return group


def _matter_ai_context_panel() -> QWidget:
    """The brief's trusted AI layer: ask about *this* matter, sources visible.

    Slide 14 puts this beside the matter, not in a settings page, and the
    distinction is the product's whole argument. A question asked here is
    scoped to the open matter, the answer names how many of its documents
    supported it, and nothing is presented as settled: a lawyer verifies and
    remains accountable.
    """
    panel = QFrame()
    panel.setObjectName("matterAiPanel")
    layout = QVBoxLayout(panel)

    heading = QLabel("Trusted AI layer")
    heading.setObjectName("matterAiHeading")
    caption = QLabel("Ask about this matter using only authorised sources.")
    caption.setObjectName("matterAiCaption")
    caption.setWordWrap(True)

    question = QTextEdit()
    question.setObjectName("matterAiQuestionInput")
    question.setFixedHeight(64)
    question.setPlaceholderText("What was filed and what is the next recorded step?")

    ask = QPushButton("Ask this matter")
    ask.setObjectName("matterAiAskButton")

    answer = QTextEdit()
    answer.setObjectName("matterAiAnswerOutput")
    answer.setReadOnly(True)
    answer.setPlaceholderText("The answer and its sources appear here.")

    sources = QLabel("Sources: none yet")
    sources.setObjectName("matterAiSourcesLabel")
    sources.setWordWrap(True)

    review = QLabel("Lawyer review required")
    review.setObjectName("matterAiReviewLabel")

    for widget in (heading, caption, question, ask, answer, sources, review):
        layout.addWidget(widget)
    return panel


def _matter_summary_tab() -> QWidget:
    tab = QWidget()
    tab.setObjectName("summaryTab")
    layout = QFormLayout(tab)
    case_information = QTextEdit()
    case_information.setObjectName("matterCaseInformationInput")
    case_information.setFixedHeight(86)
    matter_status = QLabel("Active - filed")
    matter_status.setObjectName("matterStatusLabel")
    ai_summary = QTextEdit()
    ai_summary.setObjectName("aiMatterSummaryOutput")
    ai_summary.setReadOnly(True)
    ai_summary.setPlainText("No summary yet")
    generate = QPushButton("Draft summary")
    generate.setObjectName("generateSummaryButton")
    generate.setToolTip("Compose a summary from the matter's own record")
    summary_add = QPushButton("Update summary")
    summary_add.setObjectName("summaryAddButton")
    layout.addRow("Case information", case_information)
    layout.addRow("Status", matter_status)
    layout.addRow("AI summary", ai_summary)
    layout.addRow("", generate)
    layout.addRow("", summary_add)
    return tab


def _matter_text_list_tab(object_name: str, empty_text: str, *, addable: bool = True) -> QWidget:
    tab = QWidget()
    tab.setObjectName(object_name)
    layout = QVBoxLayout(tab)
    listing = QListWidget()
    listing.setObjectName(f"{object_name}List")
    listing.addItem(empty_text)
    layout.addWidget(listing)
    if addable:
        add_button = QPushButton("Add")
        add_button.setObjectName(f"{object_name}AddButton")
        layout.addWidget(add_button)
    return tab


def _about_page(modules: tuple[ModuleStatus, ...]) -> QWidget:
    page = QWidget()
    page.setObjectName("aboutPage")
    layout = QVBoxLayout(page)
    release_info = QLabel("JurisNuru multi-seat litigation management")
    release_info.setObjectName("releaseInfoLabel")
    layout.addWidget(release_info)
    grid = QGridLayout()
    for index, module in enumerate(modules):
        card = _module_card(module)
        grid.addWidget(card, index // 3, index % 3)
    layout.addLayout(grid)
    layout.addStretch(1)
    return page


def _provider_environment_from_os() -> dict[str, str]:
    environment: dict[str, str] = {}
    for provider in supported_providers():
        env_var = provider_env_var(provider)
        value = os.environ.get(env_var, "")
        if value:
            environment[env_var] = value
    return environment
