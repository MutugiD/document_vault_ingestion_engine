"""Download public Kenyan legal documents listed in the repository manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "resources" / "public_kenyan_legal_docs.json"
EXTENSIONS = {
    "pdf": ".pdf",
    "docx": ".docx",
}
SIGNATURES = {
    "pdf": b"%PDF-",
    "docx": b"PK\x03\x04",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download public Kenyan legal PDFs.")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "test-output" / "public-kenyan-documents",
        help="Folder where public documents should be downloaded.",
    )
    parser.add_argument(
        "--hash-report",
        type=Path,
        default=None,
        help="Optional JSON report path. Defaults to <output>/download-manifest.json.",
    )
    args = parser.parse_args(argv)
    documents = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["documents"]
    args.output.mkdir(parents=True, exist_ok=True)
    hash_report = args.hash_report or args.output / "download-manifest.json"

    downloaded = 0
    report_items: list[dict[str, object]] = []
    for item in documents:
        expected_type = str(item.get("expected_file_type", "pdf"))
        extension = EXTENSIONS.get(expected_type)
        if extension is None:
            print(f"DOWNLOAD WARNING: skipped unsupported expected type for {item['slug']}")
            continue
        target = args.output / f"{item['slug']}{extension}"
        if target.exists() and target.stat().st_size > 0:
            payload = target.read_bytes()
            if not _payload_matches(expected_type, payload):
                print(f"DOWNLOAD WARNING: skipped invalid cached file for {item['slug']}")
                target.unlink()
                continue
            report_items.append(_report_item(item, target, payload))
            downloaded += 1
            continue
        request = urllib.request.Request(
            str(item["url"]),
            headers={"User-Agent": "DocumentVaultIngestionEngine/0.1 public-e2e"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            payload = response.read()
        if not _payload_matches(expected_type, payload):
            print(f"DOWNLOAD WARNING: skipped invalid {expected_type} response for {item['slug']}")
            continue
        expected_hash = item.get("expected_sha256")
        actual_hash = hashlib.sha256(payload).hexdigest()
        if expected_hash and expected_hash != actual_hash:
            print(f"DOWNLOAD WARNING: skipped hash mismatch for {item['slug']}")
            continue
        target.write_bytes(payload)
        report_items.append(_report_item(item, target, payload))
        downloaded += 1

    hash_report.parent.mkdir(parents=True, exist_ok=True)
    hash_report.write_text(
        json.dumps(
            {
                "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "source_manifest": str(MANIFEST_PATH.relative_to(ROOT)).replace("\\", "/"),
                "downloaded_count": downloaded,
                "documents": report_items,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print("PUBLIC KENYAN DOC DOWNLOAD PASS")
    print(f"Downloaded or found {downloaded} public documents in {args.output}")
    print(f"Hash report: {hash_report}")
    return 0 if downloaded else 1


def _payload_matches(expected_type: str, payload: bytes) -> bool:
    signature = SIGNATURES.get(expected_type)
    return bool(signature and payload.startswith(signature))


def _report_item(item: dict[str, object], target: Path, payload: bytes) -> dict[str, object]:
    return {
        "slug": item["slug"],
        "title": item["title"],
        "source": item["source"],
        "category": item.get("category", ""),
        "expected_file_type": item.get("expected_file_type", "pdf"),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
        "path": str(target),
    }


if __name__ == "__main__":
    raise SystemExit(main())
