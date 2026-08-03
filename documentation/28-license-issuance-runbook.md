# 28 - Issuing a JurisNuru licence

Operational runbook for the vendor. This is the process a customer cannot see
and cannot do for themselves: JurisNuru licences are signed offline with a
private key that never leaves vendor control.

---

## 0. What a licence is

A licence is a small JSON file, conventionally `license.key`, carrying an
RSA-PSS/SHA-256 signature over a canonical serialization of its own fields:

```json
{
  "installation_id": "ec65d956-933f-4b58-9cb7-b11628bb1170",
  "license_id": "LIC-...",
  "firm_display_name": "Kiunga & Company Advocates",
  "plan": "enterprise",
  "features": { "...": true },
  "expiry": "2027-12-31",
  "issued_at": "2026-08-03T11:04:12Z",
  "signature": "base64..."
}
```

Three properties follow from that, and they shape the whole process:

- **It is bound to one machine.** `installation_id` is checked against the
  identity the application generated on first run. A licence issued for one
  laptop will not open on another; it reports `installation_mismatch`.
- **It is verified offline.** The application never contacts a server. The
  public key is compiled into `licensing/core.pyd` in release builds.
- **It cannot be reissued without the private key.** There is no recovery path
  if `_vendor/private_key.pem` is lost — see §6.

---

## 1. What you need before issuing

| Item | Where it lives | Notes |
|---|---|---|
| `_vendor/private_key.pem` | Vendor signing machine only | Never committed; `_vendor/` is gitignored |
| The customer's Installation ID | Sent by the customer | Shown on the activation screen |
| Firm display name | Agreed commercially | Appears in the app after activation |
| Plan | Agreed commercially | `solo`, `pro`, or `enterprise` |
| Expiry | Agreed commercially | `YYYY-MM-DD` |

Confirm the signing key matches the build the customer is running before you
issue anything:

```powershell
python scripts\verify_trust_anchor.py
```

That asserts `licensing/core.py` and `resources/license_public_key.pem` publish
the same key. It does **not** prove the customer's build carries it — if they
are on an older release, see §5.

---

## 2. Getting the Installation ID from the customer

The activation screen shows it and offers a **Copy ID** button. Ask for the
value only, e.g.:

```
ec65d956-933f-4b58-9cb7-b11628bb1170
```

It is a UUID generated on first run and stored at
`%APPDATA%\WakiliOS\settings\installation.json`. It contains nothing sensitive
and is safe to send by email.

**Each seat needs its own.** A firm of eight advocates on eight laptops sends
eight IDs and receives eight files. There is no firm-wide licence file — seat
count is enforced by the firm backend, not by the licence.

---

## 3. Issuing

On the signing machine, from the repository root:

```powershell
python tools\sign_license.py <installation-id> "<firm name>" <plan> <expiry> <output>
```

Worked example:

```powershell
python tools\sign_license.py `
  ec65d956-933f-4b58-9cb7-b11628bb1170 `
  "Kiunga & Company Advocates" `
  enterprise `
  2027-12-31 `
  out\kiunga-alice-wanjiru.key
```

Name the output after the firm *and the person or machine*. You will be issuing
several per firm, and `license.key` eight times over is not a filing system.

### Verify before sending

```powershell
python -c "import sys; sys.path.insert(0,'.'); from pathlib import Path; from licensing.core import embedded_public_key_pem, read_license_file, verify_license_document; d=read_license_file(Path(r'out\kiunga-alice-wanjiru.key')); print(verify_license_document(d, embedded_public_key_pem(), d.installation_id).status)"
```

Expect `active`. Anything else means do not send it:

| Status | Meaning |
|---|---|
| `active` | Good |
| `bad_signature` | Signed with a key the build does not carry (§5) |
| `installation_mismatch` | Wrong Installation ID |
| `expired` | Expiry is in the past |
| `malformed` | File is not a licence document |

---

## 4. Sending it

Email the `.key` file to the firm. It is not a secret in the usual sense — it
is useless on any other machine — but it does carry the firm's name and plan,
so treat it as commercial correspondence.

Tell the recipient plainly:

> Save the attached file, open JurisNuru, choose **Browse**, select it, then
> **Activate license**.

Two files are commonly mistaken for a licence, and the application rejects both
by name: `license_public_key.pem` (the verification key, shipped inside the
app) and `installation.json` (the machine identity). If a customer reports
"invalid licence", ask which file they selected before anything else.

---

## 5. When the customer's build carries a different key

`bad_signature` on a licence you just issued almost always means the customer
is running a build from before the current signing key.

Check which key their build carries:

```powershell
& "<their install>\DocumentVaultIngestionEngine.exe" --selftest
```

Then compare their release version against the one that introduced the key.
There is no way to sign for a key you do not hold — the customer must be
upgraded to a build carrying the current public key. Ship them the current
release ZIP and reissue.

---

## 6. Key custody

**Outstanding at the time of writing.** The current private key is unencrypted
PKCS8 in a development working tree. Before any licence is issued to a paying
firm:

- Encrypt it at rest and escrow it in two locations, one offsite. Losing it
  means no licence can ever be issued again, for anyone, and every future
  release needs a new key and a full reissue to every existing customer.
- Move signing to a dedicated machine that is not a general development
  workstation.
- Keep an issuance log: firm, person, installation ID, plan, expiry, date.
  Nothing in the product records what you have issued.

See [27-jurisnuru-signing-key-decision.md](27-jurisnuru-signing-key-decision.md)
for how the current key was chosen and why.

---

## 7. Rotating the key

Rotation invalidates every licence in the field simultaneously, so it is a
customer-visible event, not a maintenance task.

1. `python tools\keygen.py 4096` on the signing machine. This rewrites
   `licensing/core.py` and `resources/license_public_key.pem` together.
2. `python scripts\verify_trust_anchor.py` — the two must agree.
3. `python tests\validate_license.py` — asserts the embedded anchor rejects
   foreign signatures.
4. Build and ship a release carrying the new key.
5. Reissue a licence to **every** installation, against the new key.

Do not rotate without a plan for step 5. A customer whose licence stops working
after an update, with no replacement ready, cannot open their own matter files.

---

## 8. What is not automated

Stated so it is not assumed:

- **No licensing server, no self-service portal.** Issuance is manual, by email.
- **No revocation.** Once issued, a licence works until it expires. There is a
  local `disabled` state, but nothing pushes it from the vendor side.
- **No issuance record.** The product does not know what you have issued; the
  log in §6 is the only record.
- **No expiry warning.** The application does not warn a firm that its licence
  is close to expiring. Track expiry dates yourself and reissue ahead of time.
