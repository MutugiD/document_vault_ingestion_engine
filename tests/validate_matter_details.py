"""Validate reading matter details out of a Kenyan court document.

The risk here is not missing a field -- it is filling one in wrongly. A matter
opened with the wrong court or the wrong case number is worse than an empty
form, because nobody re-reads a field the computer already filled.

So the assertions are mostly about restraint: detection is anchored on the
formal heading, and a document without one yields nothing rather than a guess.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from intake.matter_details import extract_matter_details  # noqa: E402

MERU_APPEAL = """REPUBLIC OF KENYA
IN THE HIGH COURT OF KENYA AT MERU
[CORAM: MRIMA, J.]
CIVIL APPEAL NO. 109 OF 2018
ABDI YUSUF.....................................................APPELLANT
VERSUS
1. FAITH KINYA KIAIRA.........................................1ST RESPONDENT
2. ESTHER MWAMATU
JUDGMENT
1. The deceased was fatally wounded. The Supreme Court in Petition No. 3 of 2015
held that liability must be apportioned. The Court of Appeal at Nyeri agreed.
"""

SPLIT_HEADING = """REPUBLIC OF KENYA
IN THE HIGH COURT OF KENYA
AT MERU
CIVIL APPEAL NO.
48A OF 2020
KENYA WILDLIFE SERVICE........................................APPELLANT
VERSUS
ABRAHAM MNGAI MITUMITU......................................RESPONDENT
"""

COMMERCIAL_PLAINT = """REPUBLIC OF KENYA
IN THE HIGH COURT OF KENYA AT MILIMANI COMMERCIAL COURTS
HCCOMM/E214/2026
GITUMA OTIENO AND COMPANY ADVOCATES .......... PLAINTIFF
VERSUS
ANGELA WAMBUI NDERITO .......... 1ST DEFENDANT
"""

ELRC_CLAIM = """REPUBLIC OF KENYA
IN THE EMPLOYMENT AND LABOUR RELATIONS COURT AT NAIROBI
ELRC CAUSE NO. E455 OF 2026
JANE ADHIAMBO OWUOR .......... CLAIMANT
VERSUS
SAFARI LOGISTICS LIMITED .......... RESPONDENT
"""

# A receipt: no heading, no parties. Must yield nothing.
RECEIPT = """THE JUDICIARY OF KENYA
OFFICIAL PAYMENT RECEIPT
Customer Ref#: E6EWRY6F
Amount Paid: KES 4,000.00
"""


def main() -> None:
    # ── The court hearing the matter, not the courts it cites ────────────
    meru = extract_matter_details(MERU_APPEAL)
    assert meru.court == "High Court", meru.court
    assert meru.station == "Meru", meru.station
    assert meru.case_number == "CIVIL APPEAL NO. 109 OF 2018", meru.case_number
    assert meru.client_name == "Abdi Yusuf", meru.client_name
    assert "Faith Kinya Kiaira" in meru.parties, meru.parties
    assert meru.practice_area == "Civil", meru.practice_area
    # The body cites the Supreme Court and the Court of Appeal at Nyeri.
    # Neither may leak into the matter.
    assert "Supreme" not in meru.court
    assert meru.station != "Nyeri"

    # ── Heading split across lines ───────────────────────────────────────
    split = extract_matter_details(SPLIT_HEADING)
    assert split.court == "High Court", split.court
    assert split.station == "Meru", split.station
    assert "48A OF 2020" in split.case_number, split.case_number
    assert split.client_name == "Kenya Wildlife Service", split.client_name

    # ── Slash-form case numbers ──────────────────────────────────────────
    plaint = extract_matter_details(COMMERCIAL_PLAINT)
    assert plaint.case_number == "HCCOMM/E214/2026", plaint.case_number
    assert plaint.court == "High Court", plaint.court
    assert plaint.client_name == "Gituma Otieno And Company Advocates", plaint.client_name
    assert "Angela Wambui Nderito" in plaint.parties, plaint.parties
    # Role words are stripped from party names.
    assert "PLAINTIFF" not in plaint.parties.upper()
    assert "DEFENDANT" not in plaint.parties.upper()

    # ── A specialised court is not "High Court" ──────────────────────────
    elrc = extract_matter_details(ELRC_CLAIM)
    assert elrc.court == "Employment and Labour Relations Court", elrc.court
    assert elrc.station == "Nairobi", elrc.station
    assert elrc.practice_area == "Employment", elrc.practice_area

    # ── Restraint: no heading means no guess ─────────────────────────────
    receipt = extract_matter_details(RECEIPT)
    assert receipt.is_empty, receipt.as_fields()
    assert extract_matter_details("").is_empty
    assert extract_matter_details("   \n  ").is_empty

    # ── as_fields omits what was not found ───────────────────────────────
    fields = receipt.as_fields()
    assert fields == {}, fields
    assert "court" in meru.as_fields()
    assert set(meru.as_fields()) <= {
        "case_number",
        "parties",
        "client_name",
        "court",
        "station",
        "practice_area",
    }

    print("MATTER DETAILS VALIDATION PASS")


if __name__ == "__main__":
    main()
