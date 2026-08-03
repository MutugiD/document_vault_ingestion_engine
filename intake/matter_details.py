"""Read matter details out of a Kenyan court document.

Opening a matter means retyping what is already printed on the first page of
the filing: the case number, the parties, the court and the station. This reads
them instead.

Detection is anchored on the formal heading every Kenyan filing carries:

    REPUBLIC OF KENYA
    IN THE HIGH COURT OF KENYA AT MERU
    CIVIL APPEAL NO. 109 OF 2018
    ABDI YUSUF.................................................
    VERSUS
    FAITH KINYA KIAIRA........................................

Anchoring matters. Scanning the page for any court name reads the courts a
judgment *cites* rather than the one hearing it -- an appeal from Maua that
distinguishes a Supreme Court authority is not a Supreme Court matter. Every
field is a suggestion for the user to confirm, never written unseen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# "IN THE HIGH COURT OF KENYA AT MERU", with AT often on the following line.
HEADING_PATTERN = re.compile(
    r"^\s*IN\s+THE\s+(?P<court>[A-Z'’\s&]+?)"
    r"(?:\s+OF\s+KENYA)?"
    r"(?:\s+(?:AT|SITTING\s+AT)\s+(?P<station>[A-Z'’\s]+?))?\s*$",
    re.MULTILINE,
)
STANDALONE_STATION = re.compile(r"^\s*(?:AT|SITTING\s+AT)\s+([A-Z'’\s]{3,40})\s*$", re.MULTILINE)

# Case numbers as the registries write them, including numbers split over a
# line break ("CIVIL APPEAL NO.\n48A OF 2020").
CASE_NUMBER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b([A-Z]{2,8}(?:/[A-Z]?\d{1,6}){1,2}/\d{4})\b"),
    re.compile(
        r"((?:[A-Z][A-Za-z'’]{2,20}\s+){0,4}"
        r"(?:CAUSE|CASE|APPEAL|PETITION|SUIT|APPLICATION|MISC(?:ELLANEOUS)?)\s+"
        r"(?:NO\.?|NUMBER)\s*[A-Z]?\d{1,6}[A-Z]?(?:\s*[&,]\s*\d{1,6})*\s+OF\s+\d{4})",
        re.IGNORECASE,
    ),
    re.compile(r"(\[\d{4}\]\s*KE[A-Z]{2}\s*\d{1,6})"),
)

VERSUS = re.compile(r"^\s*(?:VERSUS|VS\.?|V\.?)\s*$", re.IGNORECASE)

COURT_LABELS: tuple[tuple[str, str], ...] = (
    ("EMPLOYMENT AND LABOUR RELATIONS", "Employment and Labour Relations Court"),
    ("ENVIRONMENT AND LAND", "Environment and Land Court"),
    ("COURT OF APPEAL", "Court of Appeal"),
    ("SUPREME COURT", "Supreme Court"),
    ("CHIEF MAGISTRATE", "Chief Magistrate's Court"),
    ("SENIOR PRINCIPAL MAGISTRATE", "Senior Principal Magistrate's Court"),
    ("PRINCIPAL MAGISTRATE", "Principal Magistrate's Court"),
    ("SENIOR RESIDENT MAGISTRATE", "Senior Resident Magistrate's Court"),
    ("RESIDENT MAGISTRATE", "Resident Magistrate's Court"),
    ("MAGISTRATE", "Magistrate's Court"),
    ("HIGH COURT", "High Court"),
)

PRACTICE_AREAS: tuple[tuple[str, str], ...] = (
    ("SUCCESSION", "Succession"),
    ("PROBATE", "Succession"),
    ("EMPLOYMENT", "Employment"),
    ("LABOUR", "Employment"),
    ("ENVIRONMENT AND LAND", "Environment and Land"),
    ("JUDICIAL REVIEW", "Judicial Review"),
    ("CONSTITUTIONAL PETITION", "Constitutional"),
    ("CRIMINAL", "Criminal"),
    ("COMMERCIAL", "Commercial"),
    ("MATRIMONIAL", "Family"),
    ("DIVORCE", "Family"),
    ("CIVIL", "Civil"),
)

ROLE_WORDS = (
    "PLAINTIFF",
    "DEFENDANT",
    "RESPONDENT",
    "APPELLANT",
    "APPLICANT",
    "PETITIONER",
    "CLAIMANT",
    "INTERESTED PARTY",
    "EXPARTE",
    "EX-PARTE",
)

# How far into the document the heading can reasonably be.
HEADING_LINES = 24


@dataclass(frozen=True)
class MatterDetails:
    """What could be read. Empty strings mean 'not found'."""

    case_number: str = ""
    parties: str = ""
    client_name: str = ""
    court: str = ""
    station: str = ""
    practice_area: str = ""
    found: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_empty(self) -> bool:
        return not self.found

    def as_fields(self) -> dict[str, str]:
        """Only the fields actually found, for prefilling a form."""
        candidates = {
            "case_number": self.case_number,
            "parties": self.parties,
            "client_name": self.client_name,
            "court": self.court,
            "station": self.station,
            "practice_area": self.practice_area,
        }
        return {key: value for key, value in candidates.items() if value}


def extract_matter_details(text: str) -> MatterDetails:
    """Read matter details from a document's extracted text."""
    if not text or not text.strip():
        return MatterDetails()

    lines = [line.rstrip() for line in text.splitlines()]
    heading = [line for line in lines[:HEADING_LINES] if line.strip()]
    if not heading:
        return MatterDetails()

    found: list[str] = []
    court, station, court_line = _read_court(heading)
    if court:
        found.append("court")
    if station:
        found.append("station")

    # The case number sits between the court heading and the parties.
    versus_index = next((i for i, line in enumerate(heading) if VERSUS.match(line)), None)
    upper_bound = versus_index if versus_index is not None else len(heading)
    case_region = " ".join(heading[court_line + 1 : upper_bound]) if court_line >= 0 else ""
    case_number = _first_match(CASE_NUMBER_PATTERNS, case_region or " ".join(heading))
    if case_number:
        found.append("case_number")

    parties = client_name = ""
    if versus_index is not None:
        left = _party_before(heading, versus_index)
        right = _party_after(heading, versus_index)
        if left and right:
            parties = f"{left} vs {right}"
            client_name = left
            found.extend(["parties", "client_name"])

    # Practice area comes from the heading's own wording -- the case number
    # ("CIVIL APPEAL", "SUCCESSION CAUSE") or the court itself, since a
    # specialised court names its area ("Employment and Labour Relations").
    # Never from the body, which discusses many areas.
    practice_area = _first_label(PRACTICE_AREAS, f"{case_number} {case_region} {court}".upper())
    if practice_area:
        found.append("practice_area")

    return MatterDetails(
        case_number=case_number,
        parties=parties,
        client_name=client_name,
        court=court,
        station=station,
        practice_area=practice_area,
        found=tuple(found),
    )


