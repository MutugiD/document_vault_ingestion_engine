"""Measure extraction accuracy against ground truth.

Nothing in this repository measured whether extracted text is *correct*. The
figures quoted elsewhere -- RAG confidence, citation counts -- measure the
system's confidence in itself and whether retrieval returned anything. Neither
is accuracy, and neither should be cited as accuracy.

This establishes a baseline so a change to the pipeline can be shown to help or
hurt, rather than argued about.

Ground truth comes from two sources, and the distinction matters:

* **Synthetic pages** are rendered from text this file owns, then flattened to
  an image. The ground truth is exact, because we wrote it. This isolates OCR
  quality from PDF parsing.
* **Real judgments** carry their own born-digital text layer. Rasterising a
  page and OCRing it, then comparing against that layer, measures OCR against a
  reference produced by the typesetter rather than by a human transcriber.

Neither substitutes for hand-transcribing scanned originals, which is still the
only way to measure accuracy on genuinely scanned Kenyan filings. That is
recorded as a limitation rather than glossed over.

Run manually: it needs the corpora and takes a few minutes.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fitz  # noqa: E402

from intake.extraction import extract_text  # noqa: E402
from intake.matter_details import extract_matter_details  # noqa: E402

MAUA = ROOT / "test-output" / "maua-corpus"
REPORT = ROOT / "test-output" / "extraction-accuracy.json"

# Text we own, so the ground truth is exact. Written to look like the pages a
# Kenyan firm actually scans: a fee table, a stamped receipt, a pleading.
SYNTHETIC: tuple[tuple[str, str], ...] = (
    (
        "receipt",
        "THE JUDICIARY OF KENYA\n"
        "OFFICIAL PAYMENT RECEIPT\n"
        "Customer Ref: E6EWRY6F\n"
        "Transaction No: 00UD8PF058F8\n"
        "Date: 08-Apr-2026 09:04:45\n"
        "Channel: PYBL\n"
        "Amount Paid: KES 4,000.00\n"
        "Case No: HCCOMM/E214/2026\n"
        "Tracking No: AERJ2026\n",
    ),
    (
        "fee-table",
        "CASE FEES\n"
        "Payment Type Fees PRN E6FGF4JY Amount 0.00 Paid 0.00 Balance 0.00\n"
        "Payment Type Fees PRN E6F7DC6P Amount 0.00 Paid 0.00 Balance 0.00\n"
        "Payment Type Fees PRN E6EWRY6F Amount 4000.00 Paid 4000.00 Balance 0.00\n"
        "Total assessed KES 330,555.00\n"
        "Total paid KES 330,555.00\n"
        "Balance due KES 0.00\n",
    ),
    (
        "pleading",
        "REPUBLIC OF KENYA\n"
        "IN THE HIGH COURT OF KENYA AT MERU\n"
        "CIVIL APPEAL NO. 109 OF 2018\n"
        "ABDI YUSUF Appellant\n"
        "VERSUS\n"
        "FAITH KINYA KIAIRA Respondent\n"
        "The appellant seeks an order setting aside the judgment delivered on\n"
        "12th June 2018 and a retrial before another magistrate.\n",
    ),
)


@dataclass(frozen=True)
class Score:
    name: str
    truth_chars: int
    output_chars: int
    cer: float  # character error rate, 0.0 is perfect
    wer: float  # word error rate
    numbers_recalled: float  # share of ground-truth numbers that survived


def normalise(text: str) -> str:
    """Collapse whitespace so layout differences do not count as errors."""
    return " ".join(text.split())


def edit_distance(left: str, right: str) -> int:
    """Levenshtein distance, row-at-a-time to stay within memory on long text."""
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, start=1):
        current = [i]
        for j, b in enumerate(right, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (a != b)))
        previous = current
    return previous[-1]


def numbers_in(text: str) -> list[str]:
    """Money and reference figures -- the parts a firm cannot afford wrong."""
    return re.findall(r"\d[\d,]*\.?\d*", text)


def score(name: str, truth: str, output: str) -> Score:
    truth_n, output_n = normalise(truth), normalise(output)
    cer = edit_distance(truth_n, output_n) / max(len(truth_n), 1)
    truth_words, output_words = truth_n.split(), output_n.split()
    wer = edit_distance(" ".join(truth_words), " ".join(output_words)) / max(
        len(" ".join(truth_words)), 1
    )
    # Word-level distance, computed over words rather than characters.
    wer = _word_error_rate(truth_words, output_words)
    truth_numbers = numbers_in(truth_n)
    recalled = sum(1 for n in truth_numbers if n in output_n)
    return Score(
        name=name,
        truth_chars=len(truth_n),
        output_chars=len(output_n),
        cer=round(cer, 4),
        wer=round(wer, 4),
        numbers_recalled=round(recalled / max(len(truth_numbers), 1), 4),
    )


def _word_error_rate(truth: list[str], output: list[str]) -> float:
    if not truth:
        return 0.0
    previous = list(range(len(output) + 1))
    for i, a in enumerate(truth, start=1):
        current = [i]
        for j, b in enumerate(output, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (a != b)))
        previous = current
    return previous[-1] / len(truth)


def render_scanned(text: str, path: Path, dpi: int = 200) -> None:
    """Write text to a page, then flatten it to an image, as a scanner does."""
    document = fitz.open()
    page = document.new_page()
    page.insert_textbox(fitz.Rect(56, 56, 540, 780), text, fontsize=11, fontname="helv")
    scanned = fitz.open()
    pixmap = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
    new_page = scanned.new_page(width=page.rect.width, height=page.rect.height)
    new_page.insert_image(page.rect, pixmap=pixmap)
    scanned.save(path)
    scanned.close()
    document.close()


class SystemTesseract:
    """Tesseract from a system install, for measurement only.

    The application resolves OCR through a *bundled* runtime validated against
    a signed manifest, and returns no engine when one is absent -- which is the
    case on a plain developer machine, and on the current packaged build. This
    measures the OCR engine itself, so a baseline exists independently of how
    the runtime is discovered and shipped.
    """

    def __init__(self, executable: Path) -> None:
        self.executable = executable

    def recognize_image(self, image_path: Path, *, languages=None) -> str:
        out = Path(tempfile.mkdtemp()) / "out"
        subprocess.run(
            [str(self.executable), str(image_path), str(out)],
            capture_output=True,
            check=True,
        )
        return out.with_suffix(".txt").read_text(encoding="utf-8", errors="replace")


def ocr_engine():
    """The application's engine if it has one, otherwise a system Tesseract."""
    from core.manual_app import resolve_ocr_engine

    engine = resolve_ocr_engine(Path("measurement.pdf"))
    if engine is not None:
        return engine, "bundled runtime"
    for candidate in (
        Path("C:/Program Files/Tesseract-OCR/tesseract.exe"),
        Path("C:/Program Files (x86)/Tesseract-OCR/tesseract.exe"),
    ):
        if candidate.exists():
            return SystemTesseract(candidate), f"system install ({candidate})"
    return None, "none available"


