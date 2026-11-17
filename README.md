# Veloxa CXO Cockpit

An evidence-backed executive cockpit for **Veloxa Technologies**, built for the Hiyaku Systems 5-day hackathon (16–20 November 2026). Individual entry.

The CEO asks one question and gets a short answer that cites the specific records behind it, states a confidence level, and says "I don't know" or "the sources disagree" when that is the honest answer. The cockpit opens on her worry list, as she asked in voice note T6a: up to three ranked concerns, each backed by evidence and carrying its own weakest link. If only two are well supported it shows two rather than padding the list, and the question box stays on the same screen. The same records ground 14 interviewable AI agents, one per person in Engineering, Finance, People & Ops and Marketing; anything invented about their lives is logged as an assumption.

Veloxa is a fictional B2B SaaS company in Bengaluru with 19 staff and about 66 customers. Its data room is contradictory: machine-generated call transcripts that mishear names and figures, and system exports that are better but have quirks of their own. Nobody will say which source is right. Deciding what to trust is the problem this system is built around.

## Status

Day 2 of 5 — 17 November 2026. Design and documentation only: there is no application code in the repository yet, so there are no setup, run or test commands to list. They will go here once they exist and have been run from a fresh clone. The Veloxa release pack is not in the repository (see `DECISIONS.md`, decision 8).

## Documentation

| File | Contents |
| --- | --- |
| `ARCHITECTURE.md` | Data model, trust ladder, conflict registry, point-in-time behaviour |
| `ASSUMPTIONS.md` | Assumptions, dated, with confidence and what would overturn them |
| `TRANSCRIPT_NOTES.md` | Suspected mishearings and contradictions, with evidence and conclusions |
| `DECISIONS.md` | Choices that could be defended either way, and what each costs |
| `AI_LOG.md` | What was delegated to AI, where it was wrong, and what changed |
| `voice_notes/` | Written responses to the CEO voice notes T6a onward |