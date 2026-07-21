"""Tesseract runtime bundle validation for local OCR packaging."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

TESSERACT_MANIFEST_NAME = "tesseract-runtime.json"
DEFAULT_OCR_TIMEOUT_SECONDS = 120


class OcrRuntimeError(Exception):
    """Raised when the local OCR runtime bundle is missing or malformed."""


@dataclass(frozen=True)
class OcrRuntimeFile:
    relative_path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class TesseractRuntimeManifest:
    manifest_format_version: int
    provider: str
    version: str
    platform: str
    executable: str
    languages: tuple[str, ...]
    files: tuple[OcrRuntimeFile, ...]


@dataclass(frozen=True)
class TesseractRuntime:
    root: Path
    executable: Path
    languages: tuple[str, ...]
    version: str


@dataclass(frozen=True)
class OcrRecognition:
    text: str
    confidence: float | None
    language: str
    engine_version: str
    duration_ms: int
    page_confidence: tuple[tuple[int, float], ...] = ()


class TesseractOcrEngine:
    """Subprocess-backed OCR adapter for a validated Tesseract runtime."""

    def __init__(
        self,
        runtime: TesseractRuntime,
        *,
        timeout_seconds: int = DEFAULT_OCR_TIMEOUT_SECONDS,
        preprocess: bool = True,
        page_segmentation_mode: int = 6,
    ) -> None:
        self.runtime = runtime
        self.timeout_seconds = timeout_seconds
        self.preprocess = preprocess
        self.page_segmentation_mode = page_segmentation_mode

    def recognize_image(
        self,
        image_path: Path,
        *,
        languages: tuple[str, ...] | None = None,
    ) -> str:
        return self.recognize_image_with_metadata(image_path, languages=languages).text

    def recognize_image_with_metadata(
        self,
        image_path: Path,
        *,
        languages: tuple[str, ...] | None = None,
    ) -> OcrRecognition:
        language_arg = "+".join(languages or self.runtime.languages)
        environment = os.environ.copy()
        environment["TESSDATA_PREFIX"] = str(self.runtime.root / "tessdata")
        started = time.perf_counter()
        working_image = _preprocess_image(image_path) if self.preprocess else image_path
        command = [
            str(self.runtime.executable),
            str(working_image),
            "stdout",
            "tsv",
            "-l",
            language_arg,
            "--psm",
            str(self.page_segmentation_mode),
        ]
        try:
            process = subprocess.Popen(
                command,
                cwd=self.runtime.root,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=False,
            )
            try:
                stdout, stderr = process.communicate(timeout=self.timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                process.kill()
                process.communicate()
                raise OcrRuntimeError("Tesseract OCR timed out") from exc
            if process.returncode != 0:
                raise OcrRuntimeError(stderr.strip() or "Tesseract OCR failed")
            text, confidence, page_confidence = _parse_tsv(stdout)
        finally:
            if working_image != image_path:
                working_image.unlink(missing_ok=True)
        return OcrRecognition(
            text=text,
            confidence=confidence,
            language=language_arg,
            engine_version=self.runtime.version,
            duration_ms=int((time.perf_counter() - started) * 1000),
            page_confidence=page_confidence,
        )


def discover_tesseract_runtime(
    search_roots: tuple[Path, ...] | None = None,
) -> TesseractRuntime | None:
    """Find and validate a Tesseract runtime from configured local bundle locations."""

    candidates: list[Path] = []
    configured_root = os.environ.get("DOCUMENT_VAULT_TESSERACT_ROOT")
    if configured_root:
        candidates.append(Path(configured_root))
    if search_roots:
        candidates.extend(search_roots)
    bundled_root = getattr(sys, "_MEIPASS", None)
    if bundled_root:
        candidates.append(Path(str(bundled_root)) / "tesseract")
    candidates.append(Path(__file__).resolve().parents[1] / "runtime" / "tesseract")

    for root in candidates:
        manifest_path = root / TESSERACT_MANIFEST_NAME
        if manifest_path.exists():
            return validate_tesseract_runtime(root, manifest_path)
    return None


def load_tesseract_manifest(manifest_path: Path) -> TesseractRuntimeManifest:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    return TesseractRuntimeManifest(
        manifest_format_version=int(payload.get("manifest_format_version", 0)),
        provider=str(payload["provider"]),
        version=str(payload["version"]),
        platform=str(payload["platform"]),
        executable=str(payload["executable"]),
        languages=tuple(str(item) for item in payload["languages"]),
        files=tuple(
            OcrRuntimeFile(
                relative_path=str(item["relative_path"]),
                sha256=str(item["sha256"]),
                size_bytes=int(item["size_bytes"]),
            )
            for item in payload["files"]
        ),
    )


def validate_tesseract_runtime(bundle_root: Path, manifest_path: Path) -> TesseractRuntime:
    manifest = load_tesseract_manifest(manifest_path)
    if manifest.provider != "tesseract":
        raise OcrRuntimeError(f"unsupported OCR provider: {manifest.provider}")
    if manifest.platform != "windows-x64":
        raise OcrRuntimeError(f"unsupported OCR platform: {manifest.platform}")
    if not manifest.languages:
        raise OcrRuntimeError("OCR runtime manifest must list at least one language")
    if manifest.manifest_format_version != 1:
        raise OcrRuntimeError("unsupported OCR runtime manifest format")

    bundle_root = bundle_root.resolve()
    executable = _resolve_bundle_path(bundle_root, manifest.executable)
    if executable.name.lower() != "tesseract.exe":
        raise OcrRuntimeError("OCR executable must be tesseract.exe on Windows")
    if not executable.exists():
        raise OcrRuntimeError(f"missing OCR executable: {executable}")

    required_paths = {
        manifest.executable,
        *(f"tessdata/{language}.traineddata" for language in manifest.languages),
    }
    manifest_paths = {item.relative_path for item in manifest.files}
    if len(manifest_paths) != len(manifest.files):
        raise OcrRuntimeError("duplicate OCR runtime paths")
    missing_declared_paths = required_paths - manifest_paths
    if missing_declared_paths:
        raise OcrRuntimeError(f"OCR manifest is missing required files: {missing_declared_paths}")

    for file_entry in manifest.files:
        path = _resolve_bundle_path(bundle_root, file_entry.relative_path)
        if not path.exists():
            raise OcrRuntimeError(f"missing OCR runtime file: {path}")
        if path.stat().st_size != file_entry.size_bytes:
            raise OcrRuntimeError(f"OCR runtime size mismatch: {file_entry.relative_path}")
        if _sha256_file(path) != file_entry.sha256:
            raise OcrRuntimeError(f"OCR runtime hash mismatch: {file_entry.relative_path}")

    return TesseractRuntime(
        root=bundle_root,
        executable=executable,
        languages=manifest.languages,
        version=manifest.version,
    )


def create_tesseract_manifest(
    bundle_root: Path,
    version: str,
    languages: tuple[str, ...],
) -> dict[str, object]:
    """Create a manifest payload for a prepared Tesseract runtime folder."""

    if not languages:
        raise OcrRuntimeError("at least one OCR language is required")
    bundle_root = bundle_root.resolve()
    relative_paths = [
        "tesseract.exe",
        *(f"tessdata/{language}.traineddata" for language in languages),
    ]
    files = []
    for relative_path in relative_paths:
        path = _resolve_bundle_path(bundle_root, relative_path)
        if not path.exists():
            raise OcrRuntimeError(f"missing OCR runtime file: {path}")
        files.append(
            {
                "relative_path": relative_path,
                "sha256": _sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )
    return {
        "manifest_format_version": 1,
        "provider": "tesseract",
        "version": version,
        "platform": "windows-x64",
        "executable": "tesseract.exe",
        "languages": list(languages),
        "files": files,
    }


def _resolve_bundle_path(bundle_root: Path, relative_path: str) -> Path:
    if Path(relative_path).is_absolute():
        raise OcrRuntimeError(f"OCR runtime path must be relative: {relative_path}")
    resolved = (bundle_root / relative_path).resolve()
    if not resolved.is_relative_to(bundle_root):
        raise OcrRuntimeError(f"OCR runtime path escapes bundle root: {relative_path}")
    return resolved


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_tsv(tsv: str) -> tuple[str, float | None, tuple[tuple[int, float], ...]]:
    lines = tsv.splitlines()
    if not lines:
        return "", None, ()
    header = lines[0].split("\t")
    indexes = {name: index for index, name in enumerate(header)}
    required = {"page_num", "conf", "text"}
    if not required.issubset(indexes):
        raise OcrRuntimeError("Tesseract TSV output is missing required columns")
    words: list[str] = []
    confidences: list[float] = []
    pages: dict[int, list[float]] = {}
    for line in lines[1:]:
        fields = line.split("\t")
        if len(fields) <= max(indexes.values()):
            continue
        word = fields[indexes["text"]].strip()
        try:
            confidence = float(fields[indexes["conf"]])
            page = int(fields[indexes["page_num"]])
        except ValueError:
            continue
        if confidence < 0:
            continue
        confidences.append(confidence)
        pages.setdefault(page, []).append(confidence)
        if word:
            words.append(word)
    aggregate = sum(confidences) / len(confidences) / 100 if confidences else None
    page_confidence = tuple(
        (page, sum(values) / len(values) / 100) for page, values in sorted(pages.items())
    )
    return " ".join(words), aggregate, page_confidence


def _preprocess_image(image_path: Path) -> Path:
    """Create an isolated grayscale/contrast derivative for OCR only."""

    try:
        from PIL import Image, ImageFilter, ImageOps

        image = Image.open(image_path).convert("L")
        image = ImageOps.autocontrast(image).filter(ImageFilter.MedianFilter(size=3))
        temporary = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        temporary_path = Path(temporary.name)
        temporary.close()
        image.save(temporary_path, format="PNG")
        return temporary_path
    except Exception as exc:
        raise OcrRuntimeError(f"OCR preprocessing failed: {image_path.name}") from exc
