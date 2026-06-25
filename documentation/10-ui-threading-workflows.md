# 10 - UI Threading Workflows

## Purpose

Provide a responsive Windows desktop UI for intake, matters, backup, and restore.

## UI Stack

PySide6.

## Required Windows

- License/setup.
- Main dashboard.
- Intake queue.
- Matter/document workspace.
- Backup and restore.

## Threading Rules

- Long-running intake/OCR/backup work runs outside the UI thread.
- Workers emit progress and status.
- Cancellation is cooperative.
- Closing during a job requires confirmation.

## F8 Implementation Boundary

The first UI slice implements:

- PySide6 application shell.
- Main window with module readiness cards.
- `--gui` application entrypoint.
- `QRunnable` worker pattern with completion/failure signals.
- Offscreen UI validation for CI.

Full setup wizard, intake queue screens, matter workspace, backup/restore forms, and admin screens are later UI slices.

## Verification

`tests/validate_ui.py` uses the Qt offscreen platform to instantiate the app, open the main window, and verify the worker-thread pattern.
