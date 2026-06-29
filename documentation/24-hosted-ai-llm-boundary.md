# 24 - Hosted AI/LLM Boundary

F36 adds the hosted AI boundary after the local vault, intake, RAG, managed cloud backup, and Wakili-Mkononi handoff boundaries are already in place.

This is not an uncontrolled chat feature. Hosted AI may only receive a prompt built from local RAG context and local citation IDs.

## Boundary Rules

- Hosted AI requires explicit user approval.
- Hosted AI requires an enabled `hosted_ai` entitlement.
- Hosted AI requires a configured provider key.
- Hosted AI requires local RAG citations and grounded local context.
- No answer is allowed when local context is missing.
- Every hosted answer must preserve at least one local citation.
- Provider responses containing unknown citation IDs are rejected.
- Provider keys, recovery material, private keys, and cloud credentials are not allowed in prompts or logs.
- If the provider is unavailable or not configured, the app falls back to the local RAG packet and returns no hosted answer.
- Hosted answer generation and local fallback both record local audit events.

## Provider Keys

Provider keys remain local settings. Current provider environment variables are:

- `DOCUMENT_VAULT_OPENAI_API_KEY`
- `DOCUMENT_VAULT_ANTHROPIC_API_KEY`
- `DOCUMENT_VAULT_GOOGLE_API_KEY`
- `DOCUMENT_VAULT_AZURE_OPENAI_API_KEY`
- `DOCUMENT_VAULT_MISTRAL_API_KEY`

Status output is redacted through `python main.py --providers`.

## Prompt Contract

The hosted prompt contains:

- the user question;
- the local cited context produced by the Local Matter RAG Connector;
- citation IDs;
- an instruction to answer only from cited local context.

The hosted prompt must not contain recovery keys, cloud provider credentials, provider API keys, private signing material, or any fallback model-memory path.

## Validation

Run:

```powershell
python tests\validate_hosted_ai_boundary.py
python main.py --hosted-ai-e2e
python tests\validate_ai_providers.py
python tests\validate_rag.py
python tests\validate_security_scan.py
```

The validator proves:

- hosted answer generation succeeds only with local citations;
- confidence is carried forward from local RAG;
- provider key status is redacted;
- provider key values are not included in prompts;
- disabled entitlement blocks hosted AI;
- missing user approval blocks hosted AI;
- missing provider key blocks hosted AI;
- missing local context blocks hosted AI;
- local fallback returns no hosted answer;
- unsafe prompt material is rejected;
- hosted answer and fallback audit events are recorded.
