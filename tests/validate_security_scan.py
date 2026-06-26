"""Validate repository and release security scans."""

from __future__ import annotations

import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from security_checks import scan_paths, scan_release_zip, scan_repository  # noqa: E402


def main() -> None:
    repo_findings = scan_repository(ROOT)
    assert not repo_findings, _format_findings(repo_findings)

    with tempfile.TemporaryDirectory() as temporary_dir:
        workspace = Path(temporary_dir)
        risky_file = workspace / "sample.txt"
        risky_file.write_text("token = '" + "AKIA" + ("A" * 16) + "'", encoding="utf-8")
        findings = scan_paths([risky_file], workspace)
        assert any(finding.rule == "aws_access_key_id" for finding in findings)

        recovery_file = workspace / "recovery.txt"
        recovery_file.write_text(
            "recovery_key = '" + "locally-held-key-that-should-not-ship" + "'",
            encoding="utf-8",
        )
        recovery_findings = scan_paths([recovery_file], workspace)
        assert any(finding.rule == "recovery_key_assignment" for finding in recovery_findings)

        safe_zip = workspace / "safe.zip"
        with zipfile.ZipFile(safe_zip, "w") as archive:
            archive.writestr("DocumentVaultIngestionEngine/readme.txt", "safe")
        assert not scan_release_zip(safe_zip)

        risky_zip = workspace / "risky.zip"
        with zipfile.ZipFile(risky_zip, "w") as archive:
            archive.writestr("DocumentVaultIngestionEngine/.env", "unsafe")
        release_findings = scan_release_zip(risky_zip)
        assert any(finding.rule == "forbidden_release_filename" for finding in release_findings)

    release_zip = _release_zip_path()
    if release_zip.exists():
        release_findings = scan_release_zip(release_zip)
        assert not release_findings, _format_findings(release_findings)

    print("SECURITY SCAN VALIDATION PASS")


def _release_zip_path() -> Path:
    import tomllib

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = str(pyproject["project"]["version"])
    return ROOT / "release-output" / f"DocumentVaultIngestionEngine-{version}-windows-x64.zip"


def _format_findings(findings: tuple[object, ...]) -> str:
    return "\n".join(str(finding) for finding in findings)


if __name__ == "__main__":
    main()
