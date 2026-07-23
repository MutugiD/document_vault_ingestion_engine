# 00 - System Overview

## Purpose

JurisNuru is a Windows local-first litigation management system for law firms. It provides matter management, document custody, search, RAG retrieval, and backup — all running on a single desktop without requiring a server.

## Users

- Solo advocate.
- Small law firm owner.
- Legal assistant or clerk.
- Product owner/admin managing licenses and cloud backup entitlements.

## Goals

- Install and run on Windows.
- Activate with a signed offline license.
- Manage litigation matters with parties, activities, lodgings, court decisions, fees, and receipts.
- Store legal documents locally in encrypted form.
- Import scanner output and manual files.
- Extract text from PDF/DOCX/image sources.
- Organize documents by matter.
- Track document versions and lifecycle status.
- Search locally.
- Retrieve matter-scoped RAG context with citations.
- Generate AI-assisted matter summaries.
- Prepare filing packs for manual court upload.
- Export matter calendars as `.ics`.
- Back up and restore safely.
- Upload only encrypted backup packages to managed cloud storage.

## Architecture

JurisNuru is a single-process desktop application. The UI calls Python modules directly — no separate server, no HTTP API, no client/server split.

```
JurisNuru Desktop App (single process)
├── ui/app.py ─── PySide6 shell, matter workspace, login, role-aware controls
├── wakilios/core.py ─── Firm backend: users, seats, roles, matters, fees, receipts, audit
├── wakilios/api.py ─── Optional LAN/VPN FastAPI wrapper (for multi-seat, NOT required for solo)
├── core/ ─── ManualAppSession: intake → extraction → vault → search → RAG
├── vault/ ─── Encrypted object storage, recovery keys
├── intake/ ─── Document import, quarantine, duplicate detection
├── search/ ─── SQLite FTS5 matter-scoped search
├── rag/ ─── Local citation-first RAG retrieval
├── backup/ ─── Encrypted backup/restore, cloud boundary
├── ai/ ─── Hosted AI provider boundary
├── licensing/ ─── Offline license validation, entitlements
└── security_checks/ ─── Security scan, key hygiene
```

For solo use, the desktop app calls `wakilios.core` directly. For multi-seat firms, the optional `wakilios.api` FastAPI wrapper allows multiple desktop clients to connect to a firm-hosted backend on LAN/VPN.

## Non-Goals

- No direct court filing automation.
- No hosted RAG by default.
- No hosted embeddings by default.
- No hosted vector database by default.
- No local LLM in the current build.
- No Wakili-Mkononi integration.
- No hosted document viewing.
- No cloud OCR by default.

## Published Products

1. JurisNuru — Litigation management with matter workspace, fees/receipts, and calendar.
2. Document Intake Engine — Import, extract, and vault legal documents.
3. Local Matter RAG Connector — Citation-first retrieval over matter documents.

## Stack

- Python 3.11.9.
- PySide6.
- SQLite and FTS5.
- PyMuPDF.
- python-docx.
- Tesseract OCR.
- cryptography.
- PyInstaller.
- FastAPI + uvicorn (optional, for multi-seat LAN/VPN mode).