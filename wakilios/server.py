"""Serve the firm backend on the firm's own network.

``uvicorn`` has been a declared dependency since the beginning and was never
imported anywhere. Firm mode has therefore never run over a real network: every
seat test drives Starlette's in-process ``TestClient``, which opens no socket.
The product sells multi-seat and has only ever been proven single-process.

Two decisions here are deliberate and worth reading before changing them.

**The bind address defaults to a private interface, never ``0.0.0.0``.** A
laptop bound to every interface at the office is still bound to every interface
in a café, and this process serves a law firm's entire matter database. Binding
broadly has to be an explicit, argued choice, so it takes a flag whose name says
what it does.

**Transport is plain HTTP on the LAN, and says so.** No certificate authority
will issue for ``192.168.x.x``, so ordinary TLS is not available. A self-signed
certificate is possible but costs a pinned trust store on every client and a
rotation procedure nobody executes; it is worth doing, and it is not worth doing
badly. What is never acceptable is HTTPS with verification disabled -- that is
strictly worse than plain HTTP, because it reads as safe. Until pinning exists,
the honest position is: the transport is unencrypted, an attacker already on the
firm network can read matter data in flight, the vault at rest stays AES-GCM
encrypted, and the application says this out loud rather than implying otherwise.
"""

from __future__ import annotations

import ipaddress
import json
import os
import socket
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PORT = 8765
VAULT_PASSPHRASE_ENV_VAR = "JURISNURU_VAULT_PASSPHRASE"
CONNECTION_FILENAME = "firm-connection.json"


class ServerConfigurationError(Exception):
    """Raised when the server cannot start safely."""


@dataclass(frozen=True)
class FirmServerConfig:
    """Everything needed to serve one firm's backend."""

    root: Path
    firm_name: str
    admin_username: str
    admin_password: str
    vault_passphrase: str
    host: str
    port: int = DEFAULT_PORT
    max_seats: int = 5

    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


WILDCARD_HOSTS = frozenset({"0.0.0.0", "::", "*", ""})
"""Bind addresses meaning "every interface".

``ipaddress`` calls ``0.0.0.0`` private, because ``0.0.0.0/8`` is the "this
network" block. As a *bind* address it means the opposite: listen on everything,
including whatever network the laptop joins next. That is precisely the case
this module exists to prevent, so wildcards are excluded by name rather than by
classification.
"""


def is_private_address(host: str) -> bool:
    """Whether it is safe to bind here without an explicit override.

    Loopback counts: a backend on 127.0.0.1 is reachable only from the machine
    it runs on, which is the safest position of all.
    """
    if host in WILDCARD_HOSTS:
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return bool(address.is_private or address.is_loopback or address.is_link_local)


def candidate_addresses() -> list[str]:
    """Every IPv4 address this machine answers on."""
    addresses: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, family=socket.AF_INET):
            address = str(info[4][0])
            if address not in addresses:
                addresses.append(address)
    except OSError:
        pass
    return addresses


def resolve_bind_host(requested: str = "", *, allow_public: bool = False) -> str:
    """Choose the interface to listen on, refusing a public one by default.

    Passing an explicit host still goes through the check. "I typed it myself"
    is not evidence that an address is private, and the failure being guarded
    against -- publishing a firm's vault to a network it does not control -- is
    not recoverable once it has happened.
    """
    if requested:
        if not allow_public and not is_private_address(requested):
            raise ServerConfigurationError(
                f"{requested} is not a private address. Serving a firm vault on a "
                f"public interface exposes every matter to that network. Pass "
                f"--allow-public only if that is genuinely intended."
            )
        return requested

    for address in candidate_addresses():
        if is_private_address(address) and not ipaddress.ip_address(address).is_loopback:
            return address

    # No private interface found. Loopback still serves this machine, which is
    # a working single-seat setup, rather than failing to start at all.
    return "127.0.0.1"


def resolve_vault_passphrase(explicit: str = "") -> str:
    """Read the vault passphrase from the environment, never from a file.

    The vault key is derived from this (``vault/core.py``), so a passphrase
    stored on disk beside the vault is equivalent to no encryption at all. It
    is therefore not a config field, and there is nowhere in
    :class:`FirmServerConfig` for it to be persisted.
    """
    passphrase = explicit or os.environ.get(VAULT_PASSPHRASE_ENV_VAR, "")
    if not passphrase:
        raise ServerConfigurationError(
            f"no vault passphrase. Set {VAULT_PASSPHRASE_ENV_VAR}. It is never read "
            f"from a configuration file: the vault key is derived from it, so a copy "
            f"beside the vault would defeat the encryption entirely."
        )
    return passphrase


def write_connection_file(config: FirmServerConfig, destination: Path) -> Path:
    """Write what a seat needs to connect, so nobody types a URL.

    Copied to each laptop, this removes the step where a clerk mistypes an
    address into the connection dialog and reports the product as broken.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(
            {
                "base_url": config.base_url(),
                "firm_name": config.firm_name,
                "transport": "http",
                "transport_note": (
                    "Unencrypted on the local network. Anyone already on this "
                    "network can read matter data in transit. The vault at rest "
                    "remains encrypted."
                ),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return destination


def read_connection_file(path: Path) -> dict[str, str]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {str(key): str(value) for key, value in raw.items()} if isinstance(raw, dict) else {}


def build_app(config: FirmServerConfig):
    """Construct the ASGI application for this firm."""
    from wakilios.api import create_app

    return create_app(
        root=config.root,
        firm_name=config.firm_name,
        admin_username=config.admin_username,
        admin_password=config.admin_password,
        vault_passphrase=config.vault_passphrase,
        max_seats=config.max_seats,
    )


def startup_banner(config: FirmServerConfig) -> str:
    """What the operator sees. The transport warning is not a footnote."""
    return "\n".join(
        [
            f"JurisNuru firm backend for {config.firm_name}",
            f"  listening on   {config.base_url()}",
            f"  vault          {config.root}",
            f"  seats          {config.max_seats}",
            "",
            "  TRANSPORT IS NOT ENCRYPTED. Anyone already on this network can read",
            "  matter data in transit. The vault on disk remains encrypted.",
            "  Serve only on a network the firm controls.",
            "",
            "  If seats cannot connect, Windows Firewall is the usual cause:",
            f'    netsh advfirewall firewall add rule name="JurisNuru" dir=in '
            f"action=allow protocol=TCP localport={config.port}",
        ]
    )


def serve(config: FirmServerConfig) -> int:
    """Run the backend until interrupted."""
    import uvicorn

    print(startup_banner(config), flush=True)
    write_connection_file(config, config.root / CONNECTION_FILENAME)
    uvicorn.run(build_app(config), host=config.host, port=config.port, log_level="info")
    return 0
