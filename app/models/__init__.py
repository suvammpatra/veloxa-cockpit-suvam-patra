"""ORM models. Importing this package registers every table on Base.

Payroll is deliberately absent: it lives in a separate database that only
app.privacy.payroll can open (DECISIONS.md 3, ARCHITECTURE.md section 10).
"""

from app.models.facts import Commit, FinancialTxn, Incident, Ticket
from app.models.meta import AppMeta
from app.models.org import (
    Alias,
    Department,
    DepartmentLine,
    DepartmentMembership,
    Person,
    Position,
    PositionHolder,
    Project,
    ReportingLine,
)
from app.models.sources import Claim, Conflict, ConflictSide, Evidence, IngestionError, SourceRecord

__all__ = [
    "AppMeta", "Alias", "Claim", "Commit", "Conflict", "ConflictSide", "Department",
    "DepartmentLine", "DepartmentMembership", "Evidence", "FinancialTxn", "Incident",
    "IngestionError", "Person", "Position", "PositionHolder", "Project", "ReportingLine",
    "SourceRecord", "Ticket",
]
