# JurisNuru seats and networking

## Current model

JurisNuru supports two local operating modes:

1. **Solo mode**: one laptop owns a local vault and uses one allocated seat.
2. **Firm mode**: one firm backend owns the SQLite metadata store and encrypted vault; each laptop runs the desktop client and connects over HTTP to that backend.

For a five-laptop firm, the intended layout is:

```text
Laptop 1 ─┐
Laptop 2 ─┤
Laptop 3 ─┼── firm backend / encrypted vault / shared matter database
Laptop 4 ─┤
Laptop 5 ─┘
```

The backend runs on a firm-controlled Windows machine with a fixed private-network address. The client only needs the backend URL plus an individual username and password. Matter records, filing events, documents, receipts, audit events and offline-cache data remain firm-scoped.

## Serving the backend

```
set JURISNURU_VAULT_PASSPHRASE=<the firm vault passphrase>
DocumentVaultIngestionEngine.exe --serve --firm-root D:\JurisNuru\firm ^
    --firm-name "Kiunga & Co Advocates" --admin-password <initial password> --max-seats 5
```

`--serve` prints the URL other seats should use and writes `firm-connection.json` into the firm root. Copy that file to each laptop rather than having anyone retype an address.

**Binding.** With no `--serve-host`, the service selects this machine's private-network address. A non-private address — including `0.0.0.0`, which means *every* interface — is refused unless `--allow-public` is passed. This is not caution for its own sake: a laptop bound to every interface at the office is bound to every interface on the next network it joins, and this process serves the firm's entire matter database.

**The vault passphrase is read from `JURISNURU_VAULT_PASSPHRASE` only, never from a configuration file.** The vault encryption key is derived from it, so a copy stored beside the vault would defeat the encryption entirely. There is deliberately no config field for it.

**Windows Firewall is the usual reason seats cannot connect.** A fresh Windows machine silently blocks the inbound port, and the firm concludes the product is broken. Allow it once:

```
netsh advfirewall firewall add rule name="JurisNuru" dir=in action=allow protocol=TCP localport=8765
```

## Transport security — stated plainly

**Traffic between a seat and the backend is not encrypted.** Anyone already on the firm's network can read matter data in transit. The vault on disk remains AES-GCM encrypted, and authentication still requires a valid token, but the transport itself is HTTP.

This is a deliberate position, not an oversight:

- No certificate authority will issue a certificate for a private address such as `192.168.1.5`, so ordinary TLS is not available on a LAN.
- A self-signed certificate is workable but only if every client pins it and someone rotates it. Half of that is worse than none.
- HTTPS with certificate verification disabled is **strictly worse than plain HTTP**, because it reads as safe while providing nothing. It will not be shipped.

Serve only on a network the firm controls. Pinned self-signed certificates are the intended next step, generated on first `--serve` and distributed through the same `firm-connection.json`.

## Seat behaviour currently implemented

- The administrator is the first allocated seat.
- `max_seats=1` supports a one-user firm and rejects a second user.
- `max_seats=5` supports the administrator plus four additional users.
- All five users can authenticate against the same backend and see the same matter list.
- Role permissions are enforced server-side; the client UI is not the security boundary.
- The API returns HTTP `409` when the firm seat limit is reached.
- A read-only offline cache can be built for a connected user.

The seat count currently represents **provisioned active firm users**, not a concurrent-login counter. One user may reconnect from another laptop using the same credentials. That is acceptable for the current pilot build but should be made explicit in commercial provisioning.

## Recommended next build steps

- Add an administrator-only Users and Seats screen showing allocated seats, roles, active/inactive state and last login.
- Add user deactivation and seat reassignment rather than deleting historical users.
- Add server-side session tracking if the commercial model is concurrent seats rather than provisioned users.
- Add pinned self-signed TLS, generated on first `--serve` and distributed through `firm-connection.json`.
- Add per-username backoff on `/auth/login`. PBKDF2 at 210,000 iterations limits brute force but makes roughly ten concurrent attempts enough to saturate a CPU.
- Keep backups on a separate protected location from the live backend machine.
- For a single-user firm, default to solo mode unless the user needs shared access or central backup.

## Tests run

`tests/validate_seat_networking.py` exercises the HTTP boundary for:

- one-seat firm rejection;
- five users on one shared backend;
- shared matter visibility across all five users;
- document upload through the shared backend;
- sixth-seat rejection;
- role and API validation.

This is an in-process boundary test using the FastAPI client, which opens no socket.

`tests/validate_lan_server.py` is the first test in the repository that binds a port. It starts a real Uvicorn server and drives it with the real `WakiliOSClient` over a real connection: health, login, matter creation, the cross-matter calendar query, and a 401 for an unauthenticated request. It also asserts the bind policy — that a public address and `0.0.0.0` are both refused without `--allow-public` — and that neither the connection file nor the startup banner leaks the vault passphrase.

**Still outstanding:** an acceptance pass on two physical Windows machines. One process binding a port on a CI runner proves the code path; it does not prove a firm's network, Windows Firewall configuration, or a second laptop.
