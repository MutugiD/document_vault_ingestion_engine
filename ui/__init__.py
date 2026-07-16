"""User interface package for PySide6 windows and workers."""

APP_VERSION = "0.1.0"  # noqa: E305

from ui.app import (  # noqa: E402
    DEFAULT_MODULES,
    BackendConnectionDialog,
    BackgroundWorker,
    MainWindow,
    ModuleStatus,
    WorkerSignals,
    create_app,
    run_gui,
)

__all__ = [
    "DEFAULT_MODULES",
    "BackendConnectionDialog",
    "BackgroundWorker",
    "MainWindow",
    "ModuleStatus",
    "WorkerSignals",
    "create_app",
    "run_gui",
]
