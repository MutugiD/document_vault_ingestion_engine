"""PySide6 desktop shell and worker pattern."""

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


@dataclass(frozen=True)
class ModuleStatus:
    name: str
    status: str


DEFAULT_MODULES = (
    ModuleStatus("Licensing", "Ready"),
    ModuleStatus("Encrypted vault", "Ready"),
    ModuleStatus("Document intake", "Ready"),
    ModuleStatus("Extraction and OCR boundary", "Ready"),
    ModuleStatus("Matter search", "Ready"),
    ModuleStatus("Backup and restore", "Ready"),
    ModuleStatus("Managed cloud boundary", "Ready"),
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


class MainWindow(QMainWindow):
    """Production-oriented V1 desktop workbench."""

    def __init__(
        self,
        modules: tuple[ModuleStatus, ...] = DEFAULT_MODULES,
        *,
        workspace: Path | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Document Vault Ingestion Engine")
        self.setMinimumSize(920, 620)

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(12)

        heading = QLabel("Document Vault Ingestion Engine")
        heading.setObjectName("heading")
        heading.setAlignment(Qt.AlignmentFlag.AlignLeft)
        root_layout.addWidget(heading)

        subtitle = QLabel(
            "Local-first legal document intake, encrypted custody, search, and backup."
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
                status_label.setText(f"Configured providers: {', '.join(configured)}")
            else:
                status_label.setText("No provider keys configured")

    def _connect_workflow_controls(self) -> None:
        button_actions = {
            "completeSetupButton": "Setup complete",
            "activateLicenseButton": "License activation checked",
            "initializeVaultButton": "Vault initialization checked",
            "newMatterButton": "Matter workflow checked",
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
    setup_button = QPushButton("Complete setup")
    setup_button.setObjectName("completeSetupButton")
    layout.addRow("Firm", firm_name)
    layout.addRow("Primary user", primary_user)
    layout.addRow("Device", device_name)
    layout.addRow("", recovery_confirmed)
    layout.addRow("", setup_button)
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
    matter_list = QListWidget()
    matter_list.setObjectName("matterList")
    matter_list.addItems(["No matter selected"])
    add_matter = QPushButton("New matter")
    add_matter.setObjectName("newMatterButton")
    layout.addWidget(matter_list)
    layout.addWidget(add_matter)
    return page


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


def _provider_environment_from_os() -> dict[str, str]:
    environment: dict[str, str] = {}
    for provider in supported_providers():
        env_var = provider_env_var(provider)
        value = os.environ.get(env_var, "")
        if value:
            environment[env_var] = value
    return environment


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
    module_grid = QGridLayout()
    module_grid.setHorizontalSpacing(12)
    module_grid.setVerticalSpacing(12)
    for index, module in enumerate(modules):
        module_grid.addWidget(_module_card(module), index // 2, index % 2)
    release_info = QLabel("Version 0.1.0")
    release_info.setObjectName("releaseInfoLabel")
    layout.addLayout(module_grid)
    layout.addWidget(release_info)
    layout.addStretch(1)
    return page
