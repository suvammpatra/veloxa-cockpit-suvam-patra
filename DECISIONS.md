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

## Day 3 — 18 November 2026

Decisions 17 to 23 were approved on 18 November 2026. Evidence is in the Day 3 sections of TRANSCRIPT_NOTES.md, ASSUMPTIONS.md and ARCHITECTURE.md (section 15).

## 17. Reporting relationships are effective-dated (T6b)

- Decision: Who reports to whom, and which department sits under which leader, is stored as rows with a start date, an end date, a status and a source. A move closes the old row and adds a new one. Nothing is overwritten.
- Alternatives rejected: A manager field that the next export overwrites; a full copy of the org chart for every day.
- Why: T6b: "Make sure the thing doesn't break when we move people around." A question about August must still get the August answer after a move. Employee_Master is one snapshot with no history.
- What it costs me: Every org question needs an as-of date. Keka shows the lines on 31 Oct only; earlier lines are "unknown" unless another record shows them, never back-filled to the join date.

## 18. T6b stays pending until a source confirms the date

- Decision: Marketing reporting to the CRO is stored as an announced change with no effective date. The current org does not change until a source confirms the date. The cockpit shows the pending change next to the current line.
- Alternatives rejected: Applying it from "next month"; ignoring it until it happens.
- Why: The note is undated, so "next month" has no anchor, and she says the date is "still finalising". T4 gives no date either.
- What it costs me: For a while the cockpit shows Marketing under the CEO while she thinks of it as under the CRO.

## 19. The CRO is a vacant role until the holder is confirmed

- Decision: Roles are stored apart from the people who hold them. Marketing can report to "CRO (vacant)" before anyone is named.
- Alternatives rejected: Waiting for a name; attaching the role to the current Sales Lead.
- Why: No CRO is in Employee_Master or Hiring_Tracker. Picking a person would invent a fact.
- What it costs me: One more table, and some answers that say "vacant".

## 20. The privacy floor uses membership on the query date

- Decision: The five-person floor (decision 3) is checked against who was in the group on the date asked. The differencing rule also applies across dates: the same group label on two dates counts as two groups, and if their members differ by fewer than five, comparing the totals is refused.
- Alternatives rejected: Checking group size on today's org only.
- Why: Moving one person between two months makes the change in a total close to that person's pay. Sales has 2 people and Marketing 2 after 31 Oct, so a CRO group would hold 4, or 5 with the CRO.
- What it costs me: More refusals after each reorg. A CRO-level payroll total may be refused or sit right on the floor.

## 21. Sneha and Snehal are never merged; git and Jira aliases need evidence

- Decision: Sneha and Snehal stay two people. A git author email or Jira initials map to a person only through an alias row that cites the record supporting it, with a confidence.
- Alternatives rejected: Fuzzy name matching; mapping by spelling alone.
- Why: The rota puts Sneha and Snehal in the same week, so they cannot be one person. Merging them would move incidents between an employee and a contractor. Priya Nair commits under two addresses, so counting by email alone would split her work.
- What it costs me: Some names stay unresolved, and alias rows need review.

## 22. Contractors are tracked separately from employee headcount

- Decision: A contractor is a Person with no Emp ID, worker type "contractor", and the records that show them (invoice, rota, incidents). Headcount answers say 19 employees and list contractors separately.
- Alternatives rejected: Leaving contractors out; counting them as staff.
- Why: Keka excludes contractors and the board says Team 19. But the on-call contractor has covered one of the two rota slots every week since mid-August and costs Rs.1,20,000 a month plus GST (Invoice PIS-114).
- What it costs me: "How big is Engineering?" has two answers, and each must say which one it is.

## 23. Commit times are not a worry signal; 09.eml is used only for ownership questions

- Decision: Priya Nair's late-night and weekend commit pattern is never shown as a CEO worry item or as an employee performance signal. 09.eml may be cited when answering a question directly about Atlas ownership, and never to infer resignation, dissatisfaction or personal motive.
- Alternatives rejected: Showing the pattern as a workload or retention risk; excluding 09.eml entirely.
- Why: Commit times are not hours worked or output, and they are one person's private pattern (decision 11). 09.eml asks to talk about ownership and says nothing about her intentions.
- What it costs me: A real workload problem may be under-signalled. The Atlas worry item can still show ticket concentration without naming anyone.

## Build — 18 November 2026

Decision 24 was made on 18 November 2026, at the Phase 2 build checkpoint.

## 24. Agents are evidence-only

