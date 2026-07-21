"""Prepare the pinned offline Docling and Tesseract runtime for Windows builds."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME = ROOT / "runtime"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--tesseract-archive", type=Path)
    parser.add_argument("--tesseract-url")
    parser.add_argument("--tesseract-sha256")
    parser.add_argument("--tesseract-version", required=True)
    parser.add_argument("--language", action="append", default=["eng"])
    args = parser.parse_args()

    runtime_root = args.runtime_root.resolve()
    docling_root = runtime_root / "docling"
    tesseract_root = runtime_root / "tesseract"
    docling_models = docling_root / "models"
    docling_models.mkdir(parents=True, exist_ok=True)
    tesseract_root.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            "docling-tools",
            "models",
            "download",
            "layout",
            "tableformer",
            "--output-dir",
            str(docling_models),
            "--quiet",
        ],
        check=True,
    )
    _write_notice(docling_root, "Docling CPU runtime", "2.41.0", "https://github.com/docling-project/docling")
    _write_manifest(
        docling_root,
        "docling",
        "2.41.0",
        docling_root.rglob("*"),
        source_url="https://github.com/docling-project/docling",
    )

    archive = args.tesseract_archive
    with tempfile.TemporaryDirectory(prefix="document-runtime-") as temporary_dir:
        if archive is None:
            if not args.tesseract_url or not args.tesseract_sha256:
                raise SystemExit(
                    "Tesseract requires --tesseract-archive or pinned "
                    "--tesseract-url and --tesseract-sha256"
                )
            archive = Path(temporary_dir) / "tesseract-runtime.zip"
            urllib.request.urlretrieve(args.tesseract_url, archive)
        if args.tesseract_sha256 and _sha256(archive) != args.tesseract_sha256.lower():
            raise SystemExit("Tesseract archive SHA-256 mismatch")
        _extract_tesseract(archive, tesseract_root, tuple(dict.fromkeys(args.language)))
    _write_notice(
        tesseract_root,
        "Tesseract OCR runtime",
        args.tesseract_version,
        args.tesseract_url or "local archive",
    )
    _write_manifest(
        tesseract_root,
        "tesseract",
        args.tesseract_version,
        tesseract_root.rglob("*"),
        source_url=args.tesseract_url or "local archive",
        languages=tuple(dict.fromkeys(args.language)),
    )
    print(f"DOCUMENT RUNTIME READY: {runtime_root}")
    return 0


def _extract_tesseract(archive: Path, target: Path, languages: tuple[str, ...]) -> None:
    if archive.suffix.lower() != ".zip":
        raise SystemExit("Tesseract asset must be a portable ZIP, not an installer")
    with zipfile.ZipFile(archive) as source:
        for member in source.infolist():
            destination = (target / member.filename).resolve()
            if not destination.is_relative_to(target.resolve()):
                raise SystemExit(f"Tesseract archive path escapes target: {member.filename}")
            source.extract(member, target)
    executables = list(target.rglob("tesseract.exe"))
    if len(executables) != 1:
        raise SystemExit("Tesseract bundle must contain exactly one tesseract.exe")
    executable = executables[0]
    for child in target.iterdir():
        if child != executable.parent:
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    for child in executable.parent.iterdir():
        if child != executable:
            destination = target / child.name
            if destination.exists():
                shutil.rmtree(destination) if destination.is_dir() else destination.unlink()
            shutil.move(str(child), destination)
    shutil.move(str(executable), str(target / "tesseract.exe"))
    tessdata = target / "tessdata"
    for language in languages:
        if not (tessdata / f"{language}.traineddata").exists():
            raise SystemExit(f"missing tessdata/{language}.traineddata")


def _write_manifest(
    root: Path,
    provider: str,
    version: str,
    paths: object,
    *,
    source_url: str,
    languages: tuple[str, ...] = (),
) -> None:
    entries = []
    for path in sorted(path for path in paths if isinstance(path, Path) and path.is_file()):
        relative = path.relative_to(root).as_posix()
        entries.append(
            {
                "relative_path": relative,
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    if not entries:
        raise SystemExit(f"no {provider} runtime files were prepared")
    payload = {
        "manifest_format_version": 1,
        "provider": provider,
        "version": version,
        "platform": "windows-x64",
        "source_url": source_url,
        "license": "See THIRD-PARTY-NOTICES.txt",
        "files": entries,
    }
    if provider == "tesseract":
        payload.update(
            {
                "executable": "tesseract.exe",
                "languages": list(languages),
            }
        )
    (root / f"{provider}-runtime.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )


def _write_notice(root: Path, name: str, version: str, source_url: str) -> None:
    (root / "THIRD-PARTY-NOTICES.txt").write_text(
        f"{name}\nVersion: {version}\nSource: {source_url}\n"
        "The complete license text is supplied by the approved build asset source.\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
