"""WakiliOS multi-seat legal firm management package."""

from wakilios.core import (
    ACCOUNTS_ROLE,
    ADMIN_ROLE,
    ADVOCATE_ROLE,
    CLERK_ROLE,
    READ_ONLY_ROLE,
    AuthSession,
    OfflineCache,
    PermissionDeniedError,
    SeatLimitError,
    WakiliOSBackend,
    WakiliOSError,
    initialize_firm_backend,
)

__all__ = [
    "ACCOUNTS_ROLE",
    "ADMIN_ROLE",
    "ADVOCATE_ROLE",
    "AuthSession",
    "CLERK_ROLE",
    "OfflineCache",
    "PermissionDeniedError",
    "READ_ONLY_ROLE",
    "SeatLimitError",
    "WakiliOSError",
    "WakiliOSBackend",
    "WakiliOSClient",
    "WakiliOSClientConfig",
    "WakiliOSClientError",
    "WakiliOSConnectionError",
    "initialize_firm_backend",
]

from wakilios.client import WakiliOSClient, WakiliOSClientConfig, WakiliOSClientError, WakiliOSConnectionError