"""What each known source file is, and how far it is trusted.

Systems and trust rungs come from ARCHITECTURE.md section 2 and the Day 3
addendum (15.1). A file that matches no profile is still ingested, as plain
evidence with no trust rung, and the pipeline logs a warning so it can be
reviewed. Nothing here contains company data; it only names file patterns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    name: str
    system: str | None
    trust_rung: int | None
    kind: str          # employees | payroll | gl | jira | incidents | git | table | email | transcript | document
    role: str = "evidence"  # evidence | copy | reference | template (templates are skipped)
    restricted_columns: tuple[str, ...] = ()  # never stored outside the payroll store
    note: str | None = None


# Order matters: the first pattern that matches the file name wins.
_PROFILES: list[tuple[str, Profile]] = [
    (r"(^|/)templates/|(^|/)(Connection_Worksheet|Entity_Resolution|Evidence_Index)\.",
     Profile("template", None, None, "document", role="template",
             note="Template for my own use; never evidence (ARCHITECTURE.md 2).")),
    (r"(^|/)README\.txt$", Profile("readme", "Data room README", None, "document", role="reference")),
    (r"Candidate_Brief\.docx$", Profile("brief", "Hackathon brief", None, "document", role="reference")),
    (r"GL_Export_.*\.xlsx$", Profile("gl", "Zoho Books", 1, "gl")),
    (r"Payroll_Register_.*\.xlsx$",
     Profile("payroll", "Payroll workbook (pre-Keka)", 1, "payroll",
             restricted_columns=("gross", "deduction", "net"),
             note="Restricted: amounts go only to the payroll store (DECISIONS.md 3).")),
    (r"Board_Update_.*\.pdf$", Profile("board", "Management", 2, "document")),
    (r"Invoice_.*\.pdf$", Profile("invoice", "Vendor invoice", 2, "document")),
    (r"Employee_Master\.xlsx$", Profile("employees", "Keka HRMS", 3, "employees")),
    (r"Resignation_Letter_.*\.pdf$", Profile("letter", "Employee document", 3, "document")),
    (r"Leave_Register\.xlsx$", Profile("leave", "Google Sheet, People & Ops", 3, "table")),
    (r"Hiring_Tracker\.xlsx$", Profile("hiring", "Keka Hire", 3, "table")),
    (r"Pulse_Survey\.xlsx$", Profile("pulse", "Culture Amp", 3, "table")),
    (r"Jira_Export_.*\.xlsx$", Profile("jira", "Jira", 3, "jira")),
    (r"git_log\.csv$", Profile("git", "GitHub", 3, "git")),
    (r"Incidents_.*\.xlsx$", Profile("incidents", "PagerDuty", 3, "incidents")),
    (r"Launch_Kit.*\.pdf$", Profile("launch_kit", "Marketing document", 3, "document")),
    (r"OnCall_Rota\.xlsx$", Profile("rota", "Team wiki", 4, "table")),
    (r"Email_Printouts\.pdf$",
     Profile("email_copy", "Email (printed copy)", None, "document", role="copy",
             note="A copy of the .eml files, not a second source (ARCHITECTURE.md 15.1).")),
    (r"\.eml$", Profile("email", "Email", 4, "email")),
    (r"(^|/)T\d+[a-z]?_[^/]*\.docx$", Profile("transcript", "MeetNotes AI", 5, "transcript")),
]

UNKNOWN = Profile("unknown", None, None, "document",
                  note="No profile matches this file; trust rung not assigned.")


def match(relative_path: str) -> Profile:
    path = relative_path.replace("\\", "/")
    for pattern, profile in _PROFILES:
        if re.search(pattern, path, flags=re.I):
            if profile.kind == "document" and path.lower().endswith((".csv", ".xlsx")):
                return Profile(profile.name, profile.system, profile.trust_rung, "table",
                               profile.role, profile.restricted_columns, profile.note)
            return profile
    if path.lower().endswith((".csv", ".xlsx")):
        return Profile("unknown", None, None, "table", note=UNKNOWN.note)
    return UNKNOWN


def confidence_for(rung: int | None) -> str:
    """Evidence confidence by source type: system exports H, email and hand tables M,
    transcripts L, unprofiled files M."""
    if rung is None:
        return "M"
    return "H" if rung <= 3 else ("M" if rung == 4 else "L")


def is_restricted(profile: Profile, header: str) -> bool:
    h = header.casefold()
    return any(word in h for word in profile.restricted_columns)
