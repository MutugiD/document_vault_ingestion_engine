"""Document intake package for validation, quarantine, extraction, and handoff."""

from intake.core import (
    ACCEPTED_STATUS,
    DUPLICATE_STATUS,
    REJECTED_STATUS,
    IntakeError,
    IntakeRecord,
    detect_file_type,
    import_document,
    list_intake_records,
)

__all__ = [
    "ACCEPTED_STATUS",
    "DUPLICATE_STATUS",
    "REJECTED_STATUS",
    "IntakeError",
    "IntakeRecord",
    "detect_file_type",
    "import_document",
    "list_intake_records",
]
