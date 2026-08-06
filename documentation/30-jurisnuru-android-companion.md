# JurisNuru Android companion — specification

## Who it is for, and what it is not

One user profile drives this: **the senior manager advocate, out of the office.** In court, at a client's premises, travelling between stations. They need to know what is happening and when, look up a matter quickly, see where a case stands, and prompt a colleague.

They do **not** need to draft, file, upload, or read documents on a phone screen. That is deliberate scoping, and it is also the security position: a phone left in a taxi must not be a route into a firm's document vault.

**Read-mostly with two writes.** The phone reads the diary, matters and reminders. It writes reminders and acknowledgements. Nothing else.

## Connectivity model — sync on the firm network, work offline

```
IN THE OFFICE                              OUT OF THE OFFICE
┌──────────────────┐                       ┌──────────────────┐
│ firm backend     │  ── Wi-Fi sync ────►  │ phone            │
│ (private LAN,    │     GET /sync/snapshot│ encrypted Room DB│
│  --serve)        │  ◄── queued writes ── │ works offline    │
└──────────────────┘                       └──────────────────┘
        ▲                                           │
        └───── nothing on the internet ─────────────┘
```

Chosen over a VPN or an internet-exposed backend because it keeps the product's central promise intact: a firm's matter data never leaves a network the firm controls. The cost is that the phone's copy is as old as its last sync, and outgoing reminders queue until it is next on the firm network. Both must be visible in the interface — a "synced 3 days ago" line, and a queued-items indicator — rather than left for the user to infer.

**Reaching the server is try-and-fail-fast, not SSID detection.** Reading the Wi-Fi SSID on modern Android requires `ACCESS_FINE_LOCATION`, and asking a law firm for location permission to check which network they are on is not a trade worth making. `GET /health` with a two-second timeout, and stay offline on failure.

## What the backend already provides

All of this exists and is tested as of schema version 5. The phone needs no new server work to reach parity with this specification.

| Need | Endpoint | Notes |
|---|---|---|
| Pair without typing a password | `POST /devices/claim` | Unauthenticated; the 8-character code is the credential |
| Everything for offline use | `GET /sync/snapshot?since=` | Matters, calendar, reminders, roster. No documents |
| The diary | `GET /calendar/upcoming` | Hearings, lodging deadlines, decisions, next actions |
| Reminders in | `GET /reminders` | The caller's own inbox only |
| Reminders out | `POST /reminders` | Any writing role, including from a phone |
| Acknowledge | `POST /reminders/{id}/acknowledge` | Recipient only |
| Liveness | `GET /health` | Also carries the schema version |

Everything else is **403 for a device token** — matter creation, workspace reads, uploads, the audit log. `allow_device` is opt-in on `require_authenticated`, so a capability added to the backend later is denied to phones until someone decides otherwise.

## Pairing

1. On the desktop: **Settings → Paired phones → Pair a phone.** An 8-character code appears with the server URL, valid ten minutes, single use.
2. On the phone: enter the server URL and the code.
3. The phone receives a device token valid ninety days and stores it in the Android Keystore.

The code alphabet excludes `I`, `L`, `O`, `0` and `1`: it is read off a screen and typed on a phone across a desk, and a transcription slip is indistinguishable from a rejected code.

**Unpairing is on the desktop, and it is the reason the pairing screen exists.** A ninety-day credential with no withdrawal path is an unbounded one. Revocation takes effect on the device's next request, and both the owner and an administrator can do it.

## Screens

| Screen | Content | Source |
|---|---|---|
| **Today** | The day's hearings, lodging deadlines, next actions. The default screen. | `calendar` rows for today |
| **Calendar** | Month and agenda views over the sync horizon (120 days ahead, 7 behind). | `calendar` |
| **Matters** | List with instant search over reference, client, parties, case number. | `matters` + Room FTS |
| **Matter detail** | Status, filing status, case number, station, next dates, summary. A "Remind someone about this" action. | `matters` + `calendar` filtered |
| **Reminders** | Inbox with unread state and acknowledge; compose, addressed from the roster. | `reminders` + `users` |
| **Pairing** | Server URL, code entry, sync status, last-synced time. | — |
| **Settings** | Digest time, sync frequency, battery-optimisation guidance, unpair. | — |

The matter detail screen shows a summary and **no documents**. When an advocate needs the document, they need the desktop — that is the honest boundary, and the interface should say so rather than showing a broken affordance.

## Notifications — local only, no Firebase

`AlarmManager.setExactAndAllowWhileIdle` fires a daily digest computed from the phone's own Room copy. `WorkManager` runs a periodic sync every six hours on an unmetered network, failing fast when the backend is unreachable — which *is* the offline behaviour, not a workaround for it.

No Firebase, no push service, no Google account. The phone already holds the data; it does not need to be told.

### The three things that will break this in the field

Named now because each one is discovered late and expensively.

