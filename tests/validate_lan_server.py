"""Validate that the firm backend can actually be reached over a network.

``uvicorn`` has been a declared dependency since the first release and was never
imported by anything. Every existing seat test drives Starlette's
``TestClient``, which calls the application in-process and opens no socket -- so
a product sold as multi-seat had never had two processes talk to each other.
This is the first test in the repository that binds a port.

It also guards the decision that matters most here: the bind address defaults to
a private interface and refuses a public one. A laptop bound to every interface
at the office is bound to every interface in a café, and this process serves a
law firm's entire matter database.
"""

from __future__ import annotations

import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from wakilios.client import (  # noqa: E402
    WakiliOSClient,
    WakiliOSClientConfig,
    WakiliOSConnectionError,
)
from wakilios.server import (  # noqa: E402
    CONNECTION_FILENAME,
    FirmServerConfig,
    ServerConfigurationError,
    is_private_address,
    read_connection_file,
    resolve_bind_host,
    resolve_vault_passphrase,
    startup_banner,
    write_connection_file,
)


def check_bind_policy() -> None:
    assert is_private_address("192.168.1.10")
    assert is_private_address("10.0.0.4")
    assert is_private_address("172.16.5.9")
    assert is_private_address("127.0.0.1")
    assert not is_private_address("8.8.8.8")
    assert not is_private_address("41.90.64.1")  # a Kenyan public range
    assert not is_private_address("not-an-address")

    # An explicit host is still checked. "I typed it myself" is not evidence
    # that an address is private, and publishing a firm's vault to a network it
    # does not control cannot be undone afterwards.
    for public in ("8.8.8.8", "0.0.0.0"):
        try:
            resolve_bind_host(public)
        except ServerConfigurationError as exc:
            assert "--allow-public" in str(exc), exc
            assert public in str(exc), exc
        else:
            raise AssertionError(f"{public} was accepted as a bind address by default")

    # ...and can still be chosen deliberately.
    assert resolve_bind_host("0.0.0.0", allow_public=True) == "0.0.0.0"
    assert resolve_bind_host("192.168.4.4") == "192.168.4.4"

    # The default must always be private, whatever this machine's interfaces are.
    assert is_private_address(resolve_bind_host()), resolve_bind_host()


