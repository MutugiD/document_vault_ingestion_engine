"""Validate the per-matter AI panel, and that uploads are searchable.

The panel is the brief's trusted AI layer (slide 14): ask about *this* matter,
see which of its documents supported the answer, and be told a lawyer must
verify it.

Building it surfaced a defect worth its own assertions. The upload path stored
``content.decode("utf-8", errors="replace")`` as a document's extracted text,
so every uploaded PDF was indexed as its own internals -- xref tables and
stream dictionaries. Search over uploaded documents returned nothing useful and
any answer drawn from one cited gibberish, while still reporting a confident
number. The test for that is simple: the indexed text must not look like a PDF.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from PySide6.QtWidgets import QLabel, QPushButton, QTextEdit  # noqa: E402

import ui.app as ui_app  # noqa: E402
from ui import MainWindow, create_app  # noqa: E402
from ui.app import DEV_UNLOCK_ENV_VAR  # noqa: E402

JUDGMENT = ROOT / "test-output" / "maua-corpus" / "meru-hc-mrima-2019-2805.pdf"

# Markers that only appear if raw PDF bytes were stored as text.
PDF_INTERNALS = ("/Type", "/Filter", "obj", "endstream", "xref", "00000 n")


def main() -> None:
    if not JUDGMENT.exists():
        print(f"MATTER AI PANEL VALIDATION SKIPPED (no corpus at {JUDGMENT})")
        return

    os.environ[DEV_UNLOCK_ENV_VAR] = "1"
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            os.environ["APPDATA"] = str(root / "appdata")
            app = create_app(["validate_matter_ai_panel"])
            window = MainWindow(workspace=root / "workspace")

            def button(name: str) -> QPushButton:
                found = window.findChild(QPushButton, name)
                assert found is not None, f"missing control: {name}"
                return found

            def label(name: str) -> QLabel:
                found = window.findChild(QLabel, name)
                assert found is not None, f"missing label: {name}"
                return found

            def text_box(name: str) -> QTextEdit:
                found = window.findChild(QTextEdit, name)
                assert found is not None, f"missing input: {name}"
                return found

            # ── With no matter open, it declines rather than guessing ────
            text_box("matterAiQuestionInput").setPlainText("What was filed?")
            button("matterAiAskButton").click()
            app.processEvents()
            assert "Open a matter" in label("matterAiSourcesLabel").text()

            button("startSoloButton").click()
            app.processEvents()

            # ── Open a matter from a real judgment and upload it ─────────
            ui_app.QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(JUDGMENT), ""))
            original_exec = ui_app.MatterDialog.exec
            ui_app.MatterDialog.exec = lambda d: (d._on_accept(), 1)[-1]
            try:
                button("newMatterFromDocumentButton").click()
                app.processEvents()
            finally:
                ui_app.MatterDialog.exec = original_exec
            assert window._current_matter_id, "a matter should be open"

            ui_app.QFileDialog.getOpenFileNames = staticmethod(
                lambda *a, **k: ([str(JUDGMENT)], "")
            )
            button("uploadDocumentButton").click()
            app.processEvents()

            # ── An uploaded document is stored as text, not as bytes ─────
            from search import search_documents

            hits = search_documents(
                window._backend_local.vault_root,
                "liability",
                matter_id=window._current_matter_id,
            )
            assert hits, "an uploaded judgment should be searchable"
            snippet = " ".join(h.snippet for h in hits)
            for marker in PDF_INTERNALS:
                assert marker not in snippet, (
                    f"PDF internals were indexed as text ({marker!r}); "
                    f"the upload path is storing raw bytes"
                )

            # ── The panel answers from the matter, and names its sources ──
            text_box("matterAiQuestionInput").setPlainText("How was liability apportioned?")
            button("matterAiAskButton").click()
            app.processEvents()

            sources = label("matterAiSourcesLabel").text()
            assert "passage(s)" in sources and "document(s)" in sources, sources
            assert "none" not in sources.lower(), sources

            answer = text_box("matterAiAnswerOutput").toPlainText()
            assert answer.strip(), "the panel should show the supporting passages"
            for marker in PDF_INTERNALS:
                assert marker not in answer, f"the panel cited PDF internals ({marker!r})"
            assert "[C1]" in answer, "passages should be citation-numbered"

            # ── It always says a lawyer must verify ──────────────────────
            assert "review required" in label("matterAiReviewLabel").text().lower()

            window.close()
            app.processEvents()
    finally:
        os.environ.pop(DEV_UNLOCK_ENV_VAR, None)

    print("MATTER AI PANEL VALIDATION PASS")


if __name__ == "__main__":
    main()
