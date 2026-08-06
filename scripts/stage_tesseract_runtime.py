"""Stage a minimal Tesseract runtime for bundling with the application.

The shipped bundle contained no OCR engine. ``main.spec`` includes
``runtime/tesseract`` only if it exists, it did not, and
``discover_tesseract_runtime()`` refuses an unsigned system install -- so a
scanned receipt silently produced no text in the packaged product.

This stages the runtime the bundle needs, from a Tesseract install or an
extracted installer, and writes the hashed manifest that discovery validates.

Minimal on purpose. A full install is ~87 MB because it ships training tools,
their HTML manual pages, and language data for a hundred scripts. OCR needs the
executable, the libraries it links, and one language file. The rest is weight
in every customer's download.

Usage:
    python scripts/stage_tesseract_runtime.py
    python scripts/stage_tesseract_runtime.py --source "C:/Program Files/Tesseract-OCR"
    python scripts/stage_tesseract_runtime.py --languages eng swa
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET = ROOT / "runtime" / "tesseract"
MANIFEST_NAME = "tesseract-runtime.json"

DEFAULT_SOURCES = (
    Path("C:/Program Files/Tesseract-OCR"),
    Path("C:/Program Files (x86)/Tesseract-OCR"),
    ROOT / "test-output" / "tesseract-runtime-local-20260722" / "stage",
    ROOT / "test-output" / "tesseract-installer-validation" / "extracted",
)

# Everything OCR needs, and nothing else. Training utilities, their manual
# pages and the installer's own scratch directory are all excluded.
EXCLUDED_EXECUTABLES = {
    "ambiguous_words.exe",
    "classifier_tester.exe",
    "cntraining.exe",
    "combine_lang_model.exe",
    "combine_tessdata.exe",
    "dawg2wordlist.exe",
    "lstmeval.exe",
    "lstmtraining.exe",
    "merge_unicharsets.exe",
    "mftraining.exe",
    "set_unicharset_properties.exe",
    "shapeclustering.exe",
    "text2image.exe",
    "unicharset_extractor.exe",
    "wordlist2dawg.exe",
}


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def find_source(explicit: Path | None) -> Path:
    candidates = [explicit] if explicit else list(DEFAULT_SOURCES)
    for candidate in candidates:
        if candidate and (candidate / "tesseract.exe").exists():
            return candidate
    raise SystemExit(
        "no Tesseract install found. Pass --source, or install Tesseract from\n"
        "https://github.com/UB-Mannheim/tesseract/wiki"
    )


def detect_version(source: Path) -> str:
    try:
        result = subprocess.run(
            [str(source / "tesseract.exe"), "--version"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    first = (result.stdout or result.stderr).splitlines()[0]
    return first.replace("tesseract", "").strip() or "unknown"


def stage(source: Path, target: Path, languages: tuple[str, ...]) -> dict:
    if target.exists():
        shutil.rmtree(target)
    (target / "tessdata").mkdir(parents=True)

    copied: list[Path] = []

    executable = source / "tesseract.exe"
    shutil.copy2(executable, target / "tesseract.exe")
    copied.append(target / "tesseract.exe")

    # The DLLs tesseract.exe links against sit beside it.
    for dll in sorted(source.glob("*.dll")):
        shutil.copy2(dll, target / dll.name)
        copied.append(target / dll.name)

    missing: list[str] = []
    for language in languages:
        trained = source / "tessdata" / f"{language}.traineddata"
        if not trained.exists():
            missing.append(language)
            continue
        shutil.copy2(trained, target / "tessdata" / trained.name)
        copied.append(target / "tessdata" / trained.name)
    if missing:
        raise SystemExit(f"language data not found in {source / 'tessdata'}: {', '.join(missing)}")

    # Orientation and script detection, used when a scan is rotated.
    osd = source / "tessdata" / "osd.traineddata"
    if osd.exists():
        shutil.copy2(osd, target / "tessdata" / osd.name)
        copied.append(target / "tessdata" / osd.name)

    manifest = {
        "provider": "tesseract",
        "version": detect_version(source),
        "platform": "windows-x64",
        "executable": "tesseract.exe",
        "languages": list(languages),
        "files": [
            {
                "relative_path": path.relative_to(target).as_posix(),
                "sha256": sha256_of(path),
                "size_bytes": path.stat().st_size,
            }
            for path in sorted(copied)
        ],
    }
    (target / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=None)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--languages", nargs="+", default=["eng"])
    args = parser.parse_args(argv)

    source = find_source(args.source)
    print(f"source : {source}")
    manifest = stage(source, args.target, tuple(args.languages))

    total = sum(item["size_bytes"] for item in manifest["files"])
    print(f"target : {args.target}")
    print(f"version: {manifest['version']}")
    print(f"files  : {len(manifest['files'])} ({total / 1_048_576:.1f} MiB)")
    print(f"langs  : {', '.join(manifest['languages'])}")

    # Prove the staged runtime is usable before anyone ships it.
    sys.path.insert(0, str(ROOT))
    from intake.ocr_runtime import discover_tesseract_runtime

    runtime = discover_tesseract_runtime(search_roots=(args.target,))
    if runtime is None:
        raise SystemExit("staged runtime was not accepted by discovery")
    print("verified: discovery accepts the staged runtime")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
