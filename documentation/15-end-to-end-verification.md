# 15 - End To End Verification

## Purpose

Prove the three published products work together as one licensed local-first system:

1. Windows Legal Document Vault.
2. Document Intake Engine.
3. Local Matter RAG Connector.

## F11 Implementation Boundary

`tests/validate_e2e.py` validates the integrated workflow:

1. Create a stable installation ID.
2. Validate an offline signed license with:
   - `document_intake`
   - `cloud_backup`
   - `managed_restore`
   - `matter_rag`
3. Initialize an encrypted vault.
4. Generate a local PDF fixture.
5. Import the PDF through quarantine.
6. Extract PDF text.
7. Store the original PDF bytes as an encrypted vault object.
8. Create matter and document metadata.
9. Add a filed document version.
10. Search extracted text within the matter.
11. Build a Local Matter RAG index.
12. Produce a cited RAG answer packet.
13. Create an encrypted local backup package.
14. Validate managed cloud upload metadata through the safe boundary.
15. Restore the backup into a clean restore workspace.
16. Reopen the restored vault and read the encrypted object with the recovery key.

## Licensing Assertions

The validator proves that the local product flow requires an active signed license for paid feature flags. It also preserves the existing security rule:

- Disabled or expired paid features must not delete or lock away local legal documents.

## Privacy Assertions

The validator checks that backup package bytes do not expose sample legal text or sample client names. F7 separately validates that cloud metadata is allowlisted and does not include matter names, client names, case numbers, filenames, OCR text, extracted text, source hashes, or recovery keys.

## Validation Command

```powershell
python tests\validate_e2e.py
```

## Release Gate

Before publishing a release bundle, run:

```powershell
python tests\validate_docs.py
python tests\validate_skeleton.py
python tests\validate_license.py
python tests\validate_vault.py
python tests\validate_intake.py
python tests\validate_extraction.py
python tests\validate_search.py
python tests\validate_rag.py
python tests\validate_backup.py
python tests\validate_cloud_boundary.py
python tests\validate_ui.py
python tests\validate_package.py
python tests\validate_e2e.py
python tests\validate_frozen_build.py
python main.py --selftest
ruff check .
```
