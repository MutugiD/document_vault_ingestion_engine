# JurisNuru license signing key: open decision

Status: **open**. This document records the decision, the evidence, and the work
already done that is correct under either outcome. It is not a recommendation
that has been acted on — the repository is unchanged and still ships the key
that was on `main`.

## What the product does today

The license is an offline RSA-PSS/SHA-256 signature over a canonical
serialization of the license document (`licensing/core.py`). The verifying
public key is published in two places:

| Location | Role |
|---|---|
| `_PUBLIC_KEY_PEM` in `licensing/core.py` | The real trust anchor. Every verification uses it via `embedded_public_key_pem()`. Release builds Cython-compile this module to `licensing/core.pyd` so the key lives in machine code. |
| `resources/license_public_key.pem` | A data file bundled by `main.spec`. Never used for verification; the activation dialog only reads it to say "this is the verification key, not a license". |

Licenses are issued by `tools/sign_license.py`, which requires
`_vendor/private_key.pem`. `_vendor/` is gitignored, so **the private key has
never been in this repository** and there is no in-repo record of which keypair
was used.

## The finding that forces the decision

A keypair was generated on the development workstation
(`_vendor/private_key.pem`, RSA-4096) and the working tree had been switched to
use it. Checking that key against what the repository actually ships:

```
embedded key == resources/license_public_key.pem   : True
_vendor/private_key.pem matches the shipped key    : False
```

**The private half of the key JurisNuru currently ships is not on this
machine.** Only the private half of the locally generated keypair is.

This has a hard consequence. `tools/sign_license.py` can only sign with the key
in `_vendor/`, so as the repository stands **no valid license can be issued from
this workstation at all**. RSA public keys are not invertible; there is no
recovery path from the shipped public key.

## The three options

### (a) Keep the shipped key

No code change — this is the current state.

Viable **only if** the matching `_vendor/private_key.pem` still exists
somewhere: escrow, another workstation, a previous developer's machine. If it
does not exist anywhere, this option means the product can never issue a
license again, and is therefore not an option at all.

Locate it before choosing this. Verify a candidate with:

```powershell
python scripts\verify_trust_anchor.py     # confirms which key the repo ships
```

then confirm the candidate private key derives that same public key.

### (b) Adopt the locally generated keypair

Commit the new `_PUBLIC_KEY_PEM` block and `resources/license_public_key.pem`,
both of which the snapshot in the reconcile branch still holds.

Cost and risk:

- **Every license issued under the shipped key stops working**, reporting
  `bad_signature` — the same message a forgery produces, with nothing to tell a
  locked-out customer apart from an attacker. If any license is in the field,
  add a `superseded` status that tries the retired key as a secondary anchor and
  returns a distinguishable message. Both anchors compile into the `.pyd`;
  neither becomes environment-controlled, so the hardening model is preserved.
- **Provenance is weak.** The key was generated ad hoc on a development
  workstation and has been sitting as unencrypted PKCS8 in an active working
  tree alongside `dist-debug/`, `build-debug/`, `output/` and `tmp/`. For a
  product whose entire licensing story is "the trust anchor lives in native
  machine code", an anchor with unauditable custody undercuts the claim.
- Normalize line endings first. The working-tree diff for `licensing/core.py`
  read as 470 changed lines; `git diff -w --ignore-cr-at-eol` showed the real
  change was the 12-line key block and nothing else. Add `*.py text eol=lf` to
  `.gitattributes` so this never recurs.

### (c) Generate a fresh production keypair in a controlled ceremony

`python tools/keygen.py 4096` on a clean, offline machine. It rewrites both
`licensing/core.py` and `resources/license_public_key.pem` in place.

Same blast radius as (b) for any field licenses, but the resulting key has
defensible custody. Keep the current local keypair under a different filename
for development licenses.

## Decision criteria, in order

1. **Does the private half of the shipped key exist anywhere?**
   If no, (a) is eliminated.
2. **Have licenses been issued to real firms under the shipped key?**
   If yes, (b) and (c) both need the `superseded` fallback before shipping.
3. **Is ad-hoc workstation provenance acceptable for the production anchor?**
   If no, (c) over (b).

## Custody requirements, whichever key wins

- `_vendor/` stays gitignored, permanently.
- The private key is encrypted at rest and escrowed in two locations, one
  offsite. `tools/keygen.py` currently writes `NoEncryption()` PKCS8.
- Issuance happens on a dedicated machine, not a general development workstation.
- A written issuance runbook: who can sign, what is recorded, how a replacement
  license is issued to a locked-out firm.

## Work already done, correct under every option

Two gaps let the key swap happen silently, and both are now closed. Neither
depends on which key is chosen.

- **`tests/validate_license.py` now validates the shipped anchor.** Every other
  check in that file supplies its own ephemeral keypair, so the embedded key was
  never exercised and the suite stayed green through a key substitution. The new
  `_validate_embedded_trust_anchor` asserts the two published copies agree and
  that a license signed by any other key is rejected as `bad_signature`.
  Confirmed to fail against a simulated one-sided swap.
- **`scripts/verify_trust_anchor.py` runs in CI after obfuscation.** The release
  path never exercised verification — `--selftest` does not — so a key mangled by
  the Cython step would have shipped green.

## What is not yet decided

The key itself. Nothing in this repository should be treated as a production
signing anchor until questions 1 and 2 above are answered.
