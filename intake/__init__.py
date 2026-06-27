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
    OCR_COMPLETED,
    OCR_FAILED,
    OCR_NOT_REQUIRED,
    OCR_PENDING,
    ExtractionError,
    ExtractionResult,
    extract_text,
)
from intake.ocr_runtime import (
    TESSERACT_MANIFEST_NAME,
    OcrRuntimeError,
    TesseractOcrEngine,
    TesseractRuntime,
    TesseractRuntimeManifest,
    create_tesseract_manifest,
    discover_tesseract_runtime,
    load_tesseract_manifest,
    validate_tesseract_runtime,
)

__all__ = [
    "ACCEPTED_STATUS",
    "DUPLICATE_STATUS",
    "OCR_COMPLETED",
    "OCR_FAILED",
    "OCR_NOT_REQUIRED",
    "OCR_PENDING",
    "OcrRuntimeError",
    "ExtractionError",
    "ExtractionResult",
    "TesseractRuntime",
    "TesseractRuntimeManifest",
    "TesseractOcrEngine",
    "TESSERACT_MANIFEST_NAME",
    "REJECTED_STATUS",
    "IntakeError",
    "IntakeRecord",
    "create_tesseract_manifest",
    "detect_file_type",
    "discover_tesseract_runtime",
    "extract_text",
    "import_document",
    "list_intake_records",
    "load_tesseract_manifest",
    "validate_tesseract_runtime",
]