- Decision: The 14 agents have no invented persona. They speak only from records: responsibilities, projects, workload signals where the records support them, history, and what is unknown. No invented personality, personal detail, opinion, motivation, activity or relationship. Workload signals stay within decisions 11 and 23. This replaces the persona layer in ARCHITECTURE.md section 8, and the README line that invented detail is logged as an assumption.
- Alternatives rejected: An invented persona, labelled as invented and logged in ASSUMPTIONS.md (ARCHITECTURE.md section 8 as written).
- Why: The agents represent the company as its records show it. This is a product decision, not a technical limit.
- What it costs me: The agents are less lifelike. They will say "the records don't show that" more often.

## Phase 5 checkpoint — 18 November 2026

Decisions 25 and 26 were approved on 18 November 2026, at the Phase 5 checkpoint.

## 25. Corroboration means the same fact; a refusal's confidence is about the policy

- Decision: Two records corroborate only when independent systems state the same fact. Records that support different parts of one answer do not, and copies of one source never count as independent. A policy refusal may show High confidence, but only as confidence in the policy decision. It is labelled so, and it says the business question was not answered.
- Alternatives rejected: Counting any two systems that support an answer as agreement (the first Phase 5 draft).
- Why: A kit status and a Jira date are two facts, not one fact seen twice. A refusal's High must not read as a high-confidence business answer.
- What it costs me: Fewer answers reach High. Most rest on one export and stay Medium.

## 26. Conflicts come from a reviewed file and are never resolved automatically

- Decision: Conflicts documented in ARCHITECTURE.md are loaded from a reviewed file. Every side must match one ingested record, or the conflict is not loaded. Status changes only by review. Loading never overwrites a stored conflict.
- Alternatives rejected: Finding conflicts in prose automatically; loading a conflict whose records are not found; marking a conflict resolved because a working position exists.
- Why: A conflict is a claim about records. It must point at records that exist, and settling it is a judgement for a person.
- What it costs me: The file must be kept by hand. A conflict is invisible until its records are ingested and the file is loaded.

## Phase 6 review — 19 November 2026

Decisions 27, 28 and 29 were approved on 19 November 2026, at the Phase 6 review.

## 27. Agent profiles cite only a fixed list of record systems

- Decision: An agent profile states facts only from Keka HRMS, Keka Hire, Jira, PagerDuty and the on-call rota (labelled as a copied plan). It may also cite two reviewed exceptions: the record behind an announced organisation change, and the sides of a stored conflict that touches the person's records. Call transcripts, voice notes, emails, git commits and their times, the leave register, the pulse survey, payroll and letters are never used in profiles. Every cited key must also pass citation validation at the profile's time frame.
- Scope: Agent profiles only (app/agents, /api/agents). Search, the evidence endpoints and the answer engine keep the general rules: restricted sources, purpose limits and roles, plus the decision 23 rule in ARCHITECTURE.md 16.13. This decision does not change decision 24; it states which records a profile may speak from.
- Alternatives rejected: Using every open record that names the person; using emails and transcripts as quoted statements.
- Why: A profile describes a person. Statements, opinions, personal circumstances and pay must not become facts about someone, and an exact allowlist is easier to check than a list of exclusions.
- What it costs me: Finance, People & Ops and Marketing profiles hold Keka facts only. Work shown only in emails or calls does not appear.

## 28. A remark about a named person's working hours is never disclosed

- Decision: A sentence that pairs a working-hours phrase (late nights, weekends, overtime, working late, staying late, working nights, hours worked, working pattern) with a name is withheld from every user-facing output. That covers search results and snippets, evidence detail, citations and quotes, answers and agent profiles. The stored record and its provenance are kept unchanged; this restricts disclosure, not storage. The working-hours question refusal stays. A sentence about on-call, the rota, incidents, deploys or releases is operational and is not withheld; questions about those are not refused. The first case is T5's remark about "Pria".
- Alternatives rejected: Leaving the raw evidence layer open, as in ARCHITECTURE.md 16.13; withholding all of T5.
- Why: Decision 23 bars working-hours patterns as a signal about a person. A raw search, or an evidence page, that returns such a remark under a person's name shows that signal just as an answer would.
- What it costs me: The cockpit can no longer show that remark to anyone, even to check it. A remark that names someone and also mentions on-call or an incident is not withheld.

## 29. Personal circumstances in source records are not disclosed

