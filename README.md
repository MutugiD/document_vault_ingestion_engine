# Document Vault Ingestion Engine

Local-first Windows document vault and ingestion engine for legal-office workflows.

This repository is being built documentation-first, feature by feature, using the same discipline as the IFC Converter reference project: clear architecture docs, a project tracker, small validation scripts, and a Windows packaging path before feature work expands.

## Current Status

F0 documentation and skeleton baseline.

Implemented in this slice:

- Python package skeleton.
- Documentation pack under `documentation/`.
- Windows build guide.
- Validation scripts under `tests/`.
- `main.py --selftest` smoke entrypoint.

Not implemented yet:

- Real licensing.
- Encrypted vault storage.
- OCR and document parsing.
- Backup/restore.
- UI.
- Packaging output.

## Product Boundary

In scope:

- Signed offline license with periodic entitlement sync.
- Local encrypted document vault.
- Document intake from watched folders and manual import.
- PDF/DOCX/image validation and text extraction.
- Local OCR using bundled Tesseract.
- Matter/document/version metadata.
- SQLite FTS5 local search.
- Local encrypted backups and restore drills.
- Managed encrypted cloud backup through short-lived AWS/GCP/Azure grants.

Deferred:

- RAG.
- Embeddings.
- Vector databases.
- Local LLM.
- Wakili-Mkononi integration.
- Direct Judiciary e-filing automation.
- Hosted AI.

## Repository Layout

```text
.
  README.md
  BUILD.md
  main.py
  main.spec
  pyproject.toml
  requirements.txt
  requirements-dev.txt
  backup/
  core/
  intake/
  licensing/
  scripts/
  search/
  tests/
  tools/
  ui/
  vault/
  documentation/
```

## Local Validation

From the repo root:

```powershell
python tests\validate_docs.py
python tests\validate_skeleton.py
python main.py --selftest
```

After dependencies are installed:

```powershell
python -m pip install -r requirements-dev.txt
ruff check .
```

## Documentation

Start here:

- [documentation/README.md](documentation/README.md)
- [documentation/STATUS.md](documentation/STATUS.md)
- [documentation/13-implementation-plan.md](documentation/13-implementation-plan.md)
