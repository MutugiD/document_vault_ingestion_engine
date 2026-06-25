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

## Verification

`tests/validate_ui.py` will use offscreen/headless UI checks once UI begins.