1. **OEM battery managers.** Xiaomi, Oppo, Vivo, Samsung and Tecno kill background work aggressively, and Tecno and Infinix are common in Kenya. Without an onboarding screen that walks the user through disabling battery optimisation for JurisNuru, the digest will silently stop on exactly the phones this product's users carry. This is the single most under-estimated item in the build.
2. **`SCHEDULE_EXACT_ALARM` is restricted on Android 13+.** Needs `USE_EXACT_ALARM` (justifiable for a calendar reminder) or a user-granted permission, with a graceful fall back to an inexact alarm.
3. **`POST_NOTIFICATIONS` is a runtime permission on Android 13+.** It must be requested with context, at a moment where the reason is obvious, not on first launch.

## Storage on the device

Encrypted at rest, and there are two workable ways to do it. **Decide deliberately; do not roll your own either way.**

- **SQLCipher under Room**, key held in the Android Keystore via `androidx.security:security-crypto`, with `setUserAuthenticationRequired` so the phone's own lock protects it. Queryable, standard, heavier dependency.
- **A single AES-GCM blob** matching `vault/core.py`'s existing AESGCM and PBKDF2 choices, decrypted into memory at open with an in-memory index. Far simpler, no SQLCipher, and entirely adequate at a few thousand rows.

**Recommendation: the AES-GCM blob for v1.** A realistic snapshot is well under 2 MB, so the queryability SQLCipher buys is not needed yet, and it reuses cryptographic choices that are already reviewed in this codebase.

## Sync payload and its honest limit

A matter header is roughly 600 bytes of JSON. Five hundred matters is about 300 KB; two thousand calendar entries about 600 KB. A full snapshot is under 2 MB — trivial on office Wi-Fi.

`since` filters on `created_at`, so **it returns appends only**. The schema has no `updated_at` and no soft delete, so a rescheduled hearing or a closed matter cannot appear in a delta.

**The client must therefore take a full snapshot whenever the last full sync is more than seven days old.** At under 2 MB that is cheap and correct. This is a real limitation, not a rough edge: do not describe the product as having delta sync. Fixing it properly means adding `updated_at` and a change log, which touches every write path in `wakilios/core.py`.

## Repository layout and versioning

**A sibling `android/` directory in this repository**, not a separate repo. The sync contract and the backend must version together; separate repositories guarantee schema drift, and the failure mode — a phone that syncs successfully against a schema it does not understand — is silent.

```
android/
  settings.gradle.kts
  app/build.gradle.kts
  app/src/main/java/ke/jurisnuru/mobile/
    data/     ApiClient, SnapshotDto, SyncRepository
              db/     Matter, CalendarEntry, Reminder, SyncState (+ FTS)
              crypto/ Keystore key, AES-GCM store
    sync/     SyncWorker (WorkManager), PairingManager
    notify/   NotificationScheduler (AlarmManager, channels)
    ui/       Today, Calendar, MatterList, MatterDetail, SendReminder,
              Pairing, Settings          -- Compose, Material 3
```

Version is derived from `pyproject.toml` by `scripts/sync_android_version.py`, with a test asserting the two agree. That drift is exactly what produces "the phone says it synced" while the schema has moved.

**Repository hygiene, needed before the first commit of Kotlin:** `.gitignore` already covers `android/app/build/` through its `build/` pattern, but `*.jks`, `*.keystore`, `local.properties` and `.gradle/` must be added. `security_checks/scanner.py` walks the whole repository, does not exclude `android/`, and has no rule that would flag a committed signing keystore — it needs one.

## Distribution

Direct APK, signed with a release keystore that never enters git, handed over at the pairing visit or hosted on the firm's own machine.

**No Play Store means no update channel.** Every update is a manual visit or a file the firm has to install by hand. `GET /device/latest-apk-version` would at least let the app tell the user to come in. This is acceptable for a handful of senior advocates and does not scale beyond that; if the user base grows, the store or an MDM becomes necessary.

## Effort, and what to reconsider first

**Six to ten weeks** for someone who already knows Android, tested across at least three OEMs. Compose, Room, encrypted storage, WorkManager, pairing, offline sync and reliable local notifications are each straightforward and collectively are not.

It is also roughly 60% of the total effort of this whole workstream, for one user.

**Worth one more look before committing: a progressive web app served by the same FastAPI backend on the LAN.** A service worker with IndexedDB genuinely works offline, it is one codebase, it works on an iPhone, and there is no APK, no keystore, no OEM battery fight and no manual update visit. What it gives up is reliable background notifications — the digest would only appear when the user opens it — and stronger at-rest encryption.

The decision taken is native Kotlin, and this specification is written to it. The difference is about two months of work, which is enough that it deserves being asked once more before the first line of Kotlin.

## Status

**This document is the deliverable. No Kotlin has been written.**

The backend half is built and tested: pairing, device tokens with revocation, the restricted capability set, and `/sync/snapshot` — see `tests/validate_device_sync.py`. The contract the app will consume is therefore stable and can be reviewed before anyone commits to the client.

Prerequisites before the build starts, in order:

1. The backend running on a real firm LAN on two machines (`--serve`; `tests/validate_lan_server.py` proves the code path, not a firm's network).
2. `/sync/snapshot` frozen — no field changes once a phone is in the field without an update channel.
3. The native-versus-PWA decision confirmed.
