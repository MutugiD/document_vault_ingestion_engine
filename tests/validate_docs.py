"""Validate the documentation pack exists and cross-links important files."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_DOCS = [
    "documentation/README.md",
    "documentation/STATUS.md",
    "documentation/FINDINGS-SUMMARY.md",
    "documentation/00-system-overview.md",
    "documentation/01-architecture-e2e.md",
    "documentation/02-defects-and-remedies.md",
    "documentation/03-local-storage-vault.md",
    "documentation/04-document-intake-validation.md",
    "documentation/05-text-extraction-ocr.md",
    "documentation/06-matter-document-versioning.md",
    "documentation/07-search-indexing.md",
    "documentation/08-licensing-security.md",
    "documentation/09-backup-restore-cloud.md",
    "documentation/10-ui-threading-workflows.md",
    "documentation/11-packaging-distribution.md",
    "documentation/12-error-handling-reporting.md",
    "documentation/13-implementation-plan.md",
    "documentation/14-three-products-rag-strategy.md",
    "documentation/15-end-to-end-verification.md",
    "documentation/16-end-to-end-testing-guide.md",
]


def main() -> int:
    missing = [path for path in REQUIRED_DOCS if not (ROOT / path).exists()]
    if missing:
        print("DOC VALIDATION FAIL")
        for path in missing:
            print(f"- missing {path}")
        return 1

    readme = (ROOT / "documentation/README.md").read_text(encoding="utf-8")
    for path in REQUIRED_DOCS[1:]:
        doc_name = Path(path).name
        if doc_name not in readme:
            print("DOC VALIDATION FAIL")
            print(f"- documentation/README.md does not reference {doc_name}")
            return 1

    print("DOC VALIDATION PASS")
    print(f"Checked {len(REQUIRED_DOCS)} documentation files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
