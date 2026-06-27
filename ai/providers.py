"""Provider API-key configuration with redacted status output."""

from __future__ import annotations

import os
from dataclasses import dataclass

SUPPORTED_PROVIDERS = {
    "openai": "DOCUMENT_VAULT_OPENAI_API_KEY",
    "anthropic": "DOCUMENT_VAULT_ANTHROPIC_API_KEY",
    "google": "DOCUMENT_VAULT_GOOGLE_API_KEY",
    "azure_openai": "DOCUMENT_VAULT_AZURE_OPENAI_API_KEY",
    "mistral": "DOCUMENT_VAULT_MISTRAL_API_KEY",
}


class ProviderSettingsError(Exception):
    """Raised when an unsupported provider key setting is requested."""


@dataclass(frozen=True)
class ProviderKeyStatus:
    provider: str
    env_var: str
    configured: bool
    redacted_value: str

    def to_mapping(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "env_var": self.env_var,
            "configured": self.configured,
            "redacted_value": self.redacted_value,
        }


def supported_providers() -> tuple[str, ...]:
    return tuple(SUPPORTED_PROVIDERS)


def provider_env_var(provider: str) -> str:
    try:
        return SUPPORTED_PROVIDERS[provider]
    except KeyError as exc:
        raise ProviderSettingsError(f"unsupported provider: {provider}") from exc


def configured_provider_statuses(
    environment: dict[str, str] | None = None,
) -> tuple[ProviderKeyStatus, ...]:
    environment = dict(os.environ if environment is None else environment)
    statuses: list[ProviderKeyStatus] = []
    for provider, env_var in SUPPORTED_PROVIDERS.items():
        raw_value = environment.get(env_var, "")
        statuses.append(
            ProviderKeyStatus(
                provider=provider,
                env_var=env_var,
                configured=bool(raw_value),
                redacted_value=redact_api_key(raw_value) if raw_value else "",
            )
        )
    return tuple(statuses)


def redact_api_key(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:3]}...{value[-4:]}"
