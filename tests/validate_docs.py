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
    "documentation/17-windows-distribution-release-checklist.md",
    "documentation/18-installer-code-signing-publishing.md",
    "documentation/19-automatic-update-channel.md",
    "documentation/20-manual-windows-app-e2e-handover.md",
    "documentation/21-admin-license-payment-boundary.md",
    "documentation/22-managed-cloud-backup-boundary.md",
    "documentation/23-wakili-mkononi-integration-boundary.md",
    "documentation/24-hosted-ai-llm-boundary.md",
    "documentation/enterprise/README.md",
    "documentation/enterprise/architecture.md",
    "documentation/enterprise/product-roadmap.md",
    "documentation/enterprise/ci-cd-release.md",
    "documentation/enterprise/security-compliance.md",
    "documentation/enterprise/windows-distribution.md",
    "documentation/enterprise/e2e-validation-plan.md",
    "documentation/enterprise/commercial-operations.md",
    "documentation/products/README.md",
    "documentation/products/windows-legal-document-vault/architecture.md",
    "documentation/products/windows-legal-document-vault/features-breakdown.md",
    "documentation/products/windows-legal-document-vault/gap-analysis.md",
    "documentation/products/windows-legal-document-vault/implementation.md",
    "documentation/products/document-intake-engine/architecture.md",
    "documentation/products/document-intake-engine/features-breakdown.md",
    "documentation/products/document-intake-engine/gap-analysis.md",
    "documentation/products/document-intake-engine/implementation.md",
    "documentation/products/local-matter-rag-connector/architecture.md",
    "documentation/products/local-matter-rag-connector/features-breakdown.md",
    "documentation/products/local-matter-rag-connector/gap-analysis.md",
    "documentation/products/local-matter-rag-connector/implementation.md",
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
