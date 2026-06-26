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
from intake.ocr_runtime import (
    OcrRuntimeError,
    TesseractRuntime,
    TesseractRuntimeManifest,
    create_tesseract_manifest,
    load_tesseract_manifest,
    validate_tesseract_runtime,
)

__all__ = [
    "ACCEPTED_STATUS",
    "DUPLICATE_STATUS",
    "OCR_FAILED",
    "OCR_NOT_REQUIRED",
    "OCR_PENDING",
    "OcrRuntimeError",
    "ExtractionError",
    "ExtractionResult",
    "TesseractRuntime",
    "TesseractRuntimeManifest",
    "REJECTED_STATUS",
    "IntakeError",
    "IntakeRecord",
    "create_tesseract_manifest",
    "detect_file_type",
    "extract_text",
    "import_document",
    "list_intake_records",
    "load_tesseract_manifest",
    "validate_tesseract_runtime",
]
