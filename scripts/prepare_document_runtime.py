"""Prepare the pinned offline Docling and Tesseract runtime for Windows builds."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME = ROOT / "runtime"
TESSERACT_LOCK = ROOT / "resources" / "tesseract-runtime.lock.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--tesseract-archive", type=Path)
    parser.add_argument("--tesseract-url")
    parser.add_argument("--tesseract-sha256")
    parser.add_argument("--tesseract-version")
    parser.add_argument("--language", action="append", default=["eng"])
    args = parser.parse_args()

    lock = _load_tesseract_lock()
    tesseract_url = args.tesseract_url or str(lock["archive_url"])
    tesseract_sha256 = args.tesseract_sha256 or str(lock["archive_sha256"])
    tesseract_version = args.tesseract_version or str(lock["version"])

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
    _write_notice(
        docling_root, "Docling CPU runtime", "2.41.0", "https://github.com/docling-project/docling"
    )
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
            archive = Path(temporary_dir) / Path(tesseract_url).name
            urllib.request.urlretrieve(tesseract_url, archive)
        if _sha256(archive) != tesseract_sha256.lower():
            raise SystemExit("Tesseract archive SHA-256 mismatch")
        _extract_tesseract(archive, tesseract_root)
        _stage_tesseract_languages(
            tesseract_root,
            tuple(dict.fromkeys(args.language)),
            lock,
        )
    _write_notice(
        tesseract_root,
        "Tesseract OCR runtime",
        tesseract_version,
        tesseract_url if args.tesseract_archive is None else "local archive",
    )
    _write_manifest(
        tesseract_root,
        "tesseract",
        tesseract_version,
        tesseract_root.rglob("*"),
        source_url=tesseract_url if args.tesseract_archive is None else "local archive",
        languages=tuple(dict.fromkeys(args.language)),
    )
    print(f"DOCUMENT RUNTIME READY: {runtime_root}")
    return 0


def _extract_tesseract(archive: Path, target: Path) -> None:
    if archive.suffix.lower() == ".zip":
        with zipfile.ZipFile(archive) as source:
            for member in source.infolist():
                destination = (target / member.filename).resolve()
                if not destination.is_relative_to(target.resolve()):
                    raise SystemExit(f"Tesseract archive path escapes target: {member.filename}")
                source.extract(member, target)
    elif archive.suffix.lower() == ".exe" and sys.platform == "win32":
        _extract_nsis_tesseract_installer(archive, target)
    else:
        raise SystemExit("Tesseract asset must be a ZIP or Windows NSIS installer")
    executables = list(target.rglob("tesseract.exe"))
    if len(executables) != 1:
        raise SystemExit("Tesseract bundle must contain exactly one tesseract.exe")
    executable = executables[0]
    if executable.parent != target:
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
    if not (target / "tesseract.exe").is_file():
        raise SystemExit("Tesseract bundle did not produce tesseract.exe")


def _extract_nsis_tesseract_installer(installer: Path, target: Path) -> None:
    extractor = _seven_zip_executable()
    subprocess.run([str(extractor), "x", str(installer), f"-o{target}", "-y"], check=True)


def _stage_tesseract_languages(
    target: Path,
    languages: tuple[str, ...],
    lock: dict[str, object],
) -> None:
    entries = lock["languages"]
    if not isinstance(entries, list):
        raise SystemExit("Tesseract runtime lock languages must be a list")
    by_code = {str(entry["code"]): entry for entry in entries if isinstance(entry, dict)}
    tessdata = target / "tessdata"
    tessdata.mkdir(parents=True, exist_ok=True)
    for language in languages:
        entry = by_code.get(language)
        if entry is None:
            raise SystemExit(f"Tesseract runtime lock does not pin language: {language}")
        destination = tessdata / f"{language}.traineddata"
        urllib.request.urlretrieve(str(entry["source_url"]), destination)
        if _sha256(destination) != str(entry["sha256"]):
            destination.unlink(missing_ok=True)
            raise SystemExit(f"Tesseract language SHA-256 mismatch: {language}")


def _seven_zip_executable() -> Path:
    discovered = shutil.which("7z") or shutil.which("7z.exe")
    if discovered:
        return Path(discovered)
    program_files = Path(r"C:\\Program Files") / "7-Zip" / "7z.exe"
    if program_files.is_file():
        return program_files
    raise SystemExit("pinned 7-Zip build tool is required to extract Tesseract")


def _load_tesseract_lock() -> dict[str, object]:
    payload = json.loads(TESSERACT_LOCK.read_text(encoding="utf-8"))
    required = {
        "archive_url",
        "archive_sha256",
        "asset_type",
        "format_version",
        "platform",
        "version",
    }
    if set(payload) != required | {"license", "languages"}:
        raise SystemExit("unexpected Tesseract runtime lock fields")
    if payload["format_version"] != 1 or payload["platform"] != "windows-x64":
        raise SystemExit("unsupported Tesseract runtime lock")
    if payload["asset_type"] != "nsis-installer":
        raise SystemExit("unsupported Tesseract runtime asset type")
    digest = str(payload["archive_sha256"])
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise SystemExit("invalid Tesseract runtime lock SHA-256")
    language_entries = payload["languages"]
    if not isinstance(language_entries, list) or not language_entries:
        raise SystemExit("Tesseract runtime lock must pin language assets")
    for entry in language_entries:
        if not isinstance(entry, dict) or set(entry) != {"code", "sha256", "source_url"}:
            raise SystemExit("invalid Tesseract language lock entry")
    return payload


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
