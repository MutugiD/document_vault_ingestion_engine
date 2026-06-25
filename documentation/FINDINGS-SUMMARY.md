# Findings Summary

## Main Finding

The first commercial build should be a local-first Windows document custody and intake system, not an AI/RAG system.

## Product Shape

The application should combine:

- licensed Windows app shell
- local encrypted vault
- document intake and OCR
- matter/document/version metadata
- local search
- filing-pack preparation
- local backup and restore drill
- managed encrypted cloud backup

## Deferred Work

The following remain intentionally out of the first build:

- RAG
- embeddings
- vector search
- local LLM
- Wakili-Mkononi integration
- direct Judiciary e-filing automation
- hosted AI

## Highest Risks

1. Packaging native OCR/PDF/UI dependencies into a reliable Windows bundle.
2. Keeping plaintext legal documents out of app-managed temporary folders after intake.
3. Designing licensing so disablement never traps client data.
4. Designing cloud backup so metadata does not leak legal identifiers.
5. Proving restore on a clean machine, not just backup creation.

## Remedy Strategy

Build feature-by-feature with validation scripts. Do not move to the next feature until the current feature has a local executable validator.
