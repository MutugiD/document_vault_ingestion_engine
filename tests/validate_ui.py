"""Validate F8 PySide6 UI shell."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402

from ui import DEFAULT_MODULES, BackgroundWorker, MainWindow, create_app  # noqa: E402


def main() -> None:
    app = create_app(["validate_ui"])
    window = MainWindow()
    assert window.windowTitle() == "Document Vault Ingestion Engine"
    assert window.minimumWidth() >= 900
    assert len(DEFAULT_MODULES) >= 7

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
    window.close()
    app.processEvents()

    print("UI VALIDATION PASS")


if __name__ == "__main__":
    main()
