"""Manual Windows app E2E runner for source and frozen executable checks."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QLabel, QListWidget, QTextEdit  # noqa: E402

from ui import MainWindow, create_app  # noqa: E402


def run_manual_windows_app_e2e(input_root: Path) -> dict[str, Any]:
    """Run the one-by-one desktop workflow against an input document folder."""

    source_paths = sorted(path for path in input_root.rglob("*") if path.is_file())
    if not source_paths:
        raise ValueError(f"no input documents found in {input_root}")

    start = time.perf_counter()
    app = create_app(["manual-windows-app-e2e"])
    with tempfile.TemporaryDirectory(prefix="dv-manual-app-e2e-") as temporary_dir:
        workspace = Path(temporary_dir)
        window = MainWindow(workspace=workspace / "app-workspace")
        window.show()
        app.processEvents()

        for source_path in source_paths:
            window.import_files([source_path])
            app.processEvents()

        queue = _required_child(window, QListWidget, "documentReviewQueue")
        queue_text = _queue_text(queue)
        import_results = window.manual_session.import_results
        accepted_searchable = [
            result
            for result in import_results
            if result.status == "accepted" and result.text_available
        ]

        rag_questions = tuple(
            f"What does manual corpus topic {index} say about Kenyan court procedure?"
            for index in range(1, 26)
        )
        rag_output = _required_child(window, QTextEdit, "ragCitationPacketOutput")
        rag_failures: list[str] = []
        for question in rag_questions:
            question_box = _required_child(window, QTextEdit, "ragQuestionInput")
            question_box.setPlainText(question)
            window.ask_current_question()
            app.processEvents()
            output_text = rag_output.toPlainText()
            if "Confidence:" not in output_text or "Citations:" not in output_text:
                rag_failures.append(question)

        window.create_backup_and_restore()
        app.processEvents()
        backup_status = _required_child(window, QLabel, "backupStatusLabel").text()
        restore_status = _required_child(window, QLabel, "restoreStatusLabel").text()

        object_files = list((workspace / "app-workspace" / "vault" / "objects").rglob("*.vaultobj"))
        plaintext_probe = b"manual corpus topic 17"
        plaintext_probe_found = any(plaintext_probe in path.read_bytes() for path in object_files)
        source_copies_preserved = all(result.source_copy_preserved for result in import_results)

        report = {
            "input_documents": len(source_paths),
            "queue_items": queue.count(),
            "accepted_searchable_documents": len(accepted_searchable),
            "duplicate_detected": "duplicate" in queue_text,
            "unsupported_detected": "unsupported" in queue_text,
            "extraction_failure_detected": "extraction_failed" in queue_text,
            "ocr_completed_detected": "completed_tesseract" in queue_text,
            "source_copies_preserved": source_copies_preserved,
            "vault_objects": len(object_files),
            "vault_plaintext_probe_found": plaintext_probe_found,
            "rag_questions": len(rag_questions),
            "rag_failures": rag_failures,
            "rag_min_citations": min(
                (result.citation_count for result in window.manual_session.rag_results),
                default=0,
            ),
            "rag_min_confidence": min(
                (result.confidence for result in window.manual_session.rag_results),
                default=0.0,
            ),
            "backup_status": backup_status,
            "restore_status": restore_status,
            "elapsed_seconds": round(time.perf_counter() - start, 3),
        }

        window.close()
        app.processEvents()

    _assert_report(report)
    return report


def _assert_report(report: dict[str, Any]) -> None:
    assert report["queue_items"] == report["input_documents"]
    assert report["accepted_searchable_documents"] >= 50
    assert report["duplicate_detected"]
    assert report["unsupported_detected"]
    assert report["extraction_failure_detected"]
    assert report["ocr_completed_detected"]
    assert report["source_copies_preserved"]
    assert report["vault_objects"] >= 50
    assert not report["vault_plaintext_probe_found"]
    assert report["rag_questions"] == 25
    assert not report["rag_failures"]
    assert report["rag_min_citations"] > 0
    assert report["rag_min_confidence"] > 0
    assert "Backup bytes:" in report["backup_status"]
    assert "Restore verified: True" in report["restore_status"]
    assert "wrong key failed: True" in report["restore_status"]


def _required_child(window: MainWindow, widget_type: type[Any], object_name: str) -> Any:
    child = window.findChild(widget_type, object_name)
    if child is None:
        raise AssertionError(f"missing UI child: {object_name}")
    return child


def _queue_text(queue: QListWidget) -> str:
    return "\n".join(queue.item(index).text() for index in range(queue.count())).lower()
