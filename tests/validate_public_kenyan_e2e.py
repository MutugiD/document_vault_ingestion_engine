"""Validate public Kenyan legal-document E2E runner with deterministic fixtures."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary_dir:
        workspace = Path(temporary_dir)
        input_root = workspace / "public-docs"
        input_root.mkdir()
        _write_pdf(
            input_root / "supreme-court-rules.pdf",
            "The Supreme Court rules provide forms, notices, petitions, and procedure "
            "for filing applications in the Supreme Court of Kenya.",
        )
        _write_pdf(
            input_root / "land-commission-stay.pdf",
            "The National Land Commission stay application concerns land, registry "
            "procedure, court orders, and a public law dispute.",
        )
        _write_pdf(
            input_root / "court-of-appeal-registry.pdf",
            "The Court of Appeal registry manual discusses appeals, notices, records, "
            "registry workflow, and court filing procedure.",
        )

        report_path = workspace / "report.json"
        command = [
            sys.executable,
            str(ROOT / "scripts" / "public_kenyan_e2e.py"),
            "--input",
            str(input_root),
            "--workspace",
            str(workspace / "scratch"),
            "--report",
            str(report_path),
        ]
        result = subprocess.run(command, check=False, capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "PUBLIC KENYAN E2E PASS" in result.stdout
        assert '"restore_verified": true' in result.stdout
        assert '"confidence":' in result.stdout
        assert report_path.exists()

        app_command = [
            sys.executable,
            str(ROOT / "main.py"),
            "--public-kenya-e2e",
            str(input_root),
        ]
        app_result = subprocess.run(app_command, check=False, capture_output=True, text=True)
        assert app_result.returncode == 0, app_result.stdout + app_result.stderr
        assert '"answers":' in app_result.stdout
        assert '"citations":' in app_result.stdout
        assert '"confidence":' in app_result.stdout

    print("PUBLIC KENYAN E2E VALIDATION PASS")


def _write_pdf(path: Path, text: str) -> None:
    document = fitz.open()
    page = document.new_page()
    page.insert_textbox(fitz.Rect(72, 72, 523, 760), text, fontsize=11)
    document.save(path)
    document.close()


if __name__ == "__main__":
    main()