def check_passphrase_policy() -> None:
    """The vault passphrase must never be readable from configuration."""
    import os

    from wakilios.server import VAULT_PASSPHRASE_ENV_VAR

    previous = os.environ.pop(VAULT_PASSPHRASE_ENV_VAR, None)
    try:
        try:
            resolve_vault_passphrase()
        except ServerConfigurationError as exc:
            assert VAULT_PASSPHRASE_ENV_VAR in str(exc), exc
        else:
            raise AssertionError("a missing vault passphrase was tolerated")

        os.environ[VAULT_PASSPHRASE_ENV_VAR] = "from the environment"
        assert resolve_vault_passphrase() == "from the environment"
        assert resolve_vault_passphrase("explicit") == "explicit"
    finally:
        os.environ.pop(VAULT_PASSPHRASE_ENV_VAR, None)
        if previous is not None:
            os.environ[VAULT_PASSPHRASE_ENV_VAR] = previous

    # The config object must have nowhere to persist it. The vault key is
    # derived from this value, so a copy on disk beside the vault would defeat
    # the encryption completely.
    written = write_connection_file(
        FirmServerConfig(
            root=Path("."),
            firm_name="F",
            admin_username="admin",
            admin_password="p",
            vault_passphrase="the secret passphrase",
            host="192.168.1.5",
        ),
        Path(tempfile.mkdtemp()) / CONNECTION_FILENAME,
    )
    body = written.read_text(encoding="utf-8")
    assert "the secret passphrase" not in body, "the connection file leaked the vault passphrase"
    assert "the secret passphrase" not in startup_banner(
        FirmServerConfig(
            root=Path("."),
            firm_name="F",
            admin_username="admin",
            admin_password="p",
            vault_passphrase="the secret passphrase",
            host="192.168.1.5",
        )
    )

    published = read_connection_file(written)
    assert published["base_url"] == "http://192.168.1.5:8765", published
    # A seat operator has to be told the transport is not encrypted, in the file
    # they are handed, not only in a document nobody opens.
    assert "encrypt" in published["transport_note"].lower(), published


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def check_real_socket() -> None:
    """Drive a running server with the real client over a real socket."""
    import uvicorn

    from wakilios.server import build_app

    with tempfile.TemporaryDirectory() as temp_dir:
        port = free_port()
        config = FirmServerConfig(
            root=Path(temp_dir) / "firm",
            firm_name="LAN Test Firm",
            admin_username="admin",
            admin_password="admin-pass",
            vault_passphrase="lan vault passphrase",
            host="127.0.0.1",
            port=port,
        )
        server = uvicorn.Server(
            uvicorn.Config(build_app(config), host=config.host, port=port, log_level="error")
        )
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        try:
            client = WakiliOSClient(WakiliOSClientConfig(base_url=config.base_url()))

            # Bounded retry rather than a fixed sleep: a fixed sleep is either
            # slow or flaky on a shared CI runner, and eventually both.
            deadline = time.monotonic() + 30
            health = None
            while time.monotonic() < deadline:
                try:
                    health = client.health()
                    break
                except (WakiliOSConnectionError, OSError):
                    time.sleep(0.1)
            assert health is not None, "the server never became reachable on its socket"
            assert health.get("status") == "ok", health

            session = client.login("admin", "admin-pass")
            assert session["token"], session
            assert session["role"] == "admin", session

            # A real request with a real body over a real connection.
            matter = client.create_matter(
                internal_reference="MTR-LAN-1",
                client_name="Kiunga Holdings",
                parties="Kiunga v Republic",
                court="High Court",
                station="Meru",
                case_number="HCCC/E9/2026",
                practice_area="Commercial",
                responsible_advocate="A. Advocate",
                filing_status="filed",
                filing_date="2026-08-01",
            )
            assert matter["internal_reference"] == "MTR-LAN-1", matter

            client.add_activity(
                matter["matter_id"],
                activity_type="Mention",
                title="Mention before the Deputy Registrar",
                starts_at="2026-08-06T09:00:00",
            )
            entries = client.upcoming("2026-08-06", "2026-08-07")
            assert len(entries) == 1, entries
            assert entries[0]["kind"] == "hearing", entries

            assert len(client.list_matters()) == 1

            # An unauthenticated client must be refused over the wire, not only
            # in-process where the dependency is easy to satisfy.
            anonymous = WakiliOSClient(WakiliOSClientConfig(base_url=config.base_url()))
            try:
                anonymous.list_matters()
            except Exception as exc:  # WakiliOSClientError
                assert "401" in str(exc) or getattr(exc, "status_code", 0) == 401, exc
            else:
                raise AssertionError("an unauthenticated request was served")
        finally:
            server.should_exit = True
            thread.join(timeout=15)


def check_banner() -> None:
    banner = startup_banner(
        FirmServerConfig(
            root=Path("/vault"),
            firm_name="Kiunga & Co Advocates",
            admin_username="admin",
            admin_password="p",
            vault_passphrase="x",
            host="192.168.1.5",
            port=8765,
        )
    )
    assert "192.168.1.5:8765" in banner
    assert "NOT ENCRYPTED" in banner, "the operator must be told the transport is in the clear"
    # Windows Firewall silently blocks the port on a fresh machine, and the firm
    # concludes the product is broken. The fix belongs where they will see it.
    assert "netsh advfirewall" in banner, banner
    assert "8765" in banner


def main() -> None:
    check_bind_policy()
    check_passphrase_policy()
    check_banner()
    check_real_socket()
    print("LAN SERVER VALIDATION PASS")


if __name__ == "__main__":
    main()
