"""Download public Kenyan legal documents listed in the repository manifest."""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "resources" / "public_kenyan_legal_docs.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download public Kenyan legal PDFs.")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "test-output" / "public-kenyan-documents",
        help="Folder where public documents should be downloaded.",
    )
    args = parser.parse_args(argv)
    documents = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["documents"]
    args.output.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    for item in documents:
        target = args.output / f"{item['slug']}.pdf"
        if target.exists() and target.stat().st_size > 0:
            downloaded += 1
            continue
        request = urllib.request.Request(
            str(item["url"]),
            headers={"User-Agent": "DocumentVaultIngestionEngine/0.1 public-e2e"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            payload = response.read()
        if not payload.startswith(b"%PDF-"):
            print(f"DOWNLOAD WARNING: skipped non-PDF response for {item['slug']}")
            continue
        target.write_bytes(payload)
        downloaded += 1

    print("PUBLIC KENYAN DOC DOWNLOAD PASS")
    print(f"Downloaded or found {downloaded} public documents in {args.output}")
    return 0 if downloaded else 1


if __name__ == "__main__":
    raise SystemExit(main())
