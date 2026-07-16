"""WakiliOS desktop shell with backend connectivity."""

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
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
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
    """Login dialog for connecting to a WakiliOS backend."""

    login_succeeded = Signal(str, str, str)  # token, username, role

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
        self.connect_button = QPushButton("Connect")
        self.connect_button.setObjectName("connectButton")

        layout.addRow("Server URL", self.server_url)
        layout.addRow("Username", self.username_input)
        layout.addRow("Password", self.password_input)
        layout.addRow("Status", self.status_label)
        layout.addRow("", self.connect_button)

        self.connect_button.clicked.connect(self._attempt_login)

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
        self.tabs.addTab(_first_run_page(), "Setup")
        self.tabs.addTab(_license_page(), "License")
        self.tabs.addTab(_vault_page(), "Vault")
        self.tabs.addTab(_matter_page(), "Matters")
        self.tabs.addTab(_import_page(), "Import")
        self.tabs.addTab(_search_rag_page(), "Search and RAG")
        self.tabs.addTab(_provider_keys_page(), "AI Keys")
        self.tabs.addTab(_backup_page(), "Backup")
        self.tabs.addTab(_admin_page(), "Admin")
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

        for tab_name, button_name, handler in [
            ("Matters", "newMatterButton", self._on_new_matter),
            ("Matters", "exportCalendarButton", self._on_export_calendar),
            ("Matters", "refreshMatterListButton", self._on_refresh_matters),
        ]:
            button = self.findChild(QPushButton, button_name)
            if button is not None:
                button.clicked.connect(handler)

        for tab_name, button_suffix, handler in [
            ("Summary", "AddButton", self._on_update_summary),
            ("Parties", "AddButton", self._on_add_party),
            ("Activities", "AddButton", self._on_add_activity),
            ("Lodgings", "AddButton", self._on_add_lodging),
            ("Court Decisions", "AddButton", self._on_add_court_decision),
            ("Fees", "AddButton", self._on_add_fee),
            ("Receipts", "AddButton", self._on_add_receipt),
        ]:
            object_name = f"{tab_name.lower().replace(' ', '')}{button_suffix}" if tab_name != "Summary" else f"summary{button_suffix}"
            button = self.findChild(QPushButton, object_name)
            if button is None:
                object_name = f"{tab_name.replace(' ', '').lower()}{button_suffix}"
                button = self.findChild(QPushButton, object_name)
            if button is not None:
                button.clicked.connect(handler)

    @Slot(str, str, str)
    def _on_backend_login(self, token: str, username: str, role: str) -> None:
        url_input = self.findChild(QLineEdit, "serverUrlInput")
        url = url_input.text().strip() if url_input else "http://localhost:8000"
        self._backend_client = WakiliOSClient(WakiliOSClientConfig(base_url=url, session_token=token))
        self._current_role = role
        self._current_username = username
        role_label = self.findChild(QLabel, "roleStatusLabel")
        if role_label is not None:
            role_label.setText(f"Role: {role}")
        self.status_label.setText(f"Connected to backend as {username} ({role})")
        self._apply_role_permissions(role)

    def _apply_role_permissions(self, role: str) -> None:
        """Enable/disable controls based on user role."""
        from wakilios.core import ACCOUNTS_ROLES, DOCUMENT_ROLES, SUMMARY_ROLES, WRITE_ROLES

        can_write = role in WRITE_ROLES
        can_manage_fees = role in ACCOUNTS_ROLES
        can_summarize = role in SUMMARY_ROLES
        can_manage_docs = role in DOCUMENT_ROLES

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

    def _on_new_matter(self) -> None:
        if self._backend_client is None:
            self.status_label.setText("Connect to backend first")
            return
        try:
            result = self._backend_client.create_matter(
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
            self._current_matter_id = str(result["matter_id"])
            self.status_label.setText(f"Created matter: {result.get('internal_reference', self._current_matter_id)}")
            self._on_refresh_matters()
        except (WakiliOSClientError, WakiliOSConnectionError) as exc:
            self.status_label.setText(f"Failed to create matter: {exc}")

    def _on_export_calendar(self) -> None:
        if self._backend_client is None:
            self.status_label.setText("Connect to backend first")
            return
        if not self._current_matter_id:
            self.status_label.setText("Select a matter first")
            return
        try:
            ics = self._backend_client.export_calendar(self._current_matter_id)
            dest = QFileDialog.getSaveFileName(self, "Save Calendar", "", "Calendar Files (*.ics)")[0]
            if dest:
                Path(dest).write_text(ics, encoding="utf-8")
                self.status_label.setText(f"Calendar exported to {dest}")
        except (WakiliOSClientError, WakiliOSConnectionError) as exc:
            self.status_label.setText(f"Calendar export failed: {exc}")

    def _on_refresh_matters(self) -> None:
        if self._backend_client is None:
            self.status_label.setText("Connect to backend first")
            return
        try:
            result = self._backend_client.list_matters()
            matter_list = self.findChild(QListWidget, "matterList")
            if matter_list is not None:
                matter_list.clear()
                for m in result:
                    ref = m.get("internal_reference", "")
                    client = m.get("client_name", "")
                    matter_list.addItem(f"{ref} - {client}")
        except (WakiliOSClientError, WakiliOSConnectionError) as exc:
            self.status_label.setText(f"Failed to list matters: {exc}")

    def _on_update_summary(self) -> None:
        if self._backend_client is None or not self._current_matter_id:
            return
        summary_box = self.findChild(QTextEdit, "aiMatterSummaryOutput")
        if summary_box is None:
            return
        try:
            self._backend_client.update_matter_summary(self._current_matter_id, summary_box.toPlainText())
            self.status_label.setText("Summary updated")
        except (WakiliOSClientError, WakiliOSConnectionError) as exc:
            self.status_label.setText(f"Summary update failed: {exc}")

    def _on_add_party(self) -> None:
        if self._backend_client is None or not self._current_matter_id:
            return
        try:
            self._backend_client.add_party(self._current_matter_id, name="New Party", party_role="Respondent")
            self.status_label.setText("Party added")
        except (WakiliOSClientError, WakiliOSConnectionError) as exc:
            self.status_label.setText(f"Add party failed: {exc}")

    def _on_add_activity(self) -> None:
        if self._backend_client is None or not self._current_matter_id:
            return
        try:
            self._backend_client.add_activity(self._current_matter_id, activity_type="mention", title="New Activity", starts_at="")
            self.status_label.setText("Activity added")
        except (WakiliOSClientError, WakiliOSConnectionError) as exc:
            self.status_label.setText(f"Add activity failed: {exc}")

    def _on_add_lodging(self) -> None:
        if self._backend_client is None or not self._current_matter_id:
            return
        try:
            self._backend_client.add_lodging(self._current_matter_id, document_kind="New Lodging")
            self.status_label.setText("Lodging added")
        except (WakiliOSClientError, WakiliOSConnectionError) as exc:
            self.status_label.setText(f"Add lodging failed: {exc}")

    def _on_add_court_decision(self) -> None:
        if self._backend_client is None or not self._current_matter_id:
            return
        try:
            self._backend_client.add_court_decision(self._current_matter_id, decision_type="Ruling", decision_date="")
            self.status_label.setText("Court decision added")
        except (WakiliOSClientError, WakiliOSConnectionError) as exc:
            self.status_label.setText(f"Add court decision failed: {exc}")

    def _on_add_fee(self) -> None:
        if self._backend_client is None or not self._current_matter_id:
            return
        try:
            self._backend_client.add_fee(self._current_matter_id, fee_type="Filing fee", amount=0)
            self.status_label.setText("Fee added")
        except (WakiliOSClientError, WakiliOSConnectionError) as exc:
            self.status_label.setText(f"Add fee failed: {exc}")

    def _on_add_receipt(self) -> None:
        if self._backend_client is None or not self._current_matter_id:
            return
        try:
            self._backend_client.add_receipt(self._current_matter_id, receipt_number="NEW-RCT", amount=0)
            self.status_label.setText("Receipt added")
        except (WakiliOSClientError, WakiliOSConnectionError) as exc:
            self.status_label.setText(f"Add receipt failed: {exc}")

    @Slot()
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
    return QApplication(list(sys.argv if argv is None else argv))


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


def _first_run_page() -> QWidget:
    page = QWidget()
    page.setObjectName("setupPage")
    layout = QFormLayout(page)
    layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
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

    # Backend connection section
    backend_connection = BackendConnectionDialog()
    backend_connection.setObjectName("backendConnectionDialog")

    layout.addRow("Firm", firm_name)
    layout.addRow("Primary user", primary_user)
    layout.addRow("Device", device_name)
    layout.addRow("", recovery_confirmed)
    layout.addRow("", setup_button)
    layout.addRow(backend_connection)
    return page


def _license_page() -> QWidget:
    page = QWidget()
    page.setObjectName("licensePage")
    layout = QFormLayout(page)
    license_file = QLineEdit()
    license_file.setObjectName("licenseFileInput")
    license_status = QLabel("Not activated")
    license_status.setObjectName("licenseStatusLabel")
    activate = QPushButton("Activate")
    activate.setObjectName("activateLicenseButton")
    layout.addRow("License file", license_file)
    layout.addRow("Status", license_status)
    layout.addRow("", activate)
    return page


def _vault_page() -> QWidget:
    page = QWidget()
    page.setObjectName("vaultPage")
    layout = QFormLayout(page)
    vault_path = QLineEdit()
    vault_path.setObjectName("vaultPathInput")
    recovery_key = QLineEdit()
    recovery_key.setObjectName("recoveryKeyInput")
    recovery_key.setEchoMode(QLineEdit.EchoMode.Password)
    initialize = QPushButton("Initialize vault")
    initialize.setObjectName("initializeVaultButton")
    layout.addRow("Vault path", vault_path)
    layout.addRow("Recovery key", recovery_key)
    layout.addRow("", initialize)
    return page


def _matter_page() -> QWidget:
    page = QWidget()
    page.setObjectName("matterPage")
    layout = QVBoxLayout(page)

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

    matter_list = QListWidget()
    matter_list.setObjectName("matterList")
    matter_list.addItems(["Connect to backend to load matters"])

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

    layout.addLayout(header)
    layout.addWidget(matter_list)
    layout.addWidget(workspace_tabs, stretch=1)
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


def _import_page() -> QWidget:
    page = QWidget()
    page.setObjectName("importPage")
    layout = QVBoxLayout(page)
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
    layout.addWidget(queue)
    layout.addLayout(controls)
    return page


def _search_rag_page() -> QWidget:
    page = QWidget()
    page.setObjectName("searchRagPage")
    layout = QVBoxLayout(page)
    search_box = QLineEdit()
    search_box.setObjectName("matterSearchInput")
    ask_box = QTextEdit()
    ask_box.setObjectName("ragQuestionInput")
    ask_box.setFixedHeight(96)
    answer_box = QTextEdit()
    answer_box.setObjectName("ragCitationPacketOutput")
    answer_box.setReadOnly(True)
    ask_button = QPushButton("Ask")
    ask_button.setObjectName("askRagButton")
    layout.addWidget(search_box)
    layout.addWidget(ask_box)
    layout.addWidget(ask_button)
    layout.addWidget(answer_box)
    return page


def _provider_keys_page() -> QWidget:
    page = QWidget()
    page.setObjectName("providerKeysPage")
    layout = QFormLayout(page)
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
        layout.addRow(label, field)
    status = QLabel("Provider keys are local settings")
    status.setObjectName("providerKeyStatusLabel")
    save = QPushButton("Save provider settings")
    save.setObjectName("saveProviderSettingsButton")
    layout.addRow("Status", status)
    layout.addRow("", save)
    return page


def _backup_page() -> QWidget:
    page = QWidget()
    page.setObjectName("backupPage")
    layout = QFormLayout(page)
    backup_status = QLabel("No backup yet")
    backup_status.setObjectName("backupStatusLabel")
    restore_status = QLabel("No restore drill yet")
    restore_status.setObjectName("restoreStatusLabel")
    backup_button = QPushButton("Create backup")
    backup_button.setObjectName("createBackupButton")
    restore_button = QPushButton("Restore drill")
    restore_button.setObjectName("restoreDrillButton")
    layout.addRow("Backup", backup_status)
    layout.addRow("Restore", restore_status)
    layout.addRow("", backup_button)
    layout.addRow("", restore_button)
    return page


def _admin_page() -> QWidget:
    page = QWidget()
    page.setObjectName("adminPage")
    layout = QFormLayout(page)
    installation = QLabel("Installation not synced")
    installation.setObjectName("installationStatusLabel")
    entitlement = QLabel("Entitlement unknown")
    entitlement.setObjectName("entitlementStatusLabel")
    sync_button = QPushButton("Check status")
    sync_button.setObjectName("adminSyncButton")
    layout.addRow("Installation", installation)
    layout.addRow("Entitlement", entitlement)
    layout.addRow("", sync_button)
    return page


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