# Windows Legal Document Vault - Gap Analysis

| Current State | Expected Product Behavior | Missing Implementation | Priority | Validator Needed | Impact |
| --- | --- | --- | --- | --- | --- |
| admin/license sync boundary exists | admin can enable/disable paid features through sync | real owner backend endpoint and operator dashboard | high | hosted admin integration validator | monetization |
| feature flags exist | paid plans map cleanly to product modules | payment entitlement model | high | entitlement validator | monetization |
| encrypted vault works | operator can manage matters through UI | production UI screens | high | UI workflow validator | usability |
| local backup works | cloud uploads use owner backend grants | real grant client/backend contract | high | cloud backend validator | backup operations |
| release ZIP works | user installs with installer | installer wrapper | medium | installer validator | distribution |
| unsigned EXE works | commercial release is signed | code-signing workflow | medium | signed artifact validator | trust/publishing |
| no update channel | signed update checks exist | update manifest and updater boundary | medium | update validator | maintenance |
| docs exist | clean-machine report is repeatable | VM test report template and checklist | medium | package validator extension | release readiness |

## Immediate Gap Order

1. Managed cloud grant backend.
2. Payment entitlements.
3. Production Windows UI.
4. Installer and code signing.
5. Automatic update channel.
6. Hosted admin dashboard endpoint wiring.

## Gap Closure Rule

Every PR that closes a gap must update this file with the new current state and validator evidence.
