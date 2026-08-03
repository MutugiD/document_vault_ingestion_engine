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

The backend should run on a firm-controlled Windows machine or server with a fixed private-network address. The client only needs the backend URL plus an individual username and password. Matter records, filing events, documents, receipts, audit events and offline-cache data remain firm-scoped.

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
- Add a firm backend setup command that binds the service to a private interface, writes a firm URL/configuration file and verifies the vault path.
- Add a connection health indicator and a clear offline/read-only state in the desktop client.
- Add server-side session tracking if the commercial model is concurrent seats rather than provisioned users.
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

This is a local networking boundary test using the FastAPI client. A later acceptance pass should run the same client against a real LAN-bound Uvicorn process on two Windows machines.
