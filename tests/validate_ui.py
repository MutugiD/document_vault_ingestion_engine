"""Validate F8 PySide6 UI shell."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEventLoop, QObject, QTimer  # noqa: E402
from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QTabWidget, QTextEdit  # noqa: E402

from ui import (  # noqa: E402
    DEFAULT_MODULES,
    BackgroundWorker,
    MainWindow,
    create_app,
)
from ui import app as ui_app  # noqa: E402
from ui.app import DEV_UNLOCK_ENV_VAR  # noqa: E402


def main() -> None:
    # The gate must be validated in its shipped state, never under a dev
    # bypass that a developer happened to leave exported.
    os.environ.pop(DEV_UNLOCK_ENV_VAR, None)

    app = create_app(["validate_ui"])
    window = MainWindow()
    assert window.windowTitle() == "JurisNuru"
    assert window.minimumWidth() >= 900
    assert len(DEFAULT_MODULES) >= 7
    assert window.tabs.count() == 4  # Dashboard, Workspace, Settings, About
    assert [window.tabs.tabText(index) for index in range(window.tabs.count())] == [
        "Dashboard",
        "Workspace",
        "Settings",
        "About",
    ]
    # Locked at startup: the gate is showing and the application is not
    # merely disabled behind it, it is not in the visible widget tree at all.
    assert window._license_active is False
    assert window.application_stack.currentIndex() == 0
    assert window.application_stack.currentWidget() is window.license_gate
    assert window.application_stack.currentWidget().findChild(QObject, "dashboardPage") is None
    assert window.tabs.widget(0).findChild(QObject, "licenseGroup") is None
    expected_widgets = (
        "licensePage",
        "licenseGroup",
        "licenseFileInput",
        "browseLicenseButton",
        "licenseStatusLabel",
        "licenseInstallationLabel",
        "dashboardPage",
        "connectionGroup",
        "setupGroup",
        "firmNameInput",
        "primaryUserInput",
        "deviceNicknameInput",
        "recoveryKeyConfirmedCheck",
        "vaultGroup",
        "vaultPathInput",
        "recoveryKeyInput",
        "workspacePage",
        "matterList",
        "roleStatusLabel",
        "exportCalendarButton",
        "matterWorkspaceTabs",
        "summaryTab",
        "matterCaseInformationInput",
        "matterStatusLabel",
        "aiMatterSummaryOutput",
        "partiesTab",
        "activitiesTab",
        "lodgingsTab",
        "courtDecisionsTab",
        "feesTab",
        "receiptsTab",
        "matterDocumentsTab",
        "filingRecordTab",
        "settingsPage",
        "importGroup",
        "documentReviewQueue",
        "ocrStatusLabel",
        "duplicateStatusLabel",
        "searchGroup",
        "matterSearchInput",
        "ragQuestionInput",
        "ragCitationPacketOutput",
        "aiKeysGroup",
        "openaiApiKeyInput",
        "anthropicApiKeyInput",
        "googleApiKeyInput",
        "azureOpenaiApiKeyInput",
        "mistralApiKeyInput",
        "providerKeyStatusLabel",
        "saveProviderSettingsButton",
        "backupGroup",
        "backupStatusLabel",
        "restoreStatusLabel",
        "adminGroup",
        "installationStatusLabel",
        "entitlementStatusLabel",
        "aboutPage",
        "releaseInfoLabel",
        "runNativeWorkflowButton",
        "backendConnectionDialog",
        "serverUrlInput",
        "backendUsernameInput",
        "backendPasswordInput",
        "backendStatusLabel",
        "connectButton",
        "refreshMatterListButton",
        "summaryAddButton",
        "uploadDocumentButton",
        "auditLogList",
        "refreshAuditLogButton",
        "startSoloButton",
    )
    for object_name in expected_widgets:
        assert window.findChild(QObject, object_name) is not None, object_name

    license_input = window.findChild(QLineEdit, "licenseFileInput")
    activate_button = window.findChild(QPushButton, "activateLicenseButton")
    license_status = window.findChild(QLabel, "licenseStatusLabel")
    assert license_input is not None
    assert activate_button is not None
    assert license_status is not None
    license_input.setText(str(ROOT / "resources" / "license_public_key.pem"))
    activate_button.click()
    assert "public verification key" in license_status.text()
    assert "Expecting value" not in window.status_label.text()
    assert window.application_stack.currentIndex() == 0

    # The installation identity is the one file a user is most likely to
    # mistake for a license: same directory, same .json shape, no signature.
    with tempfile.TemporaryDirectory() as temp_dir:
        identity_file = Path(temp_dir) / "installation.json"
        identity_file.write_text(
            json.dumps({"installation_id": "ec65d956-test", "created_at": "2026-01-01T00:00:00"}),
            encoding="utf-8",
        )
        license_input.setText(str(identity_file))
        activate_button.click()
    assert "installation identity" in license_status.text()
    assert window.application_stack.currentIndex() == 0

    window._set_license_state(True, "Active: validation")
    assert window.application_stack.currentIndex() == 1
    assert all(window.tabs.isTabEnabled(index) for index in range(window.tabs.count()))

    matter_workspace = window.findChild(QTabWidget, "matterWorkspaceTabs")
    assert matter_workspace is not None
    assert [matter_workspace.tabText(index) for index in range(matter_workspace.count())] == [
        "Summary",
        "Parties",
        "Activities",
        "Lodgings",
        "Court Decisions",
        "Fees",
        "Receipts",
        "Documents",
        "Filing record",
    ]

    openai_key = window.findChild(QLineEdit, "openaiApiKeyInput")
    provider_status = window.findChild(QLabel, "providerKeyStatusLabel")
    save_provider = window.findChild(QPushButton, "saveProviderSettingsButton")
    assert openai_key is not None
    assert provider_status is not None
    assert save_provider is not None
    openai_key.setText("sk-ui-secret-123456")
    save_provider.click()
    assert "openai" in provider_status.text()
    assert "sk-ui-secret" not in provider_status.text()
    assert openai_key.text() == ""

    admin_sync = window.findChild(QPushButton, "adminSyncButton")
    installation_status = window.findChild(QLabel, "installationStatusLabel")
    entitlement_status = window.findChild(QLabel, "entitlementStatusLabel")
    assert admin_sync is not None
    assert installation_status is not None
    assert entitlement_status is not None
    admin_sync.click()
    app.processEvents()
    assert installation_status.text() == "active"
    assert "paid=True" in entitlement_status.text()
    assert "cloud=True" in entitlement_status.text()
    assert "rag=True" in entitlement_status.text()
    assert "hosted_ai=False" in entitlement_status.text()
    assert "sk-ui-secret" not in entitlement_status.text()

    loop = QEventLoop()
    worker = BackgroundWorker(lambda: "worker-ok")
    result: dict[str, object] = {}
    worker.signals.completed.connect(lambda value: (result.update({"value": value}), loop.quit()))
    worker.signals.failed.connect(lambda message: (result.update({"error": message}), loop.quit()))
    window.thread_pool.start(worker)
    QTimer.singleShot(5000, loop.quit)
    loop.exec()

    assert result.get("value") == "worker-ok"
    assert "error" not in result

    workflow_loop = QEventLoop()
    workflow_button = window.findChild(QPushButton, "runNativeWorkflowButton")
    status_label = window.findChild(QLabel, "statusLabel")
    rag_output = window.findChild(QTextEdit, "ragCitationPacketOutput")
    assert workflow_button is not None
    assert status_label is not None
    assert rag_output is not None
    workflow_button.click()

    def maybe_quit_workflow() -> None:
        if "Native workflow pass" in status_label.text():
            workflow_loop.quit()

    poll_timer = QTimer()
    poll_timer.timeout.connect(maybe_quit_workflow)
    poll_timer.start(100)
    QTimer.singleShot(15000, workflow_loop.quit)
    workflow_loop.exec()
    poll_timer.stop()

    assert "Native workflow pass" in status_label.text()
    assert "RAG citations:" in rag_output.toPlainText()
    assert "sk-ui-secret" not in status_label.text()
    assert "sk-ui-secret" not in rag_output.toPlainText()
    assert "invoice default evidence" not in rag_output.toPlainText()

    window.close()
    app.processEvents()

    # The dev bypass is production code and is tested as such: it opens the
    # gate when exported, and it is inert when the build is frozen.
    os.environ[DEV_UNLOCK_ENV_VAR] = "1"
    try:
        unlocked = MainWindow()
        assert unlocked._license_active is True
        assert unlocked.application_stack.currentIndex() == 1
        assert "DEVELOPMENT BUILD" in unlocked.findChild(QLabel, "licenseStatusLabel").text()
        unlocked.close()
        app.processEvents()

        sys.frozen = True  # type: ignore[attr-defined]
        try:
            assert ui_app._dev_unlock_requested() is False
            frozen = MainWindow()
            assert frozen._license_active is False
            assert frozen.application_stack.currentIndex() == 0
            frozen.close()
            app.processEvents()
        finally:
            del sys.frozen  # type: ignore[attr-defined]
    finally:
        os.environ.pop(DEV_UNLOCK_ENV_VAR, None)

    print("UI VALIDATION PASS")


if __name__ == "__main__":
    main()
