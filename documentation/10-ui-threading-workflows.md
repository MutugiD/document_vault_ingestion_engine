# 10 - UI Threading Workflows

## Purpose

Provide a responsive Windows desktop UI for intake, matters, backup, restore,
licensing, and local RAG.

## UI Stack

PySide6 with a professional dark navy/blue theme (`ui/wakilios.qss`).

## Tab Layout (4 tabs)

| Tab | Sections |
| --- | --- |
| **Startup gate** | Signed license activation before the product shell opens |
| **Dashboard** | Backend connection (Start Solo / Connect to server), Firm setup, Vault initialization |
| **Workspace** | Matter list with actions (New, Refresh, Export calendar), 8 sub-tabs: Summary, Parties, Activities, Lodgings, Court Decisions, Fees, Receipts, Documents |
| **Settings** | Document Import, Search & RAG, AI Keys, Backup/Restore, Admin & Audit Log |
| **About** | Module cards, release info, native workflow button |

## Solo Mode

- "Start Solo" button on Dashboard initializes an in-process `WakiliOSBackend`.
- UI calls `wakilios.core` directly — no server needed.
- Role is set to the admin user; all features available.

## Multi-Seat Mode

- "Connect" button on Dashboard connects to a remote FastAPI server via `WakiliOSClient`.
- `WakiliOSClient` uses `urllib` (no extra HTTP deps for Windows desktop).
- Role-aware UI: buttons enable/disable based on user permissions (write, accounts, summary, document roles).

## Worker Pattern

Long operations (backup, restore, OCR, RAG queries) run in `QThread` workers
to keep the UI responsive. The `BackgroundWorker` class wraps a callable and
emits `succeeded`/`failed` signals back to the main thread.

## Key Widgets

| Object Name | Purpose |
| --- | --- |
| `backendConnectionDialog` | Solo/Connect panel with server URL, username, password |
| `startSoloButton` | Initializes local backend |
| `connectButton` | Connects to remote backend |
| `roleStatusLabel` | Shows current role (e.g., "admin (solo)") |
| `matterList` | List of litigation matters |
| `matterWorkspaceTabs` | 8 sub-tabs for matter details |
| `refreshMatterListButton` | Refreshes matter list from backend |
| `newMatterButton` | Creates new matter |
| `documentReviewQueue` | Import queue with OCR status |
| `matterSearchInput` | FTS5 search box |
| `ragQuestionInput` | RAG question box |
| `ragCitationPacketOutput` | RAG answer with citations |
| `auditLogList` | Audit event viewer |
| `refreshAuditLogButton` | Refreshes audit log |
