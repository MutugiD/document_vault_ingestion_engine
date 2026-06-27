# Product Documentation

This folder tracks the three commercial products delivered from Document Vault Ingestion Engine.

## Products

| Product | Architecture | Features | Gaps | Implementation |
| --- | --- | --- | --- | --- |
| Windows Legal Document Vault | [architecture](windows-legal-document-vault/architecture.md) | [features](windows-legal-document-vault/features-breakdown.md) | [gaps](windows-legal-document-vault/gap-analysis.md) | [implementation](windows-legal-document-vault/implementation.md) |
| Document Intake Engine | [architecture](document-intake-engine/architecture.md) | [features](document-intake-engine/features-breakdown.md) | [gaps](document-intake-engine/gap-analysis.md) | [implementation](document-intake-engine/implementation.md) |
| Local Matter RAG Connector | [architecture](local-matter-rag-connector/architecture.md) | [features](local-matter-rag-connector/features-breakdown.md) | [gaps](local-matter-rag-connector/gap-analysis.md) | [implementation](local-matter-rag-connector/implementation.md) |

## Commercial Completion Rule

No product is considered commercially complete until its architecture, features, gap analysis, implementation plan, validator list, Windows packaging path, PyInstaller bundle rules, release ZIP validation, portable install validation, and clean-machine distribution checklist are current.

## PR Rule

Every implementation PR after F19 must update the affected product `gap-analysis.md` and `implementation.md`.
