# Enterprise Masterpack

This masterpack is the documentation-first control layer for taking Document Vault
Ingestion Engine from local product foundation to an enterprise-ready Windows
release for Kenyan legal teams.

It covers the three product lines:

- Windows Legal Document Vault.
- Document Intake Engine.
- Local Matter RAG Connector.

Enterprise work proceeds one pull request at a time. Each PR must update the
relevant documentation, add or extend validation, pass CI, and be merged before
the next feature branch starts.

## Reading Order

1. [architecture.md](architecture.md) - enterprise system architecture and product boundaries.
2. [product-roadmap.md](product-roadmap.md) - F27 onward PR sequence.
3. [ci-cd-release.md](ci-cd-release.md) - validation, CI, merge, and release gates.
4. [security-compliance.md](security-compliance.md) - privacy, secrets, crypto, and audit rules.
5. [windows-distribution.md](windows-distribution.md) - Windows packaging and publishing path.
6. [e2e-validation-plan.md](e2e-validation-plan.md) - local, public Kenyan, and clean-machine testing.
7. [commercial-operations.md](commercial-operations.md) - licensing, admin, payment, cloud, support, and rollout.

## Delivery Principles

- Documentation leads implementation.
- Branch names use `feature/...`; branch names must not contain `codex`.
- One feature PR is active at a time.
- CI must run all completed validators, not only the current validator.
- Release artifacts must not contain private keys, provider keys, cloud credentials,
  client files, recovery keys, or plaintext legal documents.
- Disablement of paid or online features must never block local document recovery
  or export.

