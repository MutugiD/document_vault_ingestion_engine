"""Validate that OCR resolves to a usable engine, and says so when it cannot.

The shipped bundle contained no OCR engine, and two separate defects kept that
invisible:

* ``main.spec`` bundles ``runtime/tesseract`` only if it exists, and nothing
  staged it, so the packaged application had nothing to run.
* ``resolve_ocr_engine()`` returned the *runtime* rather than the engine
  adapter, so even a present runtime produced an object with no
  ``recognize_image``. That never surfaced, because a runtime was never found.

Neither failed loudly. A scanned receipt imported as empty text with an
``ocr_status`` no user sees, so a firm believed a document was captured when
nothing was. These assertions are mostly about that: whatever the resolver
returns must actually be able to read an image, and when it cannot resolve
anything the application must say so.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import fitz  # noqa: E402

from core.manual_app import (  # noqa: E402
    _bundled_runtime,
    _system_tesseract,
    describe_ocr_availability,
    resolve_ocr_engine,
)
from intake.extraction import OCR_COMPLETED, extract_text  # noqa: E402

SCANNED_TEXT = (
    "THE JUDICIARY OF KENYA\n"
    "OFFICIAL PAYMENT RECEIPT\n"
    "Customer Ref: E6EWRY6F\n"
    "Amount Paid: KES 4,000.00\n"
    "Case No: HCCOMM/E214/2026\n"
)


def make_scanned_pdf(path: Path) -> None:
    """A page with no text layer -- what a scanner or phone camera produces."""
    document = fitz.open()
    page = document.new_page()
    page.insert_textbox(fitz.Rect(56, 56, 540, 400), SCANNED_TEXT, fontsize=13, fontname="helv")
    flattened = fitz.open()
    pixmap = page.get_pixmap(matrix=fitz.Matrix(200 / 72, 200 / 72), alpha=False)
    new_page = flattened.new_page(width=page.rect.width, height=page.rect.height)
    new_page.insert_image(page.rect, pixmap=pixmap)
    flattened.save(path)
    flattened.close()
    document.close()


def main() -> None:
    available, detail = describe_ocr_availability()
    print(f"OCR availability: {available} ({detail})")

    # The description must name what it found, never claim availability vaguely.
    assert detail, "availability must be described"
    if available:
        assert "Tesseract" in detail, detail
    else:
        assert "no OCR engine" in detail, detail

    with tempfile.TemporaryDirectory() as temp_dir:
        scanned = Path(temp_dir) / "receipt.pdf"
        make_scanned_pdf(scanned)

        # The page genuinely has no text layer, or the test proves nothing.
        assert not extract_text(scanned).text.strip(), (
            "the fixture must have no extractable text, or OCR is not being exercised"
        )

        engine = resolve_ocr_engine(scanned)
        if not available:
            assert engine is None, "no engine may be returned when OCR is unavailable"
            print("OCR AVAILABILITY VALIDATION PASS (no engine on this machine)")
            return

        # Whatever the resolver hands back must be usable. Returning the
        # runtime instead of its adapter was the defect that made a present
        # runtime useless.
        assert engine is not None, "an engine was promised by describe_ocr_availability"
        assert hasattr(engine, "recognize_image"), (
            f"{type(engine).__name__} has no recognize_image; the resolver returned "
            f"a runtime rather than an engine adapter"
        )

        result = extract_text(scanned, ocr_engine=engine)
        assert result.text.strip(), "a scanned page yielded no text through the resolver"
        assert result.ocr_status == OCR_COMPLETED, result.ocr_status

        recovered = " ".join(result.text.split())

        # The money figure must survive exactly. A misread amount is the one
        # error a firm cannot absorb, and it is what reconciliation turns on.
        assert "4,000.00" in recovered, f"the amount was not recovered: {recovered[:120]}"

        # Headings survive, so the document is identifiable in search.
        assert "JUDICIARY" in recovered.upper(), recovered[:120]
        assert "RECEIPT" in recovered.upper(), recovered[:120]

        # Alphanumeric references are the weak spot, and worth stating rather
        # than asserting away: a case number arrives with spacing damage
        # ("HCCOMM/E21 4/2026") and a customer reference can lose a digit to a
        # letter ("E6EWRY6F" -> "EEEWRY6F"). Match on the stable prefix, and
        # see documentation/doc-extraction-improvement.md for why this matters
        # more than the character error rate suggests.
        squashed = recovered.replace(" ", "")
        assert "HCCOMM/E21" in squashed, f"the case number was lost entirely: {recovered[:120]}"

    # Whichever source was used, it must be one of the two we support.
    if _bundled_runtime() is not None:
        print("  engine source: bundled runtime (validated against its manifest)")
    else:
        system = _system_tesseract()
        assert system is not None and system.exists(), "unmanifested fallback must exist"
        print(f"  engine source: system install at {system}")

    print("OCR AVAILABILITY VALIDATION PASS")


if __name__ == "__main__":
    main()
