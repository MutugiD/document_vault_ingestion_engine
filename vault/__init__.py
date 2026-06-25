"""Encrypted vault package for local document custody."""

from vault.core import (
    AuditEvent,
    InvalidRecoveryKeyError,
    ObjectNotFoundError,
    StoredObject,
    VaultError,
    VaultPaths,
    VaultSession,
    initialize_vault,
    open_vault,
)

__all__ = [
    "AuditEvent",
    "InvalidRecoveryKeyError",
    "ObjectNotFoundError",
    "StoredObject",
    "VaultError",
    "VaultPaths",
    "VaultSession",
    "initialize_vault",
    "open_vault",
]
