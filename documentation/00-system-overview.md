# 00 - System Overview

## Purpose

Document Vault Ingestion Engine is a Windows local-first system for legal document intake, encrypted custody, local search, backup, and restore.

## Users

- Solo advocate.
- Small law firm owner.
- Legal assistant or clerk.
- Product owner/admin managing licenses and cloud backup entitlements.

## Goals

- Install and run on Windows.
- Activate with a signed offline license.
- Store legal documents locally in encrypted form.
- Import scanner output and manual files.
- Extract text from PDF/DOCX/image sources.
- Organize documents by matter.
- Track document versions and lifecycle status.
- Search locally.
- Prepare filing packs for manual court upload.
- Back up and restore safely.
- Upload only encrypted backup packages to managed cloud storage.

## Non-Goals

- No direct court filing automation.
- No RAG.
- No embeddings.
- No vector database.
- No local LLM.
- No Wakili-Mkononi integration.
- No hosted document viewing.
- No cloud OCR by default.

## Stack

- Python 3.11.9.
- PySide6.
- SQLite and FTS5.
- PyMuPDF.
- python-docx.
- Tesseract OCR.
- cryptography.
- PyInstaller.
