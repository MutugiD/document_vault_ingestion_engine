# WakiliOS E2E Evidence Log

Date: 2026-07-16
Machine: WSL Ubuntu (development), Python 3.11
Branch: `main` (post-merge of PRs #39-#46)

## PR History

| PR | Title | Status |
| --- | --- | --- |
| #39 | WakiliOS: Expand FastAPI endpoints, fix deps, add API validation | Merged |
| #40 | WakiliOS: Backend client, login dialog, role-aware UI, workspace wiring | Merged |
| #41 | WakiliOS: Fee-receipt linking, document upload, audit log viewer | Merged |
| #42 | Docs: Restructure WakiliOS as in-process product | Merged |
| #43 | WakiliOS: Solo mode, in-process backend, audit log, fee-receipt linking | Merged |
| #44 | UI: Professional dark theme stylesheet and polish | Merged |
| #45 | UI: Redesign tabs - 10 tabs consolidated to 4 | Merged |
| #46 | Licensing hardening, clock guard, and release workflow | Merged |

## Validation Suites (all passing)

- `validate_docs.py` — 50 documentation files
- `validate_license.py` — Offline license, clock-rollback guard, NTP cross-check
- `validate_wakilios_backend.py` — Solo mode backend, matters, fees, audit
- `validate_wakilios_api.py` — FastAPI endpoints (Starlette TestClient)
- `validate_products.py` — 3-product catalog
- `validate_security_scan.py` — No secrets/credentials in repo
- `validate_vault.py` — AES-GCM encryption, wrong-key rejection
- `validate_intake.py` — PDF/DOCX import, quarantine, duplicates
- `validate_search.py` — FTS5 with hyphen sanitization
- `validate_rag.py` — Citation-backed responses, confidence scores
- `validate_backup.py` — Encrypted backup, restore, wrong-key rejection
- `validate_e2e.py` — Full intake-to-RAG-to-backup pipeline
- `validate_ui.py` — 4-tab UI widget verification
- `main.py --selftest` — Module imports, licensing identity, clock guard, version

## E2E Results (5 Kenyan court judgment PDFs)

| Phase | Result |
| --- | --- |
| Document Intake | 5/5 PDFs accepted, vaulted, text extracted |
| Search | 4 legal queries returning results (unfair dismissal, breach of contract, adverse possession, redundancy) |
| RAG | 5 questions answered (conf 0.49-0.69, 5 citations each, 21-24ms) |
| Matters | 5 litigation matters created (Commercial, Employment, Commercial, Employment, Land) |
| Audit | 21 events logged |
| Backup | 51KB package, restore verified, wrong key failed |
| UI | Solo mode, 4-tab layout, matter creation, party/fee addition, audit log all working |
| License | 4096-bit RSA key pair, sign+verify E2E, clock-rollback detection |
| Selftest | PASS (modules, licensing identity, clock guard, version 0.1.0) |

## CI/CD (IFC-Converter pattern)

| Job | Status |
| --- | --- |
| Lint & format (ruff) | ✓ Pass |
| Dependency audit (pip-audit) | ✓ Pass |
| Test & coverage (>=60%) | ✓ Pass |
| Build bundle (PyInstaller + obfuscation + selftest) | ✓ Pass |
| CodeQL (weekly) | Needs code scanning enabled in repo settings |

## Licensing Hardening

- Hard-coded RSA 4096-bit public key in `licensing/core.py` (spec §6.2)
- Clock-rollback guard with NTP cross-check (`licensing/clockguard.py`)
- Cython obfuscation script (`scripts/obfuscate_licensing.py`) compiles licensing to `.pyd`
- Vendor keygen (`tools/keygen.py`) and license signing (`tools/sign_license.py`)
- `_vendor/` in `.gitignore` (private keys never committed)

## UI Redesign (PR #48, 2026-07-17)

- **Sidebar layout**: Dark charcoal (#3B2F2F) sidebar with gold (#D4A017) accent border, "THE JUDICIARY" branding, nav buttons synced with tabs
- **Dashboard stat cards**: Total Payable / Paid / Balance Due with colored left borders (green, blue, gold)
- **Kenya Judiciary color scheme**: Primary green #006B3F, gold #D4A017, dark green #004D2B, white cards on #F5F5F5
- **All objectNames preserved**: validate_ui.py passes without modification
- **Evidence**: Offscreen screenshots in evidence/wakilios_redesigned_*.png

| Tab | Screenshot |
| --- | --- |
| Dashboard | evidence/wakilios_redesigned_dashboard.png |
| Workspace | evidence/wakilios_redesigned_workspace.png |
| Settings | evidence/wakilios_redesigned_settings.png |
| About | evidence/wakilios_redesigned_about.png |
| Full window | evidence/wakilios_redesigned_full.png |

## Comprehensive E2E Evidence (2026-07-17)

Full evidence JSON: `evidence/e2e_evidence_redesign.json`

### Phase 1: License & Key Bundling (7/7 PASS)
- 4096-bit RSA PSS + SHA-256 license signing/verification
- Installation identity generated, all feature entitlements verified (document_intake, cloud_backup, managed_restore, matter_rag)
- License status: active

### Phase 2: Vault Initialization (1/1 PASS)
- AES-GCM encrypted vault initialized with recovery key

### Phase 3: Multi-Format Document Intake (6/6 PASS)
| Format | Status | Extracted |
| --- | --- | --- |
| PDF | accepted | 92 chars |
| DOCX | accepted | 150 chars |
| TXT | rejected (unsupported format, by design) | 0 chars |
| Image-based PDF | accepted | 77 chars |
| Duplicate PDF | detected as duplicate | N/A |

### Phase 4: Matter Creation & Search (5/5 PASS)
- Litigation matter created: E2E-EVIDENCE-001, Amani Traders Ltd v Umoja Supplies
- Document linked to matter with vault object reference
- FTS5 search: "invoice default", "injunction", "dissipation" all return results

### Phase 5: RAG Performance (5/5 PASS)
| Query | Citations | Confidence | Time |
| --- | --- | --- | --- |
| What supports the injunction? | 1 | 0.27 | 2.1ms |
| What evidence for invoice default? | 1 | 0.42 | 2.5ms |
| What is the risk? | 1 | 0.20 | 2.5ms |
| **Average** | **1.0** | **0.30** | **2.4ms** |

### Phase 6: Backup & Restore (6/6 PASS)
- Create local backup: 44,973 bytes, snapshot encrypted
- Encryption verification: no plaintext in backup (firm name, PDF text both absent)
- Upload encrypted snapshot to in-memory grant backend
- Restore from backup: 102.1ms, data integrity verified (byte-exact match)
- Wrong key rejection: exception raised as expected

### Phase 7: WakiliOS Backend Solo Mode (7/7 PASS)
- Solo login as admin
- Create matter, add party, add fee (KES 15,000), add receipt
- Offline cache: 1 matter, read_only mode
- Audit log: 5 events

### Phase 8: Bundle Selftest (1/1 PASS)
- `./dist/WakiliOS/WakiliOS --selftest` → SELFTEST PASS

### All Validation Suites (2026-07-17)

| Suite | Result |
| --- | --- |
| validate_vault | PASS |
| validate_intake | PASS |
| validate_search | PASS |
| validate_rag | PASS |
| validate_backup | PASS |
| validate_e2e | PASS |
| validate_ui | PASS |
| validate_license | PASS |
| validate_wakilios_backend | PASS |
| validate_wakilios_api | PASS |
| validate_security_scan | PASS |
| validate_products | PASS |
| validate_admin_license_payment_boundary | PASS |
| Bundle selftest | PASS |

### Interactive UI E2E (87/87 PASS)

Full evidence JSON: `evidence/e2e_interactive_ui_evidence.json`

| Phase | Tests | Details |
| --- | --- | --- |
| Layout | 9/9 | Sidebar, stat cards, 4 tabs, title, min width |
| Dashboard - Solo mode | 4/4 | Login, role: admin (solo), status |
| Create matter | 5/5 | New matter, list updates, status: Created matter: NEW-001 |
| Refresh matters | 2/2 | Button works, list refreshes |
| Workspace sub-tabs | 25/25 | All 8 tabs (Summary/Parties/Activities/Lodgments/Court Decisions/Fees/Receipts/Documents), add party/activity/lodging/court decision/fee/receipt |
| Settings | 20/20 | Import, search, RAG, AI keys, backup, admin groups all present |
| Admin & audit | 2/2 | Sync: install=active, paid=True/cloud=True/rag=True/hosted_ai=False; audit: 17 events |
| About | 1/1 | Release info |
| Backup & restore | 2/2 | Backup: 3506 bytes; Restore: verified=True, wrong key failed=True |
| Selftest & workflow | 4/4 | Worker selftest PASS, Native workflow: citations=1, confidence=0.436 |
| Sidebar navigation | 5/5 | 4 nav buttons found, tab sync works all 4 directions |

## Known Issues

- CodeQL scanning needs to be enabled in GitHub repo Settings > Code security (manual step)
- Coverage threshold set to 60% (UI-heavy project; core modules at 80%+)