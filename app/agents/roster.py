"""The 14 agents, exactly as ARCHITECTURE.md section 8 lists them (DECISIONS.md 5).

Names are the Keka spellings. An agent is linked to an employee record only by an exact
full-name match among employees; it is never linked through an alias, a first name or a
guess. The five other staff (Ananya Rao, Manoj Kumar, Divya Reddy, Imran Siddiqui and
Kavya Narayan) have no agent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentSpec:
    name: str
    department: str   # the agent group in ARCHITECTURE.md 8, not a claim about any date

    @property
    def slug(self) -> str:
        return re.sub(r"[^a-z0-9]+", "-", self.name.lower()).strip("-")


AGENT_ROSTER: tuple[AgentSpec, ...] = (
    AgentSpec("Vikram Menon", "Engineering"),
    AgentSpec("Priya Nair", "Engineering"),
    AgentSpec("Arjun Das", "Engineering"),
    AgentSpec("Sneha Kulkarni", "Engineering"),
    AgentSpec("Rahul Verma", "Engineering"),
    AgentSpec("Meera Iyer", "Finance"),
    AgentSpec("Karthik Subramanian", "Finance"),
    AgentSpec("Fatima Sheikh", "Finance"),
    AgentSpec("Deepa Joshi", "People & Ops"),
    AgentSpec("Rohan Banerjee", "People & Ops"),
    AgentSpec("Lakshmi Pillai", "People & Ops"),
    AgentSpec("Nikhil Bose", "Marketing"),
    AgentSpec("Aisha Khan", "Marketing"),
    AgentSpec("Siddharth Mehta", "Marketing"),
)

NO_AGENT = ("Ananya Rao", "Manoj Kumar", "Divya Reddy", "Imran Siddiqui", "Kavya Narayan")