- Decision: A sentence about a family event or a health matter is withheld from every user-facing output, as in decision 28. The terms are: wedding, marriage or married, honeymoon, divorce, funeral or bereavement, pregnancy, maternity, paternity, illness, medical, hospital, surgery, sick. A table row is one unit, so a person's name is never left beside a withheld cell. A sentence that cannot be separated from surrounding business detail is withheld whole. The rule is sentence-level: other sentences of the same record stay visible. Nothing is inferred from withheld text: no leave type, relationship status or other private detail. The stored records are unchanged. Future worry signals follow the same rule. The first case is T2's remark about an absence for a wedding.
- Alternatives rejected: Withholding all transcripts, all emails or all of T2; a broad list of personal words.
- Why: These details are not needed for a business decision about the company. An absence can still be known from operational records, such as 01.eml's "since Fatima is out".
- What it costs me: Business detail that shares a sentence with a personal remark is lost. On the real records, T2 paragraph 8 also names Kartik's planning role. Sick and marriage leave rows are withheld whole. The term list is fixed, so a personal remark in other words is not caught.

## Git commit records — 19 November 2026

Decision 30 was made on 19 November 2026, after the Phase 6 review.

## 30. Git commit metadata cannot establish individual working activity or on-call status

- Decision:
  1. Git commit authors and timestamps are never used to establish who was on call, working hours, working patterns, individual activity, workload, productivity or individual performance.
  2. A Git commit timestamp is evidence only that a commit was recorded at that time. It is not evidence that the author was actively working at that time.
  3. Questions about on-call assignments use the on-call rota or another explicitly approved operational source. At this date the rota (OnCall_Rota.xlsx) is the only approved one.
  4. If the approved operational evidence is unavailable, the answer returns uncertainty. Git commit records are not substituted.
  5. Git records stay available for technical questions about repository history, provided the answer does not infer individual working activity or performance.
  6. This decision does not delete, modify or globally suppress Git records. Search and evidence detail keep their existing behaviour.
  7. It is enforced in the answering engine and in every fallback path, not only in question classification.
- Alternatives rejected: Withholding Git records everywhere; relying on question classification alone; using PagerDuty responders or statements in place of the rota.
- Why: A commit time shows when a commit was recorded, not who was working or on call. The search fallback answered "Who was on call in the week of 17 Aug 2026?" with git_log.csv rows (an author and a commit time), so the classifier rule from decision 23 was not enough.
- What it costs me: A question that names a person, or asks "who", is never answered from Git, even "Who authored this commit?". An on-call question about a week the rota does not cover gets no answer. Enforcement is in ARCHITECTURE.md 16.15.

## Worry list — 19 November 2026

Decisions 31 and 32 were approved on 19 November 2026, after the Phase 7 review. They settle what decisions 13 and 15 left open.

## 31. Deterministic worry list scoring

- Decision: score = 3 × impact + 2 × evidence strength + recency + persistence.
  - Impact: 1 to 3, set by each candidate rule.
  - Evidence strength: the computed confidence, Low 1, Medium 2, High 3.
  - Recency: 2 when the latest supporting record is within 31 days of the as-of date, 1 within 92 days, otherwise 0.
  - Persistence: 0 to 2, by the documented candidate rules (ARCHITECTURE.md 16.16).
  - Tie-break: higher impact, then higher strength, then the rule key.
  - Record counts do not contribute to the score.
- Alternatives rejected: Ranking by an LLM (decision 15); counting records as a measure of severity.
- Why: Decision 15 required a fixed, explainable order and left the weights and the tie-break open. The same records always give the same order, and each worry shows its score parts.
- What it costs me: The weights are a judgement. A worry with Low confidence, because of an open conflict, can still rank high on impact.

## 32. Worry list evidence eligibility

- Decision:
  - Every worry passes citation validation, temporal filtering, the disclosure rules, conflict handling and decision 30.
  - At least one supporting source is not a transcript.
  - No Git record may support a worry.
  - Conflicts are visible on the worry, and its confidence reflects them.
  - Missing evidence never creates a worry.
  - Up to three primary worries are shown, and three is never forced.
- Alternatives rejected: Filling the list to three; worries resting on transcripts only; worries supported by commit records.
- Why: Decision 13 left "well supported" undefined in code. These rules make it checkable, and they keep the list from becoming a view of individual people.
- What it costs me: Some days show one or two worries. A concern known only from a call, such as an announced organisation change, appears only as a note on a related worry.

## Day 4 voice notes — 19 November 2026

