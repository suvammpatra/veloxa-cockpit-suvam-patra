# DECISIONS.md

These are choices that could reasonably be defended either way, recorded with what each one costs.

## 1. Conflicts are stored, never silently resolved

- Decision: Each conflict is stored as an object holding both claims, a resolution and a confidence.
- Alternatives rejected: Keeping the higher-trust claim and discarding the other; overwriting older claims when newer data arrives.
- Why: A discarded claim cannot be cited, explained or revisited when a later drop overturns the resolution.
- What it costs me: More tables, longer answers, and every query has to check the registry.

## 2. Three dates on every record

- Decision: Every record carries `as_of` (the period described), `exported_on` (when the source produced it) and `released_on` (when I was allowed to know it).
- Alternatives rejected: A single date; two dates (`as_of` and `released_on`).
- Why: The 31 Oct export date is not the day I could know the data. Two dates conflated them and would leak data into point-in-time answers. "What did I know on 17 November" and "what had the company recorded by 1 August" need different fields.
- What it costs me: Every parser must set three fields, and some values (transcript dates) are unknown and must be marked as such.
- Update 2026-11-17: `released_on` is now an IST timestamp, not a date. The email says each pack counts as released at 10:00 IST. So a question at 09:59 on 17 Nov must not see Day 2. The three fields stay as they are.

## 3. Payroll is aggregate-only with a five-person floor

- Decision: Payroll lives in a restricted store that emits only totals over at least five people, plus exception flags with no money values. Individual salaries are unanswerable by construction.
- Alternatives rejected: A prompt instruction telling the model not to reveal salaries; filtering salary figures out of responses after they are generated.
- Why: The CFO's rule in T2 is absolute. Prompt wording can be talked around; a store the cockpit has no handle to cannot.
- What it costs me: Only the company total and Engineering (5) are answerable. Finance, Marketing and People & Ops totals are refused, including the CFO's own.

## 4. The payroll overpayment names the person and dates, never the amount

- Decision: The cockpit reports Rahul Verma's February payroll issue with his name, join date, days payable and the email trail, but no amount.
- Alternatives rejected: Suppressing the issue entirely; reporting it with the amount.
- Why: The matter is already in his own email and needs a named owner to close. The amount would reveal his pay.
- What it costs me: In a 19-person company, naming him still hints at pay. This is a judgement call, not a guarantee.

## 5. 14 of 19 staff become agents

- Decision: Engineering, Finance, People & Ops and Marketing staff become agents. The CEO is the user. Sales and Support have no agents but stay in the model as Persons.
- Alternatives rejected: Agents for all 19; dropping Sales and Support from the model entirely.
- Why: The four departments named in the brief total exactly 14. Keeping the other five as Persons preserves manager chains, the SAL-TRV cost centre and headcount.
- What it costs me: Questions about Sales and Support can be answered from records but not by interview.

## 6. The email governs where it and the brief disagree

- Decision: The challenge email's compressed 5-day format, with no live sessions, takes precedence over the brief's 10-day format.
- Alternatives rejected: Following the brief.
- Why: The email is the instruction specific to this run.
- What it costs me: If a reviewer grades against the brief, anything that only the brief requires will be missing.

## 7. One Python process with FastAPI and SQLite, LLM behind a flag

- Decision: A single process, SQLite storage and one start command. The LLM is behind a flag so the system and tests run offline with no API key.
- Alternatives rejected: Docker; a separate PostgreSQL server; an agent-orchestration framework.
- Why: The build faces a fresh-clone test on unknown hardware, in five days, by one person, and is graded on explainability. Every extra moving part is a setup failure risk and something I have to explain without help.
- What it costs me: No concurrency to speak of, and anything that would need a framework has to be written plainly by hand.

## 8. The data room is committed to the repository

- Decision: The data room files are committed so a fresh clone runs with no manual steps.
- Alternatives rejected: Requiring the reviewer to place the files manually.
- Why: The fresh clone must run with no manual steps. Against this, the challenge email's ground rules (section 7) say "Please don't share materials or collaborate with other candidates."
- What it costs me: Exposure of the materials if the repository is public. Mitigation: the app reports a clear error if data/ is absent, so the files can be removed without breaking setup silently.
- Status 2026-11-17: under review, not acted on. No data room file has been committed or pushed (checked 17 Nov). The email requires a public repository, so the exposure above is certain, not conditional. Nothing in the email or the brief permits republishing the release pack: section 7 asks candidates not to share materials, and the email footer says no part of the message may be shared with a third party without the sender's written consent. A public repo during 16-20 Nov would give each day's pack to anyone, other candidates included, and the data being synthetic does not change that. Recommendation: keep data/ out of git, have the start command stop with a clear message naming the zip if data/ is empty, and ask Hiyaku in writing whether committing the pack is allowed. Commit it only if they say yes. Cost: the fresh-clone run needs one manual step, unzipping a pack the reviewer already has, unless they agree.

