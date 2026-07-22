"""Deterministic test seam for UI evidence without downloading production models."""

from __future__ import annotations

from pathlib import Path

from intake.docling_runtime import DoclingBlock, DoclingConversion
from intake.extraction import extract_text


class FixtureDocumentUnderstanding:
    """Test-only stand-in; production always constructs the bundled Docling adapter."""

    def convert(self, source_path: Path) -> DoclingConversion:
        native = extract_text(source_path)
        blocks = tuple(
            DoclingBlock(
                block_type="paragraph",
                text=page.text,
                page_number=page.page_number,
                bbox=None,
                provenance=page.source,
            )
            for page in native.pages
            if page.text.strip()
        )
        return DoclingConversion(
            text=native.text,
            blocks=blocks,
            tables=(),
            page_count=native.page_count,
            extractor_version="fixture-docling",
            model_version="fixture-model",
        )
