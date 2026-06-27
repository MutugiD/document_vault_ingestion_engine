"""Release bundle helpers for Windows distribution."""

from .bundle import (
    APP_NAME,
    ReleaseBundle,
    ReleaseBundleError,
    ReleaseManifest,
    create_release_bundle,
    validate_release_bundle,
)
from .install_smoke import PortableInstallResult, run_portable_install_smoke
from .publishing import (
    INSTALLER_MANIFEST_NAME,
    InstallerManifest,
    InstallerShortcut,
    PublishingManifestError,
    create_installer_manifest,
    load_installer_manifest,
    validate_installer_manifest,
)
from .updates import (
    UPDATE_AVAILABLE,
    UPDATE_CURRENT,
    UPDATE_OFFLINE,
    UPDATE_UNSUPPORTED_PLATFORM,
    UpdateArtifact,
    UpdateCheckResult,
    UpdateManifest,
    UpdateManifestError,
    canonical_update_manifest_bytes,
    check_for_update,
    update_manifest_from_mapping,
    verify_update_manifest,
)

__all__ = [
    "APP_NAME",
    "INSTALLER_MANIFEST_NAME",
    "InstallerManifest",
    "InstallerShortcut",
    "PortableInstallResult",
    "PublishingManifestError",
    "ReleaseBundle",
    "ReleaseBundleError",
    "ReleaseManifest",
    "UPDATE_AVAILABLE",
    "UPDATE_CURRENT",
    "UPDATE_OFFLINE",
    "UPDATE_UNSUPPORTED_PLATFORM",
    "UpdateArtifact",
    "UpdateCheckResult",
    "UpdateManifest",
    "UpdateManifestError",
    "canonical_update_manifest_bytes",
    "check_for_update",
    "create_release_bundle",
    "create_installer_manifest",
    "load_installer_manifest",
    "run_portable_install_smoke",
    "update_manifest_from_mapping",
    "validate_installer_manifest",
    "validate_release_bundle",
    "verify_update_manifest",
]
