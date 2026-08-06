# JurisNuru runs without an LLM

## The commitment

**A firm running JurisNuru pays no LLM subscription, and no matter data leaves the firm to answer a question about it.** There is no per-query cost, no provider account to open, and no API key in the shipped product.

This is not a plan. It is how the product is built, and as of this release it is enforced by a test rather than asserted in a document.

## What the "AI" in JurisNuru actually is

Two features carry the label. Neither generates prose.

### Matter search and the AI context panel — retrieval only

`rag/core.py` splits a document into 90-word chunks with a 20-word overlap, scores them against the question, and returns the passages that matched, with citations.

Scoring combines sparse term overlap with a 64-dimension vector built by the hashing trick (`_hashed_vector`, `VECTOR_DIMENSIONS = 64`) — a hash of each token folded into a fixed-width vector. There is no model, no weights file and no inference.

`build_answer_packet` returns a `RagAnswerPacket`:

```
question, grounded_context, citations, retrieval_results, safety_notice, confidence
```

**There is no `answer` field.** Nothing composes one. This is the architectural reason no LLM is required rather than merely not used: the panel shows you the passages from your own documents that bear on your question, numbered so you can check each one, and a lawyer reads them. `tests/validate_no_llm_egress.py` asserts the field's absence, because an `answer` field appearing is precisely where an LLM would enter.

### Matter summaries — deterministic composition

"Draft summary" (`_draft_matter_summary` in `ui/app.py`) reads what the firm has already recorded — parties, court, case number, counts of documents and activities, fees against receipts, the latest decision, the filing record, the next action — and writes it into sentences. Given the same matter it produces the same summary, every time. It ends with a line saying it was drafted from the record and must be verified.

`generate_ai_summary` in `wakilios/core.py` composes from retrieved passages by the same principle, and records the citation ids it drew on.

## `ai/hosted.py` — what it is, and what it is not

There is one module named for hosted AI, and it is a **boundary**, not a client.

- It contains **no network code at all**. Its transport is an injected callable — `HostedAITransport = Callable[[HostedAIRequest], HostedAITransportResponse]` — so a caller must supply the means of talking to anything. Nothing in the shipped product supplies one.
- It carries **no provider endpoint, no SDK and no key**. The test asserts that no provider hostname or credential prefix appears in the file.
- It is gated **twice**: `HostedAIDecision.require_allowed()` needs the licence to include `hosted_ai` *and* the user to have approved it. Either alone is refused.
- The `hosted_ai` entitlement is enforced in the UI through `ENTITLEMENT_CONTROLS`, so a licence without it disables the control and says why.

It exists so that a firm which one day asks for a hosted model has a reviewed, consented, entitlement-gated path to it — instead of someone adding an API call to `rag/core.py`. Its presence is the reason that will not happen quietly.

## How the guarantee is enforced

`tests/validate_no_llm_egress.py`, in CI.

**Static.** An AST walk over `rag/`, `search/`, `vault/`, `intake/`, `backup/` and `core/manual_app.py` — 15 modules — rejects any import of a provider client (`openai`, `anthropic`, `google.generativeai`, `transformers`, `ollama`, …) or a network module (`urllib.request`, `requests`, `httpx`, `socket`, …).

**Dynamic — the part that actually proves it.** `socket.socket.connect` and `socket.create_connection` are replaced with functions that raise. The real path then runs end to end: build a vault, index a judgment, ask a question, generate a summary. Anything that reaches the network fails with a stack trace naming the caller.

This survives what a grep does not: indirection, a transitive import, a helper added three modules away. The test also proves its own trap is armed before trusting what it does not catch — it attempts a connection and requires the refusal — so a typo in the patching cannot leave it silently passing forever.

The only `urlopen` anywhere in shipped code is `wakilios/client.py`, which talks to the firm's own backend on the firm's own network.

## The trade-off, stated

**Retrieval quality is below what an embedding model would give.** The hashing trick is a cheap approximation of semantic similarity: it matches on tokens and their hashed co-occurrence, not on meaning. A question phrased differently from the document it should match will score lower than it deserves. `evidence.md` records retrieval confidences of 0.49–0.69 on real Kenyan judgments — usable, and not what a modern embedding model produces.

"No LLM" is a cost win, a custody win, and a quality cost. All three are real, and a firm choosing this product should know all three.

**The upgrade path keeps the promise.** If retrieval quality becomes the binding complaint, the answer is a small local embedding model — a quantised ONNX sentence encoder of roughly 90 MB, running on the firm's own machine. That would improve matching substantially while adding no subscription, no API key and no data leaving the firm. It would enlarge the bundle and add CPU cost per index, which is the trade to weigh at that point.

Generation is a separate question and a harder one. Local generation good enough for legal drafting needs several gigabytes of weights and is slow on the office laptops this product targets. The current position — retrieve, cite, and let a lawyer write — is the honest one for the hardware, independent of cost.

## Summary

| | |
|---|---|
| Per-firm LLM subscription | none |
| API keys in the product | none |
| Matter data sent to a third party to answer a question | none |
| Model weights bundled | none |
| Enforced by | `tests/validate_no_llm_egress.py`, in CI |
| Retrieval method | 90-word chunks, sparse terms + 64-dim hashing trick |
| Summaries | deterministic composition from the firm's own record |
| Known limitation | retrieval quality below an embedding model |