def _read_court(heading: list[str]) -> tuple[str, str, int]:
    """Court, station and the index of the heading line, from 'IN THE ... AT ...'."""
    for index, line in enumerate(heading):
        match = HEADING_PATTERN.match(line)
        if not match:
            continue
        court_text = " ".join(match.group("court").split())
        court = _first_label(COURT_LABELS, court_text)
        if not court:
            continue
        station = " ".join((match.group("station") or "").split())
        if not station:
            # "IN THE HIGH COURT OF KENYA" / "AT MERU" on separate lines.
            for following in heading[index + 1 : index + 3]:
                standalone = STANDALONE_STATION.match(following)
                if standalone:
                    station = " ".join(standalone.group(1).split())
                    break
        return court, station.title() if station else "", index
    return "", "", -1


def _party_before(heading: list[str], versus_index: int) -> str:
    for line in reversed(heading[:versus_index]):
        party = _tidy_party(line)
        if party:
            return party
    return ""


def _party_after(heading: list[str], versus_index: int) -> str:
    for line in heading[versus_index + 1 :]:
        party = _tidy_party(line)
        if party:
            return party
    return ""


def _first_match(patterns: tuple[re.Pattern[str], ...], text: str) -> str:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return " ".join(match.group(1).split())
    return ""


def _first_label(table: tuple[tuple[str, str], ...], upper_text: str) -> str:
    for marker, label in table:
        if marker in upper_text:
            return label
    return ""


def _tidy_party(raw: str) -> str:
    """Trim the decoration registries put around party names."""
    cleaned = " ".join(raw.split())
    cleaned = re.sub(r"\.{2,}.*$", "", cleaned).strip()
    cleaned = re.sub(r"^\d+\.\s*", "", cleaned)  # "1. FAITH KINYA KIAIRA"
    for role in ROLE_WORDS:
        cleaned = re.sub(rf"\b(\d+(ST|ND|RD|TH)\s+)?{role}S?\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\((?:suing|sued)[^)]*\)", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip(" .,-&:")

    if len(cleaned) < 3 or len(cleaned) > 120:
        return ""
    skip = (
        "REPUBLIC OF KENYA",
        "IN THE MATTER OF",
        "CORAM",
        "JUDGMENT",
        "RULING",
        "BETWEEN",
        "AND",
    )
    upper = cleaned.upper()
    if any(upper.startswith(marker) for marker in skip):
        return ""
    if CASE_NUMBER_PATTERNS[1].search(upper) or re.match(r"^\[?\d{4}\]?", upper):
        return ""
    if not re.search(r"[A-Za-z]{3}", cleaned):
        return ""
    return cleaned.title() if cleaned.isupper() else cleaned
