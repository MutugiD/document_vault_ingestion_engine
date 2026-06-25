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
from intake.extraction import (
    OCR_FAILED,
    OCR_NOT_REQUIRED,
    OCR_PENDING,
    ExtractionError,
    ExtractionResult,
    extract_text,
)

__all__ = [
    "ACCEPTED_STATUS",
    "DUPLICATE_STATUS",
    "OCR_FAILED",
    "OCR_NOT_REQUIRED",
    "OCR_PENDING",
    "ExtractionError",
    "ExtractionResult",
    "REJECTED_STATUS",
    "IntakeError",
    "IntakeRecord",
    "detect_file_type",
    "extract_text",
    "import_document",
    "list_intake_records",
]
