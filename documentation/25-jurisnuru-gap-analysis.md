# 25 - JurisNuru gap analysis: brief, portal, and what ships

## 0. Scope and method

This compares three things that had drifted apart:

1. **The brief** — `juris_nuru_product_spec/JurisNuru-Product-Brief.pdf`, 16 slides. Cited by slide number.
2. **The portal** — the Kenyan Judiciary e-filing system at `efiling.court.go.ke`, reviewed from 14 photographs of a live law-firm account (July 2026). This is the ground truth the product must mirror, because it is what the work actually looks like.
3. **What ships** — this repository, at the commit introducing this document.

Assessed on `feat/jurisnuru-reconcile`: `origin/main` plus the reconcile and filing-record work.

**Grading.** `REAL` means *a user can reach it through the UI and it does the thing* — not "the function exists in `wakilios/core.py`". That distinction is why this document was rewritten. The previous version marked `MatterParty CRUD` as **DONE (core+API)** while the Parties tab in the running application was a list widget permanently displaying the string `"Parties involved"`: the data was persisted and invisible. Every `REAL` below cites a file and a test that exercises it through the UI.

---

## 1. Executive gap table

| Brief promise | Slide | Verdict | Where it lives |
|---|---|---|---|
| Licensing gate, then open dashboard | 5 | **REAL** | `ui/app.py` `QStackedWidget`; `tests/validate_ui.py` asserts the locked state and both wrong-file rejections |
| Matter workspace: identity, people, dates, documents, history | 3, 4 | **REAL** | 8 sub-tabs mirroring the portal; `tests/validate_matter_workspace_tabs.py` |
| Encrypted document custody | 3, 6 | **REAL** | `vault/core.py` AES-GCM + audit ledger; `tests/validate_vault.py` |
| Searchable memory / grounded RAG with visible sources | 3, 7 | **PARTIAL** | `rag/core.py` returns real citations, but the surface is a box in the Settings tab, not slide 14's per-matter panel |
| Independent record of what was filed | 13 | **PARTIAL** | `matter_filing_records` and the Filing record tab now exist; the tab is a list with a placeholder Add, not a data-entry form |
| Recoverable continuity: receipt, filed copy, service proof, next action | 13 | **PARTIAL** | Modelled (`filing_role`, `what_was_served`, `next_action`; next actions reach the `.ics` export); no UI to classify a document |
| Product map nav: Matters / Documents / Filing record / Search / Reports / Settings | 14 | **ABSENT** | Ships as Dashboard / Workspace / Settings / About |
| Per-matter AI context panel, source count, "Lawyer review required" | 14 | **ABSENT** | RAG is global, in Settings. `document_summaries.approval_status` exists and is unused |
| Reports | 14 | **ABSENT** | No surface, no aggregate query |
| Role-based access | 6, 9 | **REAL** | Enforced server-side in `wakilios/core.py`; `tests/validate_seat_networking.py` |
| Least privilege / purpose limitation | 9 | **PARTIAL** | Roles yes; license entitlements parsed and discarded (§3.2) |
| Audit trail | 6, 9 | **REAL** | `_audit()` on every mutation, viewer in Settings |
| Firm dashboard: payable/paid/balance and per-station counts | — | **ABSENT** | The portal has it; JurisNuru has no aggregate view |

---

## 2. Domain model vs the portal's case-detail tabs

The portal's case-detail view (e.g. `HCCOMM/E214/2026`, tracking `AERJ2026`, Milimani High Court) has eight tabs. **The matter workspace matches all eight by name and order.** That correspondence is the product's strongest asset — a lawyer who uses the portal already knows this screen — and it is why the gaps below are worth closing rather than redesigning around.

