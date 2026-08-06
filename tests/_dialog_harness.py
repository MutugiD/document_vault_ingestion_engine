"""Drive JurisNuru's modal dialogs from a headless test.

Opening a matter and adding a record both use a modal ``QDialog``. ``exec()``
blocks on its own event loop, so a test that clicks the button and waits will
hang forever. Replacing ``exec`` fills the form and accepts it, leaving
construction, the field spec and validation to run for real.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QComboBox, QDialog

import ui.app as ui_app


def _fill(dialog, value_for: Callable[[object], str]) -> int:
    for field_spec in dialog._field_specs():
        widget = dialog._inputs[field_spec.name]
        value = value_for(field_spec)
        if isinstance(widget, QComboBox):
            widget.setCurrentText(value)
        else:
            widget.setText(value)
    dialog._on_accept()
    if not dialog.result():
        # Say why. A refused dialog used to surface several frames later as a
        # bare "assert window._current_matter_id", which reads as a broken
        # product rather than a harness feeding the form a value it rejects.
        raise AssertionError(
            f"{dialog.objectName()} refused the values this harness supplied: "
            f"{dialog.error_label.text() or 'no reason given'}"
        )
    return int(QDialog.DialogCode.Accepted)


def autofill_dialogs(sample: str = "Test", *, date_value: str = "2026-08-06") -> Callable[[], None]:
    """Make both dialogs self-accepting. Returns a restore callable."""
    original_matter = ui_app.MatterDialog.exec
    original_record = ui_app.MatterRecordDialog.exec

    def value_for(field_spec) -> str:
        if getattr(field_spec, "numeric", False):
            return "1500"
        # Date fields are validated now, so prose no longer passes. That is the
        # product being right: a due date reading "Test Due date" is what used
        # to reach the calendar export and break it.
        if getattr(field_spec, "is_date", False):
            return date_value
        if field_spec.choices:
            return field_spec.choices[0]
        return f"{sample} {field_spec.label}"

    ui_app.MatterDialog.exec = lambda self: _fill(self, value_for)
    ui_app.MatterRecordDialog.exec = lambda self: _fill(self, value_for)

    def restore() -> None:
        ui_app.MatterDialog.exec = original_matter
        ui_app.MatterRecordDialog.exec = original_record

    return restore
