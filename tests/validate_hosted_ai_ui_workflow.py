"""Validate hosted AI is reachable from the manual app and desktop UI workflow."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import fitz

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QPushButton, QTextEdit  # noqa: E402

from core import ManualAppSession  # noqa: E402
from ui import MainWindow, create_app  # noqa: E402


def main() -> None:
    provider_environment = {
        "DOCUMENT_VAULT_OPENAI_API_KEY": "sk-hosted-ui-validator-secret"
    }
    with tempfile.TemporaryDirectory() as temporary_dir:
        workspace = Path(temporary_dir)
        source_pdf = workspace / "hosted-ai-ui-source.pdf"
        _write_pdf(
            source_pdf,
            "The local affidavit supports an injunction because the invoice default "
            "shows commercial urgency and risk of dissipation.",
        )

        session = ManualAppSession(workspace / "session")
        import_result = session.import_file(source_pdf)
        assert import_result.vault_object_created
        hosted = session.hosted_ai_answer(
            "What local citation supports the injunction?",
            provider_environment=provider_environment,
        )
        assert hosted.status == "hosted_answer"
        assert hosted.citation_count >= 1
        assert hosted.answer
        assert "sk-hosted-ui-validator-secret" not in hosted.summary()

        app = create_app(["validate_hosted_ai_ui_workflow"])
        window = MainWindow(workspace=workspace / "ui")
        window.provider_environment = provider_environment
        hosted_button = window.findChild(QPushButton, "askHostedAiButton")
        output = window.findChild(QTextEdit, "ragCitationPacketOutput")
        assert hosted_button is not None
        assert output is not None
        hosted_button.click()
        app.processEvents()
        text = output.toPlainText()
        assert "Hosted status:" in text
        assert "sk-hosted-ui-validator-secret" not in text
        assert "local RAG fallback" in text
        window.close()
        app.processEvents()

    print("HOSTED AI UI WORKFLOW VALIDATION PASS")


def _write_pdf(path: Path, text: str) -> None:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    document.save(path)
    document.close()


if __name__ == "__main__":
    main()
