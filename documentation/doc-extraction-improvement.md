# Improving document extraction and OCR accuracy in JurisNuru

## 0. Why this document exists

JurisNuru's value proposition is that a firm can find, trust and reuse its own
record. Everything downstream — search, RAG citations, the filing record, the
AI context panel — is only as good as the text pulled out of a PDF. Today that
text comes from a single unconditional path with no quality measurement.

This maps what the extraction pipeline actually does, contrasts it with the
architecture in [MutugiD/production-ocr-course](https://github.com/MutugiD/production-ocr-course),
and proposes a staged plan that is honest about what a local-first desktop
product can and cannot adopt.

Assessed against `main` at the commit adding this document. Every claim about
current behaviour cites a file and was verified, not inferred from the README.

---

## 1. What the pipeline does today

The whole extraction path is `intake/extraction.py`, ~200 lines.

```
detect_file_type()                        intake/core.py
   ├── pdf   → fitz.open(); page.get_text("text") for every page
   │            └── if the WHOLE document has no text → rasterise → Tesseract
   ├── docx  → python-docx paragraph concatenation
   └── image → Tesseract directly
                                          → ExtractionResult(text, page_count,
                                                             ocr_status, warnings)
```

Then `rag/core.py` chunks that flat text at **90 words with 20 words of
overlap** (`DEFAULT_CHUNK_WORDS`, `DEFAULT_CHUNK_OVERLAP`) and indexes it with a
**hashing-trick vector** (`_hashed_vector`) plus a sparse term score — not
learned embeddings.

### 1.1 Five defects, each verified

**(a) Docling is documented as mandatory and is never called.**
`README.md:29` states "Mandatory Docling document understanding after native
PDF/DOCX inspection". `docling==2.41.0` is a pinned runtime dependency,
`release/bundle.py:233` verifies a bundled `runtime/docling` model directory,
and `README.md:73` tells you to run `tests\validate_docling_runtime.py`.

`grep -rn "import docling\|from docling" intake/ core/ search/ rag/ vault/`
returns **nothing**, and `validate_docling_runtime.py` does not exist. The
product ships and bundles a document-understanding engine it never invokes.
This is the single largest gap between the documented and actual pipeline.

**(b) OCR only fires when the entire document has no text.**

```python
# intake/extraction.py:84
if not any(part.strip() for part in page_text) and ocr_engine is not None:
```

A filing with 49 typed pleading pages and one scanned exhibit gets **zero OCR
on that exhibit**, silently, with `ocr_status = not_required`. For Kenyan
judiciary work — typed pleadings with scanned annexures, stamped receipts and
signed affidavits attached — this is the *common* document shape, not an edge
case. The scanned content is simply absent from search and RAG, and nothing
reports that it is missing.

**(c) Rasterisation is at roughly 144 DPI.**

```python
# intake/extraction.py:152
page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
```

PDF user space is 72 DPI, so `Matrix(2, 2)` yields ~144 DPI. Tesseract's
accuracy degrades sharply below ~300 DPI for body text and worse for the small
type used in court stamps and receipt footers. This is a one-line change with
a large accuracy effect.

**(d) No image preprocessing at all.** No deskew, no denoise, no contrast
normalisation, no binarisation. Phone photographs of filings — which is how a
lot of Kenyan practice actually captures documents — arrive skewed and unevenly
lit, and go to Tesseract untouched.

**(e) Layout is discarded.** `page.get_text("text")` returns a flat stream in
PDF content order. Multi-column pleadings interleave. Tables — the fee and
receipt tables that matter most for the filing record — lose their row/column
structure and become unparseable runs of numbers. Reading order across
headers, footnotes and marginalia is not recovered.

### 1.2 What is already good

- The **adapter boundary is clean.** `OcrEngine` is a `Protocol`; extraction
  takes an injectable engine. A different engine can be dropped in without
  touching call sites.
- `ExtractionResult` already carries `ocr_status` and `warnings`, so there is
  somewhere to put quality signals.
- The intake quarantine, hashing and duplicate detection around it are solid.

---

## 2. What the OCR course does differently

The course builds a **two-stage, layout-first Visual Document Understanding
pipeline**, not a text-extraction pipeline:

| Stage | Component | Purpose |
|---|---|---|
| Ingest | Rust/Axum gateway → Redis | High-concurrency upload, decoupled from GPU |
| Layout | PP-DocLayoutV3 via GLM-OCR SDK | Delimit text / table / figure / formula regions **before** recognition |
| Recognise | Qwen 3.5 (4B) on vLLM | Generative recognition per region, with continuous batching and MTP |
| Handoff | `/dev/shm` zero-copy | Share high-res buffers without disk I/O |
| Scale | KEDA over T4 + A100 pools | Scale layout and inference independently, to zero |

**The idea worth stealing is the first stage, not the infrastructure.** The
course's own justification:

> The layout detector acts as a pre-input encoder that delimits semantic
> regions and their orientation before generative inference. This narrows the
> VLM's decision space and reduces visual noise (skew/warp/lighting),
> mitigating hallucinations typical of generative models.

That reasoning applies just as strongly to Tesseract as to a VLM. Tesseract
given a clean, deskewed, single-column crop of a known region type is
dramatically more accurate than Tesseract given a whole warped page. **You get
most of the accuracy win from layout-first processing without any GPU.**

### 2.1 What does *not* transfer

Be clear-eyed about this, because adopting it wholesale would break the
product:

- **JurisNuru is local-first and offline by design.** The vault is encrypted on
  the firm's own machine; `documentation/09-*` and the brief both make custody
  a core promise. A pipeline that ships every page to a GPU cluster inverts
  that promise.
- **A100/T4 node pools are not a fit** for a firm running five Windows laptops.
- **Generative OCR hallucinates.** For a legal record that must be citable,
  a model that can silently invent a figure in a fee table is a liability that
  deterministic OCR does not carry. If a VLM is ever used, its output needs to
  be treated as a *suggestion requiring review*, exactly like
  `document_summaries.approval_status` already models.

---

## 3. Recommended plan

Ordered by accuracy gained per unit of risk. Stages 1–3 are local-only and
change no architectural promise.

### Stage 1 — Stop losing text (highest value, lowest risk)

**1.1 Make OCR per-page, not per-document.**
Replace the all-or-nothing condition with a per-page decision: a page whose
extracted text is below a character threshold relative to its area is a
candidate for OCR. Track per-page status so a partially-OCR'd document is
visible as such.

Suggested shape, keeping the existing dataclass style:

```python
@dataclass(frozen=True)
class PageExtraction:
    page_number: int
    text: str
    source: str          # "native" | "ocr"
    ocr_confidence: float | None
```

`ExtractionResult` gains `pages: tuple[PageExtraction, ...]`, and `ocr_status`
becomes a summary over them rather than the only signal.

**1.2 Raise rasterisation to 300 DPI.**
`fitz.Matrix(300/72, 300/72)` instead of `Matrix(2, 2)`. Memory cost is
bounded by processing one page at a time, which the code already does.

**1.3 Capture Tesseract confidence.**
Use `image_to_data` (TSV) rather than plain `image_to_string`, and keep mean
word confidence per page. Without this there is no way to answer "is this
extraction any good?", which every later stage depends on.

**1.4 Surface low confidence in the review queue.**
`documentReviewQueue` already exists in the Documents destination. A page below
a confidence floor should land there for human review rather than flowing
silently into the vault and RAG index.

*Verification:* extend `tests/validate_intake.py` with a mixed PDF — typed
pages plus a scanned page — and assert the scanned page's text is present and
its `source` is `"ocr"`. That test fails against today's code, which is the
point.

### Stage 2 — Preprocess before recognition

Deskew (Hough or projection profile), denoise, and adaptive binarisation
(Sauvola suits uneven lighting better than Otsu) before Tesseract. OpenCV is
the obvious dependency but adds ~60 MB to the bundle; `scikit-image` or a small
hand-rolled deskew over NumPy may be the better trade for a desktop installer.

Measure before committing to the dependency: run the corpus in
`test-output/judiciary-ui-corpus` through both paths and compare mean
confidence. **Do not add 60 MB on faith.**

### Stage 3 — Actually use Docling (layout-first, no GPU)

This is the course's core insight, available locally. Docling is *already a
pinned dependency and already bundled* — it costs nothing in distribution
weight to start calling it.

Use it as the pre-layout encoder:

1. Docling produces a structured document: reading order, tables as tables,
   figures identified.
2. Native text is taken per region where the region has extractable text.
3. Only regions without text — scanned exhibits, stamps — go to Tesseract, as
   tight deskewed crops rather than whole pages.
4. Tables are preserved as structured rows rather than flattened.

The payoff is concentrated exactly where JurisNuru needs it: the **fee and
receipt tables** that the filing record reconciles against. Today those become
an unstructured run of numbers; with layout-aware extraction they can populate
`fee_entries.amount`, `fee_entries.prn` and `receipts.receipt_number` directly
instead of being retyped.

Either do this or correct `README.md` and `release/bundle.py` to stop claiming
and bundling an engine that is never called. The current state — shipping the
models, verifying them at release, documenting them as mandatory, never
invoking them — is the worst of both.

### Stage 4 — Improve retrieval, which extraction quality feeds

Two weaknesses compound the extraction problems:

- **90-word chunks with 20-word overlap** will split a judgment's holding from
  its reasoning. Chunk on layout boundaries once Stage 3 lands, rather than a
  fixed word count.
- **`_hashed_vector` is the hashing trick, not embeddings.** It cannot match
  "limitation period" to "time-barred". A small local sentence-transformer
  (~90 MB, CPU-viable) would materially improve recall. This is the difference
  between the brief's "find by meaning and context, not just filename"
  (slide 3) and what currently ships.

### Stage 5 — Optional hosted VLM, behind the existing boundary

Only if Stages 1–3 prove insufficient on real documents. If adopted:

- Route it through the existing `ai/hosted.py` boundary, which already enforces
  prompt privacy assertions and audit events.
- Gate it on the `hosted_ai` entitlement — noting that entitlements are
  currently parsed and never enforced (see
  [25-jurisnuru-gap-analysis.md](25-jurisnuru-gap-analysis.md) §3.2), so that
  enforcement has to exist first.
- Treat output as requiring review, never as a citable extraction.
- It must remain **opt-in per matter**. A firm that chose a local-first vault
  did not consent to its clients' documents leaving the machine.

---

## 4. Sequencing and expected effect

| Stage | Effort | Risk | Expected effect |
|---|---|---|---|
| 1. Per-page OCR, 300 DPI, confidence | Small | Low | Eliminates silent text loss on mixed documents — the largest correctness bug |
| 2. Preprocessing | Medium | Low, gated on measurement | Materially better OCR on photographed and skewed filings |
| 3. Docling layout-first | Medium-large | Medium | Tables and reading order preserved; fee/receipt capture becomes possible |
| 4. Layout chunking + embeddings | Medium | Low | Search and RAG that match meaning rather than words |
| 5. Hosted VLM | Large | High (privacy, hallucination) | Only if 1–3 prove insufficient |

**Start with Stage 1.** It is a few days of work, it fixes a correctness bug
rather than tuning a quality metric, and every later stage depends on the
confidence signal it introduces.

---

## 5. Measure before and after

There is currently no extraction accuracy measurement anywhere in the
repository. Before changing anything, establish a baseline, or none of the
above can be justified.

- **Corpus**: the 29 documents already in `test-output/judiciary-ui-corpus`,
  plus deliberately hard cases — a photographed filing, a stamped receipt, a
  multi-column judgment, a fee table.
- **Ground truth**: hand-transcribe a representative subset. Tedious and
  unavoidable.
- **Metrics**: character error rate; word error rate; table cell F1; and a
  retrieval metric (does a known-answer question return the correct citation?).
- **Harness**: `tests/validate_extraction_accuracy.py`, run manually rather
  than in CI — it needs the corpus and takes minutes.

### 5.1 Baseline as measured

`tests/validate_extraction_accuracy.py` now exists and has been run. Numbers
below are from that run, not estimates.

| Measure | Result |
|---|---|
| Mean character error rate | **0.078** |
| Mean word error rate | **0.070** |
| Number recall (money, PRNs, case references) | **98.7%** |
| Synthetic pages, exact ground truth | **CER 0.000** |
| Matter-detail fields, exact match | **7/7** |

Read them with their limits in mind:

- **Ground truth is not hand-transcribed.** It is text this repository owns
  (rendered, then flattened to an image) and the born-digital text layer of real
  judgments. Both are clean typeset text. A genuinely scanned Kenyan filing --
  photographed, skewed, stamped -- is *not* represented, and is where accuracy
  will be worst.
- **Number recall matters more than CER here.** A fee table with one wrong digit
  is worse than a paragraph with several wrong letters. 98.7% recall means
  roughly one figure in eighty was not recovered intact.
- **The measurement used a system Tesseract**, because the application finds no
  runtime on this machine (see below). It measures the OCR engine, not the
  application's runtime discovery.

### 5.1a Reference codes are the weak spot, not prose

Character error rate understates the risk, because the errors are not evenly
distributed over things a firm cares about. Measured on a scanned receipt:

| Field | Ground truth | Recovered |
|---|---|---|
| Amount | `KES 4,000.00` | `KES 4,000.00` — exact |
| Case number | `HCCOMM/E214/2026` | `HCCOMM/E21 4/2026` — spacing damage |
| Customer reference | `E6EWRY6F` | `EEEWRY6F` — `6` read as `E` |

Money survives, because digits with separators are well constrained. Mixed
alphanumeric references do not: `6`/`E`, `0`/`O`, `1`/`I` and `5`/`S` are the
usual confusions, and a reference has no grammar to correct against.

That is exactly the field the portal uses to reconcile a payment. A PRN or
customer reference recovered with one wrong character will not match, and the
failure looks like a missing payment rather than a misread. Any feature that
matches on these codes should compare loosely, or ask the user to confirm the
reference rather than trusting the scan.

### 5.2 The shipped bundle contains no OCR engine

Found while establishing the baseline, and more serious than any accuracy
figure: `main.spec` bundles the Tesseract runtime only `if
tesseract_runtime.exists()`, and `runtime/tesseract/` is not in the repository.
`discover_tesseract_runtime()` requires a signed manifest, so a system install
is not accepted either, and `resolve_ocr_engine()` returns `None`.

The consequence is that OCR is correctly wired and cannot run in the packaged
product: a scanned receipt still yields nothing, and `ocr_status` records
`pending_tesseract` rather than failing loudly. `DOCUMENT_VAULT_REQUIRE_TESSERACT_BUNDLE`
exists to make the release bundle assert the runtime is present, and is not set
by default.

**Both were done.** `scripts/stage_tesseract_runtime.py` stages a minimal
runtime (82 MiB: the executable, its libraries and one language, rather than the
87 MiB full install with training tools) and writes the hashed manifest
discovery validates. The binaries are gitignored -- the script is the
reproducible artefact, because 80+ MB in git history is permanent.

`resolve_ocr_engine()` now tries, in order of trust: a sidecar for evidence
runs, the bundled runtime, then an unmanifested system install. It also fixes a
second defect that would have kept OCR broken even once the runtime shipped: it
returned the *runtime* rather than the engine adapter, so callers got an object
with no `recognize_image`. That never surfaced because a runtime was never
found.

And availability is now reported rather than inferred. `main.py --selftest`
prints it, and the window says so before anything is imported. Silence was the
real failure: a scanned receipt imported as empty text with an `ocr_status`
nobody reads.

Measured through the application's own resolver: **11 of 11 scanned documents**
in the practice corpus now yield text and report `completed_tesseract`, where
all 11 previously yielded nothing.

Without this, "improving accuracy" is unfalsifiable. The figures in
`evidence.md` (RAG confidence 0.49–0.69) measure the system's confidence in
itself, not its correctness — those are not the same thing, and should not be
cited as accuracy.

---

## 6. What was not verified

- **Accuracy is now measured, on clean text only.** §5.1 records the baseline.
  No hand-transcribed scan was used, so accuracy on photographed and stamped
  originals -- the hard case, and the common one -- is still unquantified.
- **Docling's behaviour on Kenyan judiciary documents was not tested.** Stage 3
  assumes its layout detection generalises to these filings; that assumption
  needs a spike before committing to the work.
- **Bundle-size impact of OpenCV and a sentence-transformer was not measured**
  against the installer budget in
  [11-packaging-distribution.md](11-packaging-distribution.md).
- **The OCR course was reviewed as an architecture, not run.** No claim here
  depends on reproducing its throughput figures.
