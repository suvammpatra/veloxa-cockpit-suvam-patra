# Veloxa CXO Cockpit

An evidence-backed executive cockpit for **Veloxa Technologies**, built for the Hiyaku Systems 5-day hackathon (16–20 November 2026). Individual entry.

The CEO asks one question and gets a short answer that cites the specific records behind it, states a confidence level, and says "I don't know" or "the sources disagree" when that is the honest answer. The cockpit opens on her worry list, as she asked in voice note T6a: up to three ranked concerns, each backed by evidence and carrying its own weakest link. If only two are well supported it shows two rather than padding the list, and the question box stays on the same screen. The same records ground 14 interviewable AI agents, one per person in Engineering, Finance, People & Ops and Marketing; they speak only from those records and invent nothing about anyone (see `DECISIONS.md`, decision 24).

Veloxa is a fictional B2B SaaS company in Bengaluru with 19 staff and about 66 customers. Its data room is contradictory: machine-generated call transcripts that mishear names and figures, and system exports that are better but have quirks of their own. Nobody will say which source is right. Deciding what to trust is the problem this system is built around.

## Status

Day 3 of 5 — 18 November 2026. Build in progress: phases 1-5 of 12 are done (foundation, data model, ingestion, evidence retrieval, question answering). There is no user interface yet. The Veloxa release pack is not in the repository (see `DECISIONS.md`, decision 8); it is read in with the ingestion command.

Run so far in the development environment only, with Python 3.13. A fresh-clone check comes with the setup phase.

```
pip install -r requirements.txt
python -m pytest
python -m app                     # server on http://127.0.0.1:8000, see /health
python -m app.ingestion ingest PATH --release-day 2026-11-16
python -m app.ingestion status
python -m app.ingestion aliases data/aliases_reviewed.csv
python -m app.ingestion conflicts data/conflicts_reviewed.json
python -m app.retrieval "atlas release date" --as-of 2026-11-18
python -m app.answering "How many employees do we have?" --as-of 2026-11-18
```

## Documentation

| File | Contents |
| --- | --- |
| `ARCHITECTURE.md` | Data model, trust ladder, conflict registry, point-in-time behaviour |
| `ASSUMPTIONS.md` | Assumptions, dated, with confidence and what would overturn them |
| `TRANSCRIPT_NOTES.md` | Suspected mishearings and contradictions, with evidence and conclusions |
| `DECISIONS.md` | Choices that could be defended either way, and what each costs |
| `AI_LOG.md` | What was delegated to AI, where it was wrong, and what changed |
| `voice_notes/` | Written responses to the CEO voice notes T6a onward |