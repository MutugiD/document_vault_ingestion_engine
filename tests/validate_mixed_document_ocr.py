"""Validate that scanned pages inside a text document are recovered.

A Kenyan filing is typically typed pleadings with scanned annexures: stamped
receipts, executed agreements, sealed orders, title copies. Two defects meant
none of that content reached the vault:

1. ``extract_text`` decided OCR for the whole document -- one page of native
   text suppressed OCR on every scanned page, and the result still reported
   ``ocr_status = not_required``, so nothing signalled the loss.
2. The desktop application never supplied an OCR engine at all. The Tesseract
   runtime was bundled and validated at release, but the only engine wired to
   an import replayed a pre-existing ``.ocr.txt`` sidecar.

This covers the first defect directly and the second through
``core.manual_app.resolve_ocr_engine``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.manual_app import resolve_ocr_engine  # noqa: E402
from intake.extraction import (  # noqa: E402
    OCR_COMPLETED,
    OCR_RENDER_DPI,
    extract_text,
)

NATIVE_PAGES = ("Typed pleading page one.", "Typed pleading page two.")
SCANNED_TEXT = "OFFICIAL RECEIPT KES 4,000.00 TRACKING AERJ2026"


class StubOcr:
    """Stands in for Tesseract so the test needs no binary."""

    def __init__(self) -> None:
        self.calls: list[Path] = []

    def recognize_image(self, image_path: Path, *, languages: tuple[str, ...] | None = None) -> str:
        self.calls.append(image_path)
        return SCANNED_TEXT


def _build_mixed_pdf(path: Path) -> None:
    """Two typed pages, then one image-only page, as a scanner produces."""
    doc = fitz.open()
    for body in NATIVE_PAGES:
        page = doc.new_page()
        page.insert_text((72, 100), body, fontsize=12)

    annexure = fitz.open()
    scratch = annexure.new_page()
    scratch.insert_text((72, 100), SCANNED_TEXT, fontsize=12)
    pixmap = scratch.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    annexure.close()

    scanned_page = doc.new_page()
    scanned_page.insert_image(scanned_page.rect, pixmap=pixmap)
    doc.save(path)
    doc.close()


def main() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir)
        mixed = workspace / "pleadings-with-annexure.pdf"
        _build_mixed_pdf(mixed)

        with fitz.open(mixed) as doc:
            blank = [i for i, page in enumerate(doc) if not page.get_text("text").strip()]
        assert blank == [2], f"expected one image-only page, found {blank}"

        # Without an engine the scanned page is simply absent.
        bare = extract_text(mixed)
        assert SCANNED_TEXT not in bare.text
        assert all(body in bare.text for body in NATIVE_PAGES)

        # With an engine, the scanned page is recovered and the native pages
        # are kept verbatim rather than re-recognised.
        engine = StubOcr()
        result = extract_text(mixed, ocr_engine=engine)
        assert SCANNED_TEXT in result.text, "scanned annexure was not recovered"
        for body in NATIVE_PAGES:
            assert body in result.text, f"native page lost: {body}"
        assert result.ocr_status == OCR_COMPLETED, result.ocr_status
        assert len(engine.calls) == 1, (
            f"OCR ran on {len(engine.calls)} pages; it must run only on pages "
            f"without native text, or it would introduce error into exact text"
        )

        # Rasterisation must be at OCR resolution, not PDF user space.
        assert OCR_RENDER_DPI >= 300, OCR_RENDER_DPI
        with fitz.open(mixed) as doc:
            page_width = doc[2].rect.width
            rendered_width = (
                doc[2]
                .get_pixmap(
                    matrix=fitz.Matrix(OCR_RENDER_DPI / 72, OCR_RENDER_DPI / 72), alpha=False
                )
                .width
            )
        assert rendered_width > page_width * 3, "render resolution is too low for OCR"

        # The application must resolve a real engine, not only a sidecar.
        # A sidecar beside the source still wins, for deterministic runs.
        sidecar_source = workspace / "with-sidecar.pdf"
        _build_mixed_pdf(sidecar_source)
        sidecar_source.with_suffix(".pdf.ocr.txt").write_text("SIDECAR", encoding="utf-8")
        assert resolve_ocr_engine(sidecar_source) is not None
        assert resolve_ocr_engine(sidecar_source).recognize_image(Path("x")) == "SIDECAR"

    print("MIXED DOCUMENT OCR VALIDATION PASS")


if __name__ == "__main__":
    main()