## 9. Sapphire Residency Hotel is a separate vendor

- Decision: "Sapphire Events Pvt Ltd" and "Saphire Event Mgmt" resolve to one vendor. Sapphire Residency Hotel is kept separate.
- Alternatives rejected: Merging all three spellings into one summit supplier.
- Why: The hotel's line is on SAL-TRV and narrated "Sales offsite". The two MKT-EVT lines alone sum to the Rs.10,03,000 summit.
- What it costs me: If the hotel turns out to be the same legal entity, per-vendor spend is split across two records. Total spend is unchanged.

## 10. Evidence references mirror the Evidence_Index template

- Decision: Evidence refs (E001 onwards) use the Evidence_Index columns: file, sheet/page/row, fact in my words, entities, date as written and normalised to IST, and confidence.
- Alternatives rejected: A bespoke citation scheme.
- Why: One table feeds both the cockpit and any printout, and reviewers already know the template's shape.
- What it costs me: E-numbers mean nothing without the index, and they must never be reused as later drops add rows.

## 11. The worry list may describe a retention risk without naming the person

- Decision: Where a concern rests on one individual's private pattern - leave, engagement - the list states the business risk, the team and the evidence type, and names the person only if that person is named in a document intended to be read (a resignation letter). The Head of People's unnamed engineer stays unnamed.
- Alternatives rejected: Naming the engineer because the CEO is entitled to know; suppressing the concern entirely.
- Why: The CFO's rule protects personal data from reaching the CEO. A leave pattern is personal data. But a retention risk the CEO cannot see is worse than one she can, so the risk is surfaced and the name is withheld.
- What it costs me: The CEO may act on a risk without knowing who to speak to. Mitigation: the item names the manager to ask - Vikram - not the employee.

## 12. The worry list is the landing view (T6a)

- Decision: The cockpit opens on the worry list. The question box stays on the same screen.
- Alternatives rejected: A scheduled morning brief pushed to her; keeping the question box as the landing view with the worry list one click away; a dashboard.
- Why: T6a: "When I open it, it should just tell me what to worry about." She asked for something she sees on opening it, not a push. The brief already requires the view, and quotes her: "I don't want another dashboard nobody opens."
- What it costs me: The first screen depends entirely on the ranking. A wrong first item is the first thing she sees.

## 13. Three is a cap, not a quota

- Decision: Show up to three items. If fewer than three are well supported, show fewer and say so. Never fill a slot to reach three.
- Alternatives rejected: Always three; a third item drawn from weaker evidence.
- Why: She said "Top three", but a made-up third item defeats the point of an evidence-backed list (T6a section 3).
- What it costs me: Some days the list may show one or two items, which can look broken. What counts as "well supported" is not defined in code yet.

## 14. Items below the top three stay reachable

- Decision: Items ranked fourth and lower are listed below the top three, not dropped.
- Alternatives rejected: A hard cut at three.
- Why: An important concern should not disappear because it ranks fourth (T6a section 3).
- What it costs me: A longer page, and she may stop reading at three anyway.

## 15. Ranking is deterministic

- Decision: Items are ranked by rule on evidence strength, impact (money or people affected) and trend (T6a section 4). The same records always give the same order, and each item shows why it sits where it does.
- Alternatives rejected: Letting the LLM rank items.
- Why: An order that changes between visits with no new data tells her nothing, and an LLM ranking cannot be explained or tested.
- What it costs me: The weights are mine and arguable. A tie-break rule is needed and not chosen yet.

## 16. The data date is always shown

- Decision: The worry list shows the date of the latest record it rests on. For the exports supplied so far that is 31 October 2026.
- Alternatives rejected: Showing no date; showing today's date.
- Why: The records stop at 31 October 2026 (T6a section 3). Presenting them as live would mislead her.
- What it costs me: She will see that the data is weeks old.