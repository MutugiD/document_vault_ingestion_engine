"""Tesseract runtime bundle validation for local OCR packaging."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


class OcrRuntimeError(Exception):
    """Raised when the local OCR runtime bundle is missing or malformed."""


@dataclass(frozen=True)
class OcrRuntimeFile:
    relative_path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class TesseractRuntimeManifest:
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


def load_tesseract_manifest(manifest_path: Path) -> TesseractRuntimeManifest:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    return TesseractRuntimeManifest(
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
