"""Repository and release security scans."""

from __future__ import annotations

import re
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path


class SecurityScanError(Exception):
    """Raised when security findings are detected."""


@dataclass(frozen=True)
class SecurityFinding:
    path: str
    rule: str
    detail: str


SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("aws_access_key_id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("azure_connection_string", re.compile(r"DefaultEndpointsProtocol=https;AccountName=", re.I)),
    ("google_private_key_json", re.compile(r'"private_key"\s*:\s*"-----BEGIN PRIVATE KEY-----')),
)
RECOVERY_KEY_PATTERN = re.compile(
    r"\brecovery[_-]?key\s*[:=]\s*['\"](?P<value>[^'\"]{12,})",
    re.I,
)
ALLOWED_TEST_RECOVERY_VALUES = {
    "backup validator recovery key",
    "cloud boundary recovery key",
    "correct horse battery staple for vault v1",
    "e2e recovery key",
    "wrong recovery key",
}

FORBIDDEN_RELEASE_NAME_MARKERS = (
    ".env",
    "client-document",
    "credential",
    "id_rsa",
    "private-key",
    "private_key",
    "recovery-key",
    "secret",
)

BINARY_SUFFIXES = {
    ".db",
    ".dll",
    ".docx",
    ".exe",
    ".ico",
    ".jpg",
    ".jpeg",
    ".pdf",
    ".png",
    ".pyd",
    ".pyc",
    ".so",
    ".sqlite",
    ".tiff",
    ".zip",
}

EXCLUDED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "build",
    "dist",
    "release-output",
    "test-output",
    "__pycache__",
}
SELF_REFERENTIAL_PATTERN_FILES = {"security_checks/scanner.py"}


def scan_repository(root: Path) -> tuple[SecurityFinding, ...]:
    tracked_files = _git_tracked_files(root)
    if tracked_files:
        paths = [root / path for path in tracked_files]
    else:
        paths = [
            path
            for path in root.rglob("*")
            if path.is_file() and not set(path.relative_to(root).parts).intersection(EXCLUDED_DIRS)
        ]
    return scan_paths(paths, root)


def scan_paths(paths: list[Path], root: Path) -> tuple[SecurityFinding, ...]:
    findings: list[SecurityFinding] = []
    for path in paths:
        if not path.exists() or path.suffix.lower() in BINARY_SUFFIXES:
            continue
        relative = _relative_name(path, root)
        lowered = relative.lower().replace("\\", "/")
        if any(marker in lowered for marker in FORBIDDEN_RELEASE_NAME_MARKERS):
            findings.append(SecurityFinding(relative, "forbidden_filename", lowered))
        text = _read_text_safely(path)
        if text is None:
            continue
        if relative in SELF_REFERENTIAL_PATTERN_FILES:
            continue
        for rule, pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(SecurityFinding(relative, rule, "sensitive value shape detected"))
        for match in RECOVERY_KEY_PATTERN.finditer(text):
            value = match.group("value").strip().lower()
            if relative.startswith("tests/") and value in ALLOWED_TEST_RECOVERY_VALUES:
                continue
            findings.append(
                SecurityFinding(relative, "recovery_key_assignment", "recovery key assignment")
            )
    return tuple(findings)


def scan_release_zip(zip_path: Path) -> tuple[SecurityFinding, ...]:
    findings: list[SecurityFinding] = []
    with zipfile.ZipFile(zip_path, "r") as archive:
        for name in archive.namelist():
            lowered = name.lower().replace("\\", "/")
            if any(marker in lowered for marker in FORBIDDEN_RELEASE_NAME_MARKERS):
                findings.append(SecurityFinding(name, "forbidden_release_filename", lowered))
    return tuple(findings)


def _git_tracked_files(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _relative_name(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _read_text_safely(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data[:4096]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None
