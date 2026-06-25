"""PySide6 desktop shell and worker pattern."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


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
    """Initial V1 desktop shell."""

    def __init__(self, modules: tuple[ModuleStatus, ...] = DEFAULT_MODULES) -> None:
        super().__init__()
        self.setWindowTitle("Document Vault Ingestion Engine")
        self.setMinimumSize(920, 620)

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(24, 24, 24, 24)
        root_layout.setSpacing(18)

        heading = QLabel("Document Vault Ingestion Engine")
        heading.setObjectName("heading")
        heading.setAlignment(Qt.AlignmentFlag.AlignLeft)
        root_layout.addWidget(heading)

        subtitle = QLabel(
            "Local-first legal document intake, encrypted custody, search, and backup."
        )
        subtitle.setObjectName("subtitle")
        root_layout.addWidget(subtitle)

        module_grid = QGridLayout()
        module_grid.setHorizontalSpacing(12)
        module_grid.setVerticalSpacing(12)
        for index, module in enumerate(modules):
            module_grid.addWidget(_module_card(module), index // 2, index % 2)
        root_layout.addLayout(module_grid)

        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("statusLabel")
        root_layout.addWidget(self.status_label)

        self.selftest_button = QPushButton("Run UI Worker Selftest")
        self.selftest_button.clicked.connect(self.run_worker_selftest)
        root_layout.addWidget(self.selftest_button)

        root_layout.addStretch(1)
        self.setCentralWidget(root)
        self.thread_pool = QThreadPool.globalInstance()

    @Slot()
    def run_worker_selftest(self) -> None:
        self.selftest_button.setEnabled(False)
        self.status_label.setText("Running worker selftest")
        worker = BackgroundWorker(lambda: "Worker selftest pass")
        worker.signals.completed.connect(self._on_worker_completed)
        worker.signals.failed.connect(self._on_worker_failed)
        self.thread_pool.start(worker)

    @Slot(object)
    def _on_worker_completed(self, result: object) -> None:
        self.status_label.setText(str(result))
        self.selftest_button.setEnabled(True)

    @Slot(str)
    def _on_worker_failed(self, message: str) -> None:
        self.status_label.setText(f"Worker selftest failed: {message}")
        self.selftest_button.setEnabled(True)


def create_app(argv: list[str] | None = None) -> QApplication:
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    app = QApplication.instance()
    if isinstance(app, QApplication):
        return app
    return QApplication(list(sys.argv if argv is None else argv))


def run_gui(argv: list[str] | None = None) -> int:
    app = create_app(argv)
    window = MainWindow()
    window.show()
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
