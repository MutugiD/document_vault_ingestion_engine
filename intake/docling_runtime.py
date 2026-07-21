"""Mandatory local Docling conversion and structured-artifact boundary."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class DoclingRuntimeError(Exception):
    """Raised when the bundled Docling runtime or conversion fails."""


@dataclass(frozen=True)
class DoclingBlock:
    block_type: str
    text: str
    page_number: int | None
    bbox: tuple[float, float, float, float] | None
    provenance: str
    confidence: float | None = None


@dataclass(frozen=True)
class DoclingTable:
    page_number: int | None
    rows: tuple[tuple[str, ...], ...]
    provenance: str


@dataclass(frozen=True)
class DoclingConversion:
    text: str
    blocks: tuple[DoclingBlock, ...]
    tables: tuple[DoclingTable, ...]
    page_count: int
    extractor_version: str
    model_version: str
    warnings: tuple[str, ...] = ()


class DocumentUnderstanding(Protocol):
    def convert(self, source_path: Path) -> DoclingConversion:
        """Convert a source document into structured local artifacts."""


class DoclingDocumentUnderstanding:
    """Adapter around the bundled Docling converter.

    Imports are deliberately lazy so the existing intake shell can report a
    controlled runtime failure instead of crashing during module discovery.
    """

    def __init__(self, *, artifacts_path: Path | None = None) -> None:
        self.artifacts_path = (artifacts_path or _configured_artifacts_path()).resolve()
        if importlib.util.find_spec("docling") is None:
            raise DoclingRuntimeError("Docling package is not installed")
        self._converter: Any | None = None

    def convert(self, source_path: Path) -> DoclingConversion:
        try:
            converter = self._get_converter()
            result = converter.convert(source_path, raises_on_error=True)
            document = result.document
            blocks: list[DoclingBlock] = []
            tables: list[DoclingTable] = []
            for item, _level in document.iterate_items(with_groups=False):
                block = _block_from_item(item)
                if block is not None:
                    blocks.append(block)
                if item.__class__.__name__ == "TableItem":
                    tables.append(_table_from_item(item, document))
            text = document.export_to_markdown()
            page_count = max(
                (block.page_number or 0 for block in blocks),
                default=getattr(document, "pages", {}).__len__(),
            )
            return DoclingConversion(
                text=text.strip(),
                blocks=tuple(blocks),
                tables=tuple(tables),
                page_count=page_count,
                extractor_version=_package_version("docling"),
                model_version=_manifest_version(self.artifacts_path),
            )
        except DoclingRuntimeError:
            raise
        except Exception as exc:
            raise DoclingRuntimeError(f"Docling conversion failed: {source_path.name}") from exc

    def _get_converter(self) -> Any:
        if self._converter is None:
            from docling.document_converter import DocumentConverter

            self._converter = DocumentConverter()
        return self._converter


def validate_docling_runtime(bundle_root: Path) -> dict[str, object]:
    """Validate the packaged Docling manifest and model containment."""

    if importlib.util.find_spec("docling") is None:
        raise DoclingRuntimeError("Docling package is not installed")
    bundle_root = bundle_root.resolve()
    manifest_path = bundle_root / "docling-runtime.json"
    if not manifest_path.exists():
        raise DoclingRuntimeError(f"missing Docling runtime manifest: {manifest_path}")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("provider") != "docling":
        raise DoclingRuntimeError("unsupported Docling runtime provider")
    files = payload.get("files")
    if not isinstance(files, list) or not files:
        raise DoclingRuntimeError("Docling manifest must list model files")
    verified = 0
    for entry in files:
        relative = str(entry["relative_path"])
        path = (bundle_root / relative).resolve()
        if Path(relative).is_absolute() or not path.is_relative_to(bundle_root):
            raise DoclingRuntimeError(f"Docling runtime path escapes bundle root: {relative}")
        if not path.is_file():
            raise DoclingRuntimeError(f"missing Docling runtime file: {relative}")
        if path.stat().st_size != int(entry["size_bytes"]):
            raise DoclingRuntimeError(f"Docling runtime size mismatch: {relative}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != str(entry["sha256"]):
            raise DoclingRuntimeError(f"Docling runtime hash mismatch: {relative}")
        verified += 1
    return {"provider": "docling", "version": str(payload["version"]), "files_verified": verified}


def _block_from_item(item: Any) -> DoclingBlock | None:
    text = str(getattr(item, "text", "") or "").strip()
    label = str(getattr(item, "label", item.__class__.__name__)).split(".")[-1].lower()
    prov = getattr(item, "prov", None) or []
    first = prov[0] if prov else None
    page_number = getattr(first, "page_no", None)
    bbox_value = getattr(first, "bbox", None)
    bbox = None
    if bbox_value is not None:
        bbox = tuple(float(value) for value in bbox_value.as_tuple())
    if not text and label not in {"picture", "chart", "table"}:
        return None
    return DoclingBlock(label, text, page_number, bbox, str(getattr(item, "self_ref", "")))


def _table_from_item(item: Any, document: Any) -> DoclingTable:
    rows: list[tuple[str, ...]] = []
    data = getattr(item, "data", None)
    grid = getattr(data, "grid", None) if data is not None else None
    if grid:
        for row in grid:
            rows.append(tuple(str(getattr(cell, "text", cell)) for cell in row))
    prov = getattr(item, "prov", None) or []
    page_number = getattr(prov[0], "page_no", None) if prov else None
    return DoclingTable(page_number, tuple(rows), str(getattr(item, "self_ref", document)))


def _configured_artifacts_path() -> Path:
    configured = os.environ.get("DOCUMENT_VAULT_DOCLING_ARTIFACTS")
    if configured:
        return Path(configured)
    bundled_root = getattr(__import__("sys"), "_MEIPASS", None)
    if bundled_root:
        return Path(str(bundled_root)) / "runtime" / "docling" / "models"
    return Path(__file__).resolve().parents[1] / "runtime" / "docling" / "models"


def _manifest_version(artifacts_path: Path) -> str:
    manifest = artifacts_path.parent / "docling-runtime.json"
    if manifest.exists():
        return str(json.loads(manifest.read_text(encoding="utf-8")).get("version", "unknown"))
    return "unknown"


def _package_version(package_name: str) -> str:
    try:
        from importlib.metadata import version

        return version(package_name)
    except Exception:
        return "unknown"
