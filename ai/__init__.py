"""AI provider settings boundary."""

from ai.hosted import (
    HostedAIDecision,
    HostedAIError,
    HostedAIProviderHealth,
    HostedAIRequest,
    HostedAIResult,
    HostedAITransportResponse,
    assert_hosted_prompt_privacy,
    build_hosted_ai_request,
    generate_hosted_ai_answer,
    local_rag_fallback,
    provider_health,
)
from ai.providers import (
    ProviderKeyStatus,
    ProviderSettingsError,
    configured_provider_statuses,
    provider_env_var,
    redact_api_key,
    supported_providers,
)

__all__ = [
    "HostedAIDecision",
    "HostedAIError",
    "HostedAIProviderHealth",
    "HostedAIRequest",
    "HostedAIResult",
    "HostedAITransportResponse",
    "ProviderKeyStatus",
    "ProviderSettingsError",
    "assert_hosted_prompt_privacy",
    "build_hosted_ai_request",
    "configured_provider_statuses",
    "generate_hosted_ai_answer",
    "local_rag_fallback",
    "provider_env_var",
    "provider_health",
    "redact_api_key",
    "supported_providers",
]
