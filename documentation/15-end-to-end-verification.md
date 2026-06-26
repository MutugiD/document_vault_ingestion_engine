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

## F17 Real-World RAG Boundary

`tests/validate_real_world_rag_e2e.py` expands the integrated workflow with realistic legal-document fixtures:

1. Generate an old archived PDF with land, rent, lease, registry, and reconstruction facts.
2. Generate a DOCX pleading with defence, counterclaim, evidence, deadline, and hearing-preparation facts.
3. Generate an image-only scanned PDF that has no extractable text and must remain `pending_tesseract`.
4. Import the PDF, DOCX, and scanned PDF through quarantine.
5. Confirm intake copies source files and does not move or delete them.
6. Import a duplicate PDF copy and confirm duplicate hash detection.
7. Import a legacy `.doc` file and confirm current unsupported-file behavior.
8. Store original bytes as encrypted immutable vault objects.
9. Confirm encrypted object files do not equal plaintext source bytes.
10. Add matter, document, and version records for all accepted files.
11. Build a matter-scoped RAG index that excludes OCR-pending scanned content.
12. Ask forty grounded questions across the PDF and DOCX facts.
13. Confirm every RAG answer packet includes citations and the expected grounded phrase.
14. Create an encrypted backup and confirm plaintext legal/client phrases are absent from package bytes.
15. Upload through the managed cloud boundary and confirm metadata contains only allowlisted fields.
16. Restore the backup and verify all original PDF, DOCX, and scanned-PDF bytes can be read from the restored vault.

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
python tests\validate_real_world_rag_e2e.py
python tests\validate_frozen_build.py
python main.py --selftest
ruff check .
```
