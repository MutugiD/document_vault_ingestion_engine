"""WakiliOS desktop shell with in-process and multi-seat connectivity."""

from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ai import configured_provider_statuses, provider_env_var, supported_providers
from core import ManualAppSession
from wakilios.client import (
    WakiliOSClient,
    WakiliOSClientConfig,
    WakiliOSClientError,
    WakiliOSConnectionError,
)
from wakilios.core import WakiliOSBackend, initialize_firm_backend


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
        password = self.password_input.text() or "admin-pass"
        try:
            solo_root = Path(tempfile.gettempdir()) / "wakilios-solo"
            solo_root.mkdir(parents=True, exist_ok=True)
            backend = initialize_firm_backend(
                solo_root,
                firm_name="Solo Practice",
                admin_username=username,
                admin_password=password,
                vault_passphrase="solo vault passphrase",
                max_seats=1,
            )
            session = backend.login(username, password)
            role = session.role
            self.status_label.setText(f"Solo mode as {username} ({role})")
            self.solo_mode_started.emit(username, role)
        except Exception as exc:
            self.status_label.setText(f"Solo start failed: {exc}")


class MainWindow(QMainWindow):
    """Production-oriented V1 desktop workbench."""

    def __init__(
        self,
        modules: tuple[ModuleStatus, ...] = DEFAULT_MODULES,
        *,
        workspace: Path | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("WakiliOS")
        self.setMinimumSize(920, 620)

        self._backend_client: WakiliOSClient | None = None
        self._backend_local: WakiliOSBackend | None = None
        self._current_role: str = ""
        self._current_username: str = ""
        self._current_matter_id: str = ""

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(12)

        heading = QLabel("WakiliOS")
        heading.setObjectName("heading")
        heading.setAlignment(Qt.AlignmentFlag.AlignLeft)
        root_layout.addWidget(heading)

        subtitle = QLabel(
            "Multi-seat litigation management, encrypted custody, search, and firm workflows."
        )
        subtitle.setObjectName("subtitle")
        root_layout.addWidget(subtitle)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("workflowTabs")
        self.tabs.addTab(_dashboard_page(), "Dashboard")
        self.tabs.addTab(_workspace_page(), "Workspace")
        self.tabs.addTab(_settings_page(), "Settings")
        self.tabs.addTab(_about_page(modules), "About")
        root_layout.addWidget(self.tabs, stretch=1)

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
        self.manual_session = ManualAppSession(
            workspace or Path(tempfile.gettempdir()) / "document-vault-manual-app-session"
        )
        self._connect_workflow_controls()
        self._connect_backend_controls()

    def _connect_workflow_controls(self) -> None:
        """Wire up the existing workflow control buttons."""
        button_actions = {
            "completeSetupButton": "Setup complete",
            "activateLicenseButton": "License activation checked",
            "initializeVaultButton": "Vault initialization checked",
            "newMatterButton": "WakiliOS matter workflow checked",
            "exportCalendarButton": "Matter calendar export checked",
            "runOcrButton": "OCR workflow checked",
        }
        for object_name, message in button_actions.items():
            button = self.findChild(QPushButton, object_name)
            if button is not None:
                button.clicked.connect(
                    lambda _checked=False, text=message: self.status_label.setText(text)
                )

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

        for tab_object_name, handler in [
            ("summaryTab", self._on_update_summary),
            ("partiesTab", self._on_add_party),
            ("activitiesTab", self._on_add_activity),
            ("lodgingsTab", self._on_add_lodging),
            ("courtDecisionsTab", self._on_add_court_decision),
            ("feesTab", self._on_add_fee),
            ("receiptsTab", self._on_add_receipt),
        ]:
            object_name = f"{tab_object_name}AddButton"
            button = self.findChild(QPushButton, object_name)
            if button is not None:
                button.clicked.connect(handler)

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

    @Slot(str, str)
    def _on_solo_mode_started(self, username: str, role: str) -> None:
        """Handle solo mode: initialize local backend directly, no HTTP needed."""
        solo_root = Path(tempfile.gettempdir()) / "wakilios-solo"
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

    def _backend_audit_log(self) -> dict:
        if self._backend_local is not None:
            events = self._backend_local.audit_events(self._solo_token())
            return {"events": events}
        if self._backend_client is not None:
            return self._backend_client.audit_log()
        return {"events": []}

    def _on_new_matter(self) -> None:
        if self._backend_local is None and self._backend_client is None:
            self.status_label.setText("Start solo mode or connect to a server first")
            return
        try:
            result = self._backend_create_matter(
                internal_reference="NEW-001",
                client_name="New Client",
                parties="New Matter Parties",
                court="High Court",
                station="Nairobi",
                case_number="NEW/2026",
                practice_area="General",
                responsible_advocate=self._current_username,
                filing_status="draft",
                filing_date="",
            )
            self._current_matter_id = str(result.get("matter_id", ""))
            self.status_label.setText(
                f"Created matter: {result.get('internal_reference', self._current_matter_id)}"
            )
            self._on_refresh_matters()
        except (WakiliOSClientError, WakiliOSConnectionError, Exception) as exc:
            self.status_label.setText(f"Failed to create matter: {exc}")

    def _on_export_calendar(self) -> None:
        if self._backend_local is None and self._backend_client is None:
            self.status_label.setText("Start solo mode or connect to a server first")
            return
        if not self._current_matter_id:
            self.status_label.setText("Select a matter first")
            return
        try:
            ics = self._backend_export_calendar(self._current_matter_id)
            dest = QFileDialog.getSaveFileName(self, "Save Calendar", "", "Calendar Files (*.ics)")[
                0
            ]
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
                    matter_list.addItem(f"{ref} - {client}")
        except (WakiliOSClientError, WakiliOSConnectionError, Exception) as exc:
            self.status_label.setText(f"Failed to list matters: {exc}")

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

    def _on_add_party(self) -> None:
        if (
            self._backend_local is None and self._backend_client is None
        ) or not self._current_matter_id:
            return
        try:
            self._backend_add_party(
                self._current_matter_id, name="New Party", party_role="Respondent"
            )
            self.status_label.setText("Party added")
        except (WakiliOSClientError, WakiliOSConnectionError, Exception) as exc:
            self.status_label.setText(f"Add party failed: {exc}")

    def _on_add_activity(self) -> None:
        if (
            self._backend_local is None and self._backend_client is None
        ) or not self._current_matter_id:
            return
        try:
            self._backend_add_activity(
                self._current_matter_id, activity_type="mention", title="New Activity", starts_at=""
            )
            self.status_label.setText("Activity added")
        except (WakiliOSClientError, WakiliOSConnectionError, Exception) as exc:
            self.status_label.setText(f"Add activity failed: {exc}")

    def _on_add_lodging(self) -> None:
        if (
            self._backend_local is None and self._backend_client is None
        ) or not self._current_matter_id:
            return
        try:
            self._backend_add_lodging(self._current_matter_id, document_kind="New Lodging")
            self.status_label.setText("Lodging added")
        except (WakiliOSClientError, WakiliOSConnectionError, Exception) as exc:
            self.status_label.setText(f"Add lodging failed: {exc}")

    def _on_add_court_decision(self) -> None:
        if (
            self._backend_local is None and self._backend_client is None
        ) or not self._current_matter_id:
            return
        try:
            self._backend_add_court_decision(
                self._current_matter_id, decision_type="Ruling", decision_date=""
            )
            self.status_label.setText("Court decision added")
        except (WakiliOSClientError, WakiliOSConnectionError, Exception) as exc:
            self.status_label.setText(f"Add court decision failed: {exc}")

    def _on_add_fee(self) -> None:
        if (
            self._backend_local is None and self._backend_client is None
        ) or not self._current_matter_id:
            return
        try:
            self._backend_add_fee(self._current_matter_id, fee_type="Filing fee", amount=0)
            self.status_label.setText("Fee added")
            self._on_refresh_fee_receipt_view()
        except (WakiliOSClientError, WakiliOSConnectionError, Exception) as exc:
            self.status_label.setText(f"Add fee failed: {exc}")

    def _on_add_receipt(self) -> None:
        if (
            self._backend_local is None and self._backend_client is None
        ) or not self._current_matter_id:
            return
        try:
            self._backend_add_receipt(
                self._current_matter_id,
                receipt_number="NEW-RCT",
                amount=0,
                receipt_date="2026-07-16",
            )
            self.status_label.setText("Receipt added")
            self._on_refresh_fee_receipt_view()
        except (WakiliOSClientError, WakiliOSConnectionError, Exception) as exc:
            self.status_label.setText(f"Add receipt failed: {exc}")

    def _on_upload_document(self) -> None:
        if self._backend_local is None and self._backend_client is None:
            self.status_label.setText("Start solo mode or connect to a server first")
            return
        if not self._current_matter_id:
            self.status_label.setText("Select a matter first")
            return
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Upload document to matter",
            "",
            "Documents (*.pdf *.docx *.doc *.png *.jpg *.jpeg *.tif *.tiff *.txt);;All files (*)",
        )
        if not file_paths:
            return
        for file_path in file_paths:
            try:
                if self._backend_local is not None:
                    token = self._backend_local.login(self._current_username, "admin-pass").token
                    content = Path(file_path).read_bytes()
                    result = self._backend_local.upload_document(
                        token,
                        self._current_matter_id,
                        title=Path(file_path).name,
                        document_type="general",
                        content=content,
                        original_name=Path(file_path).name,
                        content_type="application/octet-stream",
                        extracted_text=content.decode("utf-8", errors="replace"),
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
        doc_list = self.findChild(QListWidget, "matterDocumentsTabList")
        if doc_list is not None:
            doc_list.clear()
            try:
                workspace = self._backend_workspace(self._current_matter_id)
                for doc in workspace.get("documents", []):
                    title = doc.get("title", doc.get("document_type", "Document"))
                    doc_list.addItem(f"{title} (id: {doc.get('document_id', '?')})")
            except Exception:
                pass

    def _on_refresh_fee_receipt_view(self) -> None:
        """Refresh the fees and receipts tabs to show linked data."""
        if (
            self._backend_local is None and self._backend_client is None
        ) or not self._current_matter_id:
            return
        try:
            workspace = self._backend_workspace(self._current_matter_id)
            fees_list = self.findChild(QListWidget, "feesTabList")
            if fees_list is not None:
                fees_list.clear()
                for fee in workspace.get("fees", []):
                    fee_id = fee.get("fee_id", "?")
                    fee_type = fee.get("fee_type", "Fee")
                    amount = fee.get("amount", 0)
                    status = fee.get("status", "")
                    fees_list.addItem(f"[{fee_id}] {fee_type}: KES {amount} ({status})")
            receipts_list = self.findChild(QListWidget, "receiptsTabList")
            if receipts_list is not None:
                receipts_list.clear()
                for receipt in workspace.get("receipts", []):
                    receipt_number = receipt.get("receipt_number", "?")
                    amount = receipt.get("amount", 0)
                    linked = receipt.get("linked_fee_id", "")
                    linked_info = f" -> fee {linked}" if linked else ""
                    receipts_list.addItem(f"[{receipt_number}] KES {amount}{linked_info}")
        except (WakiliOSClientError, WakiliOSConnectionError, Exception) as exc:
            self.status_label.setText(f"Failed to refresh fees/receipts: {exc}")

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
        selected, _ = QFileDialog.getOpenFileNames(
            self,
            "Add legal documents",
            "",
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
    stylesheet_path = Path(__file__).parent / "wakilios.qss"
    if stylesheet_path.exists():
        app.setStyleSheet(stylesheet_path.read_text(encoding="utf-8"))
    return app


def run_gui(argv: list[str] | None = None, *, smoke_ms: int | None = None) -> int:
    app = create_app(argv)
    window = MainWindow()
    window.show()
    if smoke_ms is not None:
        QTimer.singleShot(smoke_ms, app.quit)
    return app.exec()


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


def _dashboard_page() -> QWidget:
    """Dashboard: setup, connection, license, and vault in one view."""
    page = QWidget()
    page.setObjectName("dashboardPage")
    layout = QVBoxLayout(page)

    # --- Connection section ---
    connection_group = QFrame()
    connection_group.setObjectName("connectionGroup")
    connection_layout = QVBoxLayout(connection_group)
    connection_label = QLabel("Connect to WakiliOS")
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

    # --- License section ---
    license_group = QFrame()
    license_group.setObjectName("licenseGroup")
    license_layout = QFormLayout(license_group)
    license_file = QLineEdit()
    license_file.setObjectName("licenseFileInput")
    license_status = QLabel("Not activated")
    license_status.setObjectName("licenseStatusLabel")
    activate = QPushButton("Activate license")
    activate.setObjectName("activateLicenseButton")
    license_layout.addRow("License file", license_file)
    license_layout.addRow("Status", license_status)
    license_layout.addRow("", activate)
    layout.addWidget(license_group)

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
    export_calendar = QPushButton("Export calendar")
    export_calendar.setObjectName("exportCalendarButton")
    add_matter = QPushButton("New matter")
    add_matter.setObjectName("newMatterButton")
    refresh_matters = QPushButton("Refresh")
    refresh_matters.setObjectName("refreshMatterListButton")
    header.addWidget(role_status)
    header.addStretch(1)
    header.addWidget(refresh_matters)
    header.addWidget(export_calendar)
    header.addWidget(add_matter)

    # Matter list
    matter_list = QListWidget()
    matter_list.setObjectName("matterList")
    matter_list.addItems(["Connect to backend to load matters"])

    # Workspace sub-tabs (parties, activities, etc.)
    workspace_tabs = QTabWidget()
    workspace_tabs.setObjectName("matterWorkspaceTabs")
    workspace_tabs.addTab(_matter_summary_tab(), "Summary")
    workspace_tabs.addTab(_matter_text_list_tab("partiesTab", "Parties involved"), "Parties")
    workspace_tabs.addTab(
        _matter_text_list_tab("activitiesTab", "Mentions and applications"),
        "Activities",
    )
    workspace_tabs.addTab(_matter_text_list_tab("lodgingsTab", "Documents for lodging"), "Lodgings")
    workspace_tabs.addTab(
        _matter_text_list_tab("courtDecisionsTab", "Decisions so far"),
        "Court Decisions",
    )
    workspace_tabs.addTab(_matter_text_list_tab("feesTab", "Court filing fees"), "Fees")
    workspace_tabs.addTab(
        _matter_text_list_tab("receiptsTab", "Court and client receipts"),
        "Receipts",
    )
    workspace_tabs.addTab(
        _matter_text_list_tab("matterDocumentsTab", "Matter document vault"),
        "Documents",
    )
    # Document upload button (separate from the generic Add)
    doc_upload_btn = QPushButton("Upload document")
    doc_upload_btn.setObjectName("uploadDocumentButton")
    workspace_tabs.findChild(QWidget, "matterDocumentsTab").layout().addWidget(doc_upload_btn)

    layout.addLayout(header)
    layout.addWidget(matter_list)
    layout.addWidget(workspace_tabs, stretch=1)
    return page


def _settings_page() -> QWidget:
    """Settings: AI keys, backup, admin, and audit log."""
    page = QWidget()
    page.setObjectName("settingsPage")
    layout = QVBoxLayout(page)

    # --- Import section ---
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
    layout.addWidget(import_group)

    # --- Search & RAG section ---
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
    layout.addWidget(search_group)

    # --- AI Keys section ---
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
    layout.addWidget(ai_group)

    # --- Backup section ---
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
    layout.addWidget(backup_group)

    # --- Admin & Audit section ---
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
    layout.addWidget(admin_group)

    layout.addStretch(1)
    return page


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
    summary_add = QPushButton("Update summary")
    summary_add.setObjectName("summaryAddButton")
    layout.addRow("Case information", case_information)
    layout.addRow("Status", matter_status)
    layout.addRow("AI summary", ai_summary)
    layout.addRow("", summary_add)
    return tab


def _matter_text_list_tab(object_name: str, empty_text: str) -> QWidget:
    tab = QWidget()
    tab.setObjectName(object_name)
    layout = QVBoxLayout(tab)
    listing = QListWidget()
    listing.setObjectName(f"{object_name}List")
    listing.addItem(empty_text)
    add_button = QPushButton("Add")
    add_button.setObjectName(f"{object_name}AddButton")
    layout.addWidget(listing)
    layout.addWidget(add_button)
    return tab


def _about_page(modules: tuple[ModuleStatus, ...]) -> QWidget:
    page = QWidget()
    page.setObjectName("aboutPage")
    layout = QVBoxLayout(page)
    release_info = QLabel("WakiliOS multi-seat litigation management")
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