| Portal tab | Fields observed on the portal | Backend | UI | Verdict |
|---|---|---|---|---|
| Summary | case category, case type, station, case number, filed by, tracking number (used for SMS `22490`, USSD `*508#`, and MPESA/KCB reconciliation) | `matters` via `search/core.py` `MatterRecord` | `summaryTab`, free text | **PARTIAL** — no tracking-number field on the matter |
| Parties | category, party type (`1st Plaintiff`, `1st Respondent`, `1st Interested Party`), name, firm/agent, nationality, gender | `matter_parties` | `partiesTab` | **PARTIAL** — renders as of this commit; no nationality/gender; Add writes a placeholder |
| Activities | activity (`Mention`, `Directions`), date, court room, actioned to (judge), outcomes | `matter_activities` | `activitiesTab` | **PARTIAL** — renders as of this commit; `court_session` covers court room; no explicit judge field |
| Lodging | date, file count, created by, fee payable, fees paid, status (`Not Payable`), "File Additional Documents" | `lodgings` + `actioning_status` | `lodgingsTab` | **PARTIAL** — renders as of this commit; no fee payable/paid rollup on the row |
| Court Decisions | decision type, date, court, decision maker, outcome | `court_decisions` | `courtDecisionsTab` | **PARTIAL** — renders as of this commit |
| Fees | payment type, PRN, date generated, amount, paid, balance, Invoice / Pay Now | `fee_entries` + `prn` | `feesTab` | **PARTIAL** — no balance column; payment actions correctly out of scope |
| Receipts | customer ref#, transaction no, date, customer mobile, channel (`PYBL`), amount paid, verified | `receipts` | `receiptsTab` | **PARTIAL** — no channel or verified flag |
| Documents | "Uploaded at the registry" vs "Uploaded during assessment / Filed on Current Case", grouped by party, timestamped, `Not Actioned` | `documents` + `filing_role` | `matterDocumentsTab` | **PARTIAL** — flat list; no registry/assessment split, no grouping by party |

Plus one tab the portal does not have and the brief demands: **Filing record** (slide 13), backed by `matter_filing_records`.

**Vocabulary caveat.** `Not Payable`, `Not Actioned`, `PYBL`, `1st Interested Party` and the station names come from photographs of **one firm's account at a subset of stations**. They are stored as free text with suggested values — deliberately not enums — until confirmed more widely.

---

## 3. Confirmed defects

Each verified against the working tree.

### 3.1 Fixed in this branch

- **Four of eight matter tabs never rendered.** `_on_add_party`, `_on_add_activity`, `_on_add_lodging` and `_on_add_court_decision` wrote to the backend and refreshed nothing; only Fees and Receipts called a refresh. Fixed with `MATTER_TAB_VIEWS` + `_refresh_matter_workspace()`; guarded by `tests/validate_matter_workspace_tabs.py`, confirmed to fail against the old behaviour.
- **No way to open an existing matter.** `_current_matter_id` was set only by creating one, so after a restart the workspace could show nothing. Selecting a matter now opens it.
- **No schema migration mechanism.** `_create_schema` is entirely `CREATE TABLE IF NOT EXISTS`, a no-op against an existing database, so any new column reached fresh installs only. Fixed with `_migrate_schema` over `PRAGMA user_version`; `tests/validate_schema_migration.py` covers upgrade, idempotence, and row survival.
- **No test bound the shipped license key.** Every check in `validate_license.py` supplied its own ephemeral keypair, so the embedded trust anchor was never exercised and a key substitution left the suite green. Fixed with `_validate_embedded_trust_anchor` plus `scripts/verify_trust_anchor.py` in CI after obfuscation.
- **Mixed line endings hid a security-relevant diff.** No `.gitattributes`, `core.autocrlf=false`: a 12-line change to the embedded key in `licensing/core.py` presented as a 470-line diff. Fixed with `.gitattributes` and renormalization.

### 3.2 Open

