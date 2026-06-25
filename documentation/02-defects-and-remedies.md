# 02 - Defects And Remedies

## Risk Register

| ID | Risk | Remedy | Validation |
| --- | --- | --- | --- |
| D1 | Python dependency drift breaks Windows packaging. | Pin Python 3.11.9 and test frozen exe. | `validate_package.py` |
| D2 | License disablement traps client data. | Disable paid features only; keep export/recovery available. | `validate_license.py` |
| D3 | Plaintext remains in quarantine. | Delete after encrypted vault write; audit failures. | `validate_intake.py` |
| D4 | Cloud metadata leaks legal identifiers. | Allowlist metadata fields only. | `validate_cloud_boundary.py` |
| D5 | Backup exists but restore fails. | Restore drill is mandatory. | `validate_backup.py` |
| D6 | OCR failures block document custody. | Store encrypted original and mark OCR failed/retryable. | `validate_extraction.py` |

## Decision Register

Accepted decisions live in [STATUS.md](STATUS.md).
