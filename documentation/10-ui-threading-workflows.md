# 10 - UI Threading Workflows

## Purpose

Provide a responsive Windows desktop UI for intake, matters, backup, restore, licensing, and local RAG.

## UI Stack

PySide6.

## Required Windows

- License/setup.
- Main dashboard.
- Intake queue.
- Matter/document workspace.
- Backup and restore.
- Admin/license status.
- Search and Local Matter RAG.

## F25 Workflow Surface

The production workbench includes tabs for:

- first-run setup
- license activation
- vault initialization and recovery key entry
- matter list
- document import/review queue
- OCR status and duplicate status
- matter search and Local Matter RAG question panel
- backup status and restore drill
- admin/license status
- release/about information

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

F25 expands the shell into workflow tabs for setup, licensing, vault initialization, matters, import/OCR review, search/RAG, backup/restore, admin status, and release information. Later UI slices wire these controls to the live vault/intake/search/backup services.

## Verification

`tests/validate_ui.py` uses the Qt offscreen platform to instantiate the app, open the main window, verify the workflow tabs and key controls, and verify the worker-thread pattern.
