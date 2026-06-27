# Windows Legal Document Vault - Gap Analysis

| Current State | Expected Product Behavior | Missing Implementation | Priority | Validator Needed | Impact |
| --- | --- | --- | --- | --- | --- |
| admin/license sync boundary exists | admin can enable/disable paid features through sync | real owner backend endpoint and operator dashboard | high | hosted admin integration validator | monetization |
| feature flags exist | paid plans map cleanly to product modules | payment entitlement model | high | entitlement validator | monetization |
| encrypted vault works | operator can manage matters through UI | production UI screens | high | UI workflow validator | usability |
| managed grant client boundary exists | cloud uploads/downloads use owner backend grants | deployed owner backend service | high | cloud backend integration validator | backup operations |
| release ZIP works | user installs with installer | installer wrapper | medium | installer validator | distribution |
| unsigned EXE works | commercial release is signed | code-signing workflow | medium | signed artifact validator | trust/publishing |
| no update channel | signed update checks exist | update manifest and updater boundary | medium | update validator | maintenance |
| docs exist | clean-machine report is repeatable | VM test report template and checklist | medium | package validator extension | release readiness |

## Immediate Gap Order

1. Payment entitlements.
2. Production Windows UI.
3. Installer and code signing.
4. Automatic update channel.
5. Hosted admin dashboard endpoint wiring.
6. Deployed cloud grant backend integration.

## Gap Closure Rule

Every PR that closes a gap must update this file with the new current state and validator evidence.
