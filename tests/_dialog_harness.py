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
    return int(QDialog.DialogCode.Accepted if dialog.result() else QDialog.DialogCode.Rejected)


def autofill_dialogs(sample: str = "Test") -> Callable[[], None]:
    """Make both dialogs self-accepting. Returns a restore callable."""
    original_matter = ui_app.MatterDialog.exec
    original_record = ui_app.MatterRecordDialog.exec

    def value_for(field_spec) -> str:
        if getattr(field_spec, "numeric", False):
            return "1500"
        if field_spec.choices:
            return field_spec.choices[0]
        return f"{sample} {field_spec.label}"

    ui_app.MatterDialog.exec = lambda self: _fill(self, value_for)
    ui_app.MatterRecordDialog.exec = lambda self: _fill(self, value_for)

    def restore() -> None:
        ui_app.MatterDialog.exec = original_matter
        ui_app.MatterRecordDialog.exec = original_record

    return restore