def main() -> int:
    scores: list[Score] = []

    print("=" * 78)
    print("Synthetic pages -- ground truth is exact, because we wrote it")
    print("=" * 78)
    engine, provenance = ocr_engine()
    print(f"OCR engine: {provenance}")
    if engine is None:
        print("  no OCR engine on this machine; cannot measure extraction accuracy")
        return 1
    print(f"{'page':14s} {'truth':>7s} {'out':>7s} {'CER':>7s} {'WER':>7s} {'numbers':>8s}")
    with tempfile.TemporaryDirectory() as temp_dir:
        for name, truth in SYNTHETIC:
            path = Path(temp_dir) / f"{name}.pdf"
            render_scanned(truth, path)
            extracted = extract_text(path, ocr_engine=engine)
            result = score(f"synthetic/{name}", truth, extracted.text)
            scores.append(result)
            print(
                f"{name:14s} {result.truth_chars:7d} {result.output_chars:7d} "
                f"{result.cer:7.3f} {result.wer:7.3f} {result.numbers_recalled:8.1%}"
            )

    print()
    print("=" * 78)
    print("Real judgments -- OCR of a rasterised page vs its own text layer")
    print("=" * 78)
    judgments = sorted(MAUA.glob("*.pdf"))
    if not judgments:
        print(f"  (no corpus at {MAUA}; skipped)")
    else:
        print(
            f"{'document':34s} {'page':>4s} {'truth':>7s} {'CER':>7s} {'WER':>7s} {'numbers':>8s}"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            for judgment in judgments:
                with fitz.open(judgment) as document:
                    page_index = next(
                        (
                            i
                            for i, page in enumerate(document)
                            if len(page.get_text("text").split()) > 120
                        ),
                        None,
                    )
                    if page_index is None:
                        continue
                    truth = document[page_index].get_text("text")
                    pixmap = document[page_index].get_pixmap(
                        matrix=fitz.Matrix(300 / 72, 300 / 72), alpha=False
                    )
                scanned = Path(temp_dir) / f"{judgment.stem}-{page_index}.png"
                pixmap.save(scanned)
                output = engine.recognize_image(scanned)
                result = score(f"{judgment.stem}#p{page_index}", truth, output)
                scores.append(result)
                print(
                    f"{judgment.stem[:34]:34s} {page_index:4d} {result.truth_chars:7d} "
                    f"{result.cer:7.3f} {result.wer:7.3f} {result.numbers_recalled:8.1%}"
                )

    # ── Matter details: a field-level accuracy measure ───────────────────
    print()
    print("=" * 78)
    print("Matter details read from the heading -- exact-match against the filing")
    print("=" * 78)
    expected = {
        "meru-hc-mrima-2019-2805": ("High Court", "Meru", "CIVIL APPEAL NO. 109 OF 2018"),
        "kws-v-mitumitu-maua-cmcc-178-2018": ("High Court", "Meru", None),
        "kaberia-michubu-v-republic-maua": ("High Court", "Meru", None),
    }
    field_hits = field_total = 0
    for stem, (court, station, case_number) in expected.items():
        path = MAUA / f"{stem}.pdf"
        if not path.exists():
            continue
        details = extract_matter_details(extract_text(path).text)
        checks = [("court", court, details.court), ("station", station, details.station)]
        if case_number:
            checks.append(("case_number", case_number, details.case_number))
        for field, want, got in checks:
            field_total += 1
            ok = got == want
            field_hits += ok
            print(f"  {stem[:34]:34s} {field:12s} {'OK ' if ok else 'MISS'} {got[:34]!r}")

    # ── Summary ──────────────────────────────────────────────────────────
    print()
    print("=" * 78)
    if scores:
        mean_cer = sum(s.cer for s in scores) / len(scores)
        mean_wer = sum(s.wer for s in scores) / len(scores)
        mean_numbers = sum(s.numbers_recalled for s in scores) / len(scores)
        print(f"pages measured        : {len(scores)}")
        print(f"mean character error  : {mean_cer:.3f}")
        print(f"mean word error       : {mean_wer:.3f}")
        print(f"mean number recall    : {mean_numbers:.1%}")
    if field_total:
        print(f"matter detail fields  : {field_hits}/{field_total} exact")
    print("=" * 78)
    print("Ground truth is synthetic text we own, and the born-digital text layer")
    print("of real judgments. Neither substitutes for hand-transcribed scans, which")
    print("remain unmeasured -- see documentation/doc-extraction-improvement.md.")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(
            {
                "pages": [s.__dict__ for s in scores],
                "matter_detail_fields": {"exact": field_hits, "total": field_total},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nbaseline written: {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
