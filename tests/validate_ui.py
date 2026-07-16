"""Validate F8 PySide6 UI shell."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEventLoop, QObject, QTimer  # noqa: E402
from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QTabWidget, QTextEdit  # noqa: E402

from ui import DEFAULT_MODULES, BackgroundWorker, BackendConnectionDialog, MainWindow, create_app  # noqa: E402


def main() -> None:
    app = create_app(["validate_ui"])
    window = MainWindow()
    assert window.windowTitle() == "WakiliOS"
    assert window.minimumWidth() >= 900
    assert len(DEFAULT_MODULES) >= 7
    assert window.tabs.count() == 10
    expected_widgets = (
        "setupPage",
        "firmNameInput",
        "primaryUserInput",
        "deviceNicknameInput",
        "recoveryKeyConfirmedCheck",
        "licensePage",
        "licenseFileInput",
        "licenseStatusLabel",
        "vaultPage",
        "vaultPathInput",
        "recoveryKeyInput",
        "matterPage",
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
        "importPage",
        "documentReviewQueue",
        "ocrStatusLabel",
        "duplicateStatusLabel",
        "searchRagPage",
        "matterSearchInput",
        "ragQuestionInput",
        "ragCitationPacketOutput",
        "providerKeysPage",
        "openaiApiKeyInput",
        "anthropicApiKeyInput",
        "googleApiKeyInput",
        "azureOpenaiApiKeyInput",
        "mistralApiKeyInput",
        "providerKeyStatusLabel",
        "saveProviderSettingsButton",
        "backupPage",
        "backupStatusLabel",
        "restoreStatusLabel",
        "adminPage",
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
    )
    for object_name in expected_widgets:
        assert window.findChild(QObject, object_name) is not None, object_name

    matter_workspace = window.findChild(QTabWidget, "matterWorkspaceTabs")
    assert matter_workspace is not None
    assert [
        matter_workspace.tabText(index) for index in range(matter_workspace.count())
    ] == [
        "Summary",
        "Parties",
        "Activities",
        "Lodgings",
        "Court Decisions",
        "Fees",
        "Receipts",
        "Documents",
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

    print("UI VALIDATION PASS")


if __name__ == "__main__":
    main()
