# 25 - Hosted AI UI Workflow

F37 exposes the hosted AI boundary through the desktop workflow after F36 proved the local prompt and provider boundary.

The UI remains conservative: it does not call a production provider directly in validation. It uses the same local boundary contract and deterministic offline transport used by the manual app session so the workflow can be tested without leaking keys or legal text.

## User Flow

1. User imports documents into the matter workspace.
2. User saves provider keys in the AI Keys tab.
3. User asks a local RAG question in the Search and RAG tab.
4. User clicks `Hosted answer`.
5. The app builds a hosted AI request only if local RAG citations exist.
6. The app displays status, provider, confidence, citation count, fallback state, answer, and elapsed time.

## Safety Rules

- Provider keys are accepted through local UI fields and then cleared.
- Provider key status is displayed only as configured provider names.
- The hosted answer UI must not display raw provider keys.
- If local context is missing, the UI shows local fallback rather than a hosted answer.
- The manual app session and the UI use the same hosted AI boundary.
- Hosted answer and fallback audit events are still recorded in the local vault.

## Validation

Run:

```powershell
python tests\validate_hosted_ai_ui_workflow.py
python tests\validate_ui.py
python tests\validate_hosted_ai_boundary.py
python tests\validate_ai_providers.py
```

The validator proves:

- a real imported PDF can produce a hosted answer through the manual session;
- the hosted answer carries citations and confidence;
- provider keys are not exposed in summaries or UI output;
- the desktop button exists and runs;
- no-context UI flow falls back locally.