- **License entitlements are decorative.** `LicenseValidationResult` carries `FeatureEntitlements` — `cloud_backup`, `matter_rag`, `hosted_ai` — and the UI only prints them into `entitlementStatusLabel` (`ui/app.py:1170`). Nothing is gated on them. The access control that does exist is role-based and enforced server-side. **Plan tiers are cosmetic**: a `basic` license unlocks exactly what `enterprise` does.
- **Add buttons write hardcoded placeholders.** `name="New Party"`, `receipt_number="NEW-RCT"`, `amount=0`, `document_kind="New Lodging"`. There is no data-entry form anywhere in the matter workspace, so the tabs demonstrate the round trip rather than supporting real work. This is the largest remaining gap between "the tabs render" and "a firm could use this".
- **Hardcoded password in solo mode.** `login(self._current_username, "admin-pass")` at `ui/app.py:615`, `:656` and `:965`. Solo mode provisions that account itself, so this is not a credential disclosed to a third party, but the solo password is fixed and the connection dialog's password field is ignored in solo mode.
- **Seats are provisioned users, not concurrent logins.** One user may reconnect from another laptop with the same credentials. Acceptable for a pilot, but it must be stated in commercial terms. See [26-jurisnuru-seats-networking.md](26-jurisnuru-seats-networking.md).
- **The signing key decision is open**, and the private half of the currently shipped key is not on the development workstation — so no license can presently be issued. See [27-jurisnuru-signing-key-decision.md](27-jurisnuru-signing-key-decision.md).

---

## 4. Absent relative to the brief

| Gap | What the brief expects | Cost |
|---|---|---|
| Data-entry forms | Slide 14 shows real matter content | Medium — one form per tab; the backend already accepts the fields |
| Tracking number on the matter | Slides 13, 14; the portal's primary reference for SMS, USSD and payment reconciliation | Small — one column, one field |
| Filing-role classification in the UI | Slide 13: receipt, filed copy, service proof | Small — `documents.filing_role` exists, needs a picker |
| Per-matter AI context panel | Slide 14: source count, "Lawyer review required" | Medium — move RAG out of Settings; `document_summaries.approval_status` already models the review gate |
| First-class Search | Slide 14 nav item | Small — the surface exists, in the wrong place |
| Reports | Slide 14 nav item | Medium — no aggregate query exists |
| Left-nav IA | Slide 14: Matters / Documents / Filing record / Search / Reports / Settings | Medium — the cost is test churn, not code; three UI tests hardcode the 4-tab structure |
| Firm dashboard | Portal parity: payable/paid/balance, per-station case counts | Medium — one aggregate query plus a surface |

---

## 5. Sequencing

1. **Data-entry forms per tab.** Highest value per line: model and rendering are both done, only input is missing.
2. **Tracking number on the matter, filing-role picker on upload.** Completes the slide 13 continuity story.
3. **Per-matter AI context panel.** The review-gate model already exists in the schema.
4. **Left-nav IA.** Do last, in one commit that rewrites the three UI tests together; keep `objectName`s stable so `findChild` assertions survive the container change.
5. **Reports and firm dashboard**, over a new `firm_overview()` aggregate.

Entitlement enforcement is sequenced against the licensing decision, not this list.

---

## 6. What was not verified

Stated plainly so this document is not read as broader assurance than it is.

- **OCR and RAG quality were not re-measured.** The figures in `evidence.md` (confidence 0.49-0.69 across five judgments) are from a previous run and were not reproduced.
- **Portal observations come from photographs of one firm's account** at Milimani High Court, Kiambu High Court, Nairobi and Nakuru ELRC, and several Magistrates' Courts. Field vocabulary may differ elsewhere. No API contract was inspected — there is none. JurisNuru does not integrate with the portal; it records alongside it.
- **Multi-machine LAN operation has never been run.** Seat behaviour is verified in-process through Starlette's `TestClient` only; no two-machine acceptance pass exists.
- **The frozen build was not rebuilt for this analysis.** CI's `package` job covers it; the local `dist/` dates from 2026-07-22.
- **No performance or scale testing** at any point. Matter counts, document counts and FTS5 behaviour under a real firm's corpus are unmeasured.