Decisions 33 and 34 record how the Day 4 voice notes T6c and T6d are handled. The expected behaviour was set on 19 November 2026; both decisions are for review.

## 33. A CEO-reported personnel event is an unverified assertion

- Decision:
  - A personnel event reported in a voice note or call, such as T6d's "Pria resigned this morning", is stored as a reported event: status "reported unverified", the name and any notice period exactly as written, and its source.
  - It never changes a person, an employment status, an exit date or any HR record. No last working day is worked out from a reported notice period.
  - The name links to a person only through the reviewed aliases known at the time frame. The answer states the alias, its confidence and the date it became known.
  - An impact answer uses only Jira assignments, responsibilities documented in rung 1-4 records, release dates and stored conflicts. It never uses Git, the leave register, 09.eml or transcripts as support.
  - A report is known from its pack's release time. With no recording date, it is never "recorded by" any date.
- Alternatives rejected: Marking the person as leaving; working out a last day from "two months"; reading "Pria" as Priya Nair without saying how.
- Why: A voice note is the CEO's account, not an HR record; decision 18 treats announced organisation changes the same way. The board needs the dependency picture now, with the identity and the dates kept as open questions.
- What it costs me: The cockpit can't confirm the resignation or give a last day. Until HR records it, every answer about it is uncertain.

## 34. No resignation-risk ranking and no private messages

- Decision:
  - The cockpit does not rank, score or predict who is likely to leave. This holds in any wording, with or without names, and from any signal: emails, calls, leave, commit activity, hours or sentiment.
  - It does not read or show private messages such as Slack or WhatsApp, which are not in the records.
  - One person's approval (T6c: "Deepa says it's fine") is not consent from the people concerned, and it does not change the rule.
  - It offers instead an aggregate continuity view from the records: confirmed departures, requisitions, contractors, and work that rests on one person. No one is named or scored.
- Alternatives rejected: An "at risk" list built from leave and commit patterns; a ranking hidden inside the continuity view; accepting the stated approval.
- Why: Decisions 11 and 23 already bar inferring intentions and using commit times about people. A ranking applies those inferences to everyone at once. Private messages are outside the records and outside what employees expect to be read.
- What it costs me: The CEO does not get the list asked for in T6c. The continuity view shows where the company is exposed, not who might leave.

## Final review — 19 November 2026

Decisions 33 and 34 were approved in principle on 19 November 2026. The approval adds two points, recorded here without changing the entries above:

- Decision 33: A reported personnel event stays an unverified report until an independent record confirms it, such as an HR letter or a Keka update. A confirmation is loaded as its own record. The report itself is never upgraded, and its source and known-from time are kept.
- Decision 34: The workforce continuity view must not become an indirect individual-risk score. It shows only documented facts. It never combines signals about one person (leave, engagement, messages, commit activity or reports) into a view of that person.

## Clarification to decision 29: leave records

- Decision: Every row of a leave record is withheld from user-facing output, whatever its leave type.
  - Decision 29 withheld a leave row only when its type was a family or health term. Casual, earned, personal, exam and relocation rows stayed visible, with the person's name.
  - Decision 11 already treats a leave pattern as personal data, and no decision permits showing leave rows.
  - The stored rows are unchanged. An absence can still be known from operational records, as decision 29 says.
- Alternatives rejected: Adding "exam", "relocation" and "personal" to the word list; withholding only the leave type and leaving the name and dates.
- Why: A leave row says why a named person was away. The type is the personal detail whatever its value. Five "Personal (half day, PM)" rows for one engineer in September form a pattern about one person.
- What it costs me: The cockpit can no longer show who was on leave when, even for planning. A worry that rests on a leave pattern, as decision 11 allows, can't cite the rows.

## Approvals — 19 November 2026

Approved on 19 November 2026:

- The clarification to decision 29: every leave-register row is withheld whole, whatever its leave type.
- The decision 33 clarification: a CEO-reported personnel event stays unverified until separate evidence confirms it, and it never updates HR status automatically.
- The decision 34 clarification: the workforce continuity view never combines individual-level signals into an indirect resignation-risk score.

The voice-note responses `voice_notes/T6c.md` and `voice_notes/T6d.md` were approved with two safeguards. T6c keeps "slag messages" as transcribed, and any reading as "Slack messages" stays qualified. T6d keeps "Pria" as a probable, not established, match; labels every Jira figure as the 31 October snapshot; and works out no last working day. Concern 2 in `voice_notes/T6a.md` no longer cites the September leave pattern as evidence.