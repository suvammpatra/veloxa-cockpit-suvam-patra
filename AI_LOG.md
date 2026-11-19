# AI_LOG.md

AI assistants were used throughout: to read the data room, to draft documentation, and to cross-check one another. Each entry below records a specific point where machine output was wrong, what replaced it, and how it was caught.


| Date | What I was establishing | What AI returned | Where it was wrong | What the record now says | How it was caught |
| --- | --- | --- | --- | --- | --- |
| 2026-11-16 | The name of the project | "Veloxa CEO Cockpit", carried over from a summary I had written earlier | Both the challenge email subject and the candidate brief say "Veloxa CXO Cockpit" | "Veloxa CXO Cockpit" everywhere in the repository | My own check. I noticed the name was wrong and had it corrected |
| 2026-11-16 | How many staff Veloxa has | 180, taken from the brief's prose and T1's "one-eighty" | Both board updates say Team 19 and Employee_Master has 19 rows; T1's own quote contradicts the prose in the same bullet | 19 staff | A second AI pass over the board updates |
| 2026-11-16 | The confidence level on the ARR conflict | High confidence, while also proposing that T2's "forty-eight" was monthly revenue in lakhs, which reconciles with the board | A hypothesis that reconciles the figure cannot sit underneath a high-confidence rejection of it | Medium, with the monthly-revenue hypothesis as the leading explanation and marked untestable | A review pass over the draft |
| 2026-11-16 | How to date export rows for point-in-time queries | The 31 Oct export date used as the release date | It would leak Day 1 data into answers about earlier dates; 31 Oct is when IT produced the files, not when I could know them | Three dates on every record: as_of, exported_on, released_on | A review pass over the draft |
| 2026-11-16 | Whether the three similarly named Sapphire vendors are one vendor | One vendor group covering all three, because that is what I had instructed | Sapphire Residency Hotel's line sits on cost centre SAL-TRV and is narrated "Sales offsite", not summit cost | Two summit vendors summing to Rs.10,03,000, plus the hotel kept separate | The drafting AI re-reading the cost-centre column against its own instruction |
| 2026-11-16 | What is known on 17 November in a point-in-time query | "Only Day 1 sources" | Day 2 is released on 17 November | Day 1 and Day 2 sources on 17 November; Day 1 only on 16 November | A review pass over the draft |
| 2026-11-16 | The tense of references to ASSUMPTIONS.md and DECISIONS.md | Present-tense claims that content was "logged" and "recorded" when neither file existed | Neither file existed at the time of writing | Future tense, and the files were then created | A review pass over the draft |
| 2026-11-16 | Whether to document a run command on Day 1 | A README promising "python run.py" and an install step | Nothing it described was runnable; no code exists on Day 1 | Draft rejected. README left as the repository default; setup and test instructions wait for code and are due before the Friday freeze | My decision not to ship a command that could not run |

## Day 2 (2026-11-17)

My work today: reading the Day 2 sources, working out the T3 contradictions, the T6a response (`voice_notes/T6a.md`) and its product decisions, and the wording of the documentation edits I dictated during the day.

AI assistance (one AI coding assistant session):

- Applied my dictated edits to ARCHITECTURE.md (v1.1 and the Day 2 source rows), TRANSCRIPT_NOTES.md (the T3 rows and two paragraphs), ASSUMPTIONS.md (two rows), DECISIONS.md (decision 11) and README.md. It also typed two dictated edits into `voice_notes/T6a.md`: the paragraph under the section 5 table, and "3.9 to 3.1 in the Jul–Sep quarter" in row 2.
- While applying them, flagged two real problems: row 2 of T6a still cites "4.0 to 3.1" in its Evidence cell, and decision 11 keeps the engineer unnamed while TRANSCRIPT_NOTES.md and ASSUMPTIONS.md name P. Nair.
- At my request, reviewed the six docs against the Day 1 and Day 2 source files and corrected the factual errors below. It did not open the Day 3 or Day 4 packs. It added 10.eml and 11.eml to the evidence on the unnamed engineer; the conclusion and its M rating are still mine. It drafted the wording of decisions 12-16 from my T6a reasoning and the decision 8 status note, and reviewed T6a without editing it.
- After I approved it, wrote the release-time change into ARCHITECTURE.md and decision 2: `released_on` becomes a 10:00 IST timestamp, with a 09:59 versus 10:00 test. The 10:00 rule comes from the challenge email.
- At my request, applied the seven T6a corrections from its review to `voice_notes/T6a.md`: 3.9 not 4.0, four of five responding, 11.eml added, the full 06.eml line, no November date for T1, Atlas moved past 15 September with no new date, no hint at which engineer, and no claim that the letter names Atlas. The reasoning and conclusions in T6a are still mine.
- The review also found two Day 1 errors whose origin is not recorded: the GL Apr-Sep total in ARCHITECTURE.md (Rs.2,34,07,530; the 28 lines sum to Rs.2,34,37,530) and "Kayka" filed under T2's Summary instead of its Key points. Both are corrected in place and not counted below.

| Date | What I was establishing | What AI returned | Where it was wrong | What the record now says | How it was caught |
| --- | --- | --- | --- | --- | --- |
| 2026-11-17 | Applying the Day 2 documentation edits | Applied my dictated wording as given, checking it for internal consistency but not against the source files | Several lines did not match the files: "Liver" and "twenty-two open roles" are in T3's Key points, not its Summary; the GL payroll line (Apr-Sep) was described as matching "the register", which covers Jan-Mar; the leave register says "Exam", not CFA; the Keka Hire tracker was assumed complete; the resignation letter was called "signed" (it has a typed name only) | Corrected in ARCHITECTURE.md, ASSUMPTIONS.md and TRANSCRIPT_NOTES.md | The AI assistant's source review later the same day, at my request |
| 2026-11-17 | Whether the Sid paragraph in TRANSCRIPT_NOTES.md names three sources | Said it named only two | The paragraph opens with T3's "Sid from marketing" line, then the letter and Employee_Master: three | Paragraph unchanged | The AI assistant, re-reading T3 during the source review |

## Day 3 — 18 November 2026

My work today: reading the Day 3 pack and writing eight observations. (1) Marketing readiness is not product readiness. (2) The Atlas delay has several causes, not just headcount. (3) Reliability work competed with Atlas in August. (4) Compare the VP's account with Jira by chronology and scope. (5) Priya's ownership email is a signal, not a conclusion. (6) The SRE contractor may be an operational dependency. (7) T6b needs effective-dated reporting lines. (8) The cockpit's value is linking departments. These observations are mine. I gave them to the AI assistant as hypotheses to check against the sources.

Sources used: T4_Head_of_Marketing_Call.docx, T5_VP_Engineering_Call.docx, T6b_CEO_Voice_Note.docx, Jira_Export_ATLAS.xlsx, Incidents_Aug-Oct_2026.xlsx, OnCall_Rota.xlsx, git_log.csv, Atlas_Launch_Kit_v1.pdf, Invoice_PIS-114.pdf, Email_Printouts.pdf, 04.eml, 05.eml, 08.eml and 09.eml, cross-checked against the Day 1 and Day 2 files.

AI assistance (one AI coding assistant session):

- Extracted the .docx and .xlsx files with scripts and computed the Jira, incident and rota figures by script. Read git_log.csv and the three PDFs from copies I supplied in the session. Git facts are cited by commit SHA and were not counted by script.
- Checked each observation against the sources. Confirmed with changes: 1 (the press note is still a draft, so marketing is not fully ready either, and the kit's owner left on 31 Oct); 2 (the records show a request to talk about ownership and work concentrated on one person, not an ownership dispute); 3 (shown for August; Sneha's hardening tickets are still To Do at 31 Oct); 6 (the contractor has filled one rota slot every week since mid-August; SEV1s stopping after August is a correlation only); 7 (Keka gives no reporting history, and the privacy floor would need dated membership). Confirmed: 5 and 8 (8 is a product judgement, not a fact). Revised: 4. T5 is undated, so it cannot be placed before or after the 2 Sep Jira change; the gap that can be dated is between the 6 Oct board update ("feature-complete") and Jira. None rejected.
- Drafted the Day 3 sections appended to TRANSCRIPT_NOTES.md, ASSUMPTIONS.md and ARCHITECTURE.md (section 15). Existing text was not changed. The design changes it proposed for T6b were reported to me for a decision and are not in DECISIONS.md. It did not write or edit my T6b response, and did not open the Day 4 pack.

No AI error reached the documents today that I know of. Its own review changed two draft lines before they were written: T6b was first called a summary (it is a transcription), and the tickets Sneha paused on 24 Aug were first taken to be her four ATLAS-5 tickets (08.eml does not name them). The first statistics script crashed twice on header rows and was fixed before any figure was used.

Later on 18 Nov, after my review: at my request the AI assistant appended decisions 17-23 to DECISIONS.md as I approved them, appended the six tests I approved to the ARCHITECTURE.md Day 3 addendum as a backlog, and replaced three references to the tool by its product name in the Day 2 entry above with "the AI assistant". The decisions are mine.

## Build — 18 November 2026 (Phases 1-3)

My work: the 12-phase build plan and its rules, and three decisions at the Phase 2 checkpoint. (1) Keep refusing department payroll totals before 31 Oct; do not assume membership back to join dates. (2) Agents are evidence-only (DECISIONS.md 24). (3) Update the documentation at every verified checkpoint.

AI assistance (one AI coding assistant session):

- Wrote all code and tests for Phase 1 (foundation), Phase 2 (data model) and Phase 3 (ingestion), and ran them: 7, then 32, then 61 tests passing. Started the server once to check `/health`.
- Raised the department payroll limit and the persona conflict with ARCHITECTURE.md section 8 as questions. Both decisions are mine.
- Checked the Phase 3 date rules against text extracts of the Day 1 files from earlier sessions: board send dates 8 Jul and 6 Oct, the letter 15 Sep, and 31 Oct from the README. The release packs were not run through the pipeline.
- Drafted ARCHITECTURE.md section 16 and the wording of decision 24 from my instructions, and updated the README Status section, which I allowed.

| Date | What I was establishing | What AI returned | Where it was wrong | What the record now says | How it was caught |
| --- | --- | --- | --- | --- | --- |
| 2026-11-18 | A test that the CRO shows as vacant | A test that could not fail | It checked a value the test had just set | Replaced by a test of a confirmed move: the old manager on 30 Nov, "CRO (vacant)" on 2 Dec | The AI assistant's own review, before the Phase 2 checkpoint |
| 2026-11-18 | Reading "Exported 31-Oct-2026" from a sheet title | A date pattern that missed it | A character range in the pattern left out the hyphen | Fixed before any file was ingested; the Keka test covers it | A failing Phase 3 test |
| 2026-11-18 | Phase 3 test expectations | Two wrong expectations | One asked about March as known in March, before anything was released; one assumed a file order | Tests corrected; the code was right | Failing Phase 3 tests |

## Build — 18 November 2026 (Phase 4)

My work: approved Phase 3 and decided three follow-ups. (1) A reviewed alias file with only the Day 3 mappings I approved, including the GitHub no-reply address at M, and Snehal kept unresolved. (2) Change the README sentence on invented agent detail. (3) Keep differing Keka snapshots as conflicts.

AI assistance (one AI coding assistant session):

- Wrote `data/aliases_reviewed.csv` from the approved rows in ASSUMPTIONS.md (Day 3), and changed the one README sentence I approved.
- Wrote the Phase 4 retrieval code and its 36 tests, and ran the full suite: 97 tests passing. To check that the tests can fail, it switched off the privacy, time and duplicate filters one at a time; each made a test fail. The code was then restored.
- Drafted ARCHITECTURE.md sections 16.5 and 16.6, and updated the README Status section.

| Date | What I was establishing | What AI returned | Where it was wrong | What the record now says | How it was caught |
| --- | --- | --- | --- | --- | --- |
| 2026-11-18 | Example search output for the Phase 4 report | Examples from a test database built twice | The demo script loaded the same synthetic files twice, so every hit showed a duplicate and there was a second conflict | Demo rebuilt once; examples rerun. No project file affected | The AI assistant, reading the output before reporting |
| 2026-11-18 | The search command's summary line | "3 shown of 2" | The count of hits included conflict sides added after the limit | The line now gives matches shown and conflict sides separately | Same review |

## Build — 18 November 2026 (Phase 5)

My work: approved Phase 4 and set the Phase 5 scope. That is the answer pipeline, the eight typed question types, purpose decided by the backend, the five-field format, confidence by rule, an optional LLM that cannot add facts, and the list of tests.

AI assistance (one AI coding assistant session):

- Wrote `app/answering` (question reading, classification, handlers, confidence, citation checks, optional LLM wording), the `GET /api/ask` endpoint, the `python -m app.answering` command, and 53 tests. Full suite: 150 passing.
- To check that the tests can fail, it broke five guards one at a time: citation checks, purpose, open-conflict confidence, the individual-pay refusal and the corroboration rule. Each made a test fail. The code was then restored.
- Proposed two rules for my review: corroboration counts only when two systems state the same fact, and a policy refusal is High (ARCHITECTURE.md 16.7); and the incident coverage rule (ASSUMPTIONS.md, Build).
- Drafted ARCHITECTURE.md section 16.7 and updated the README Status section.

| Date | What I was establishing | What AI returned | Where it was wrong | What the record now says | How it was caught |
| --- | --- | --- | --- | --- | --- |
| 2026-11-18 | Reading dates in a question | A pattern for "22 Aug" and "Aug 22" | "August 2026" was read as 20 August. A script edit also wrote two control characters into the pattern instead of word boundaries | Pattern fixed; tests for month, day, ISO and range forms | Failing incident and payroll tests |
| 2026-11-18 | Confidence for launch readiness | High: "two independent systems agree" | Jira and the kit support different parts of the answer, not the same fact | Corroboration counts only when two systems state the same fact | The AI assistant, reading sample answers before reporting |
| 2026-11-18 | Ownership statements | Quoted 09.eml's Subject line and the kit's "Owner:" label | A header or a label is not a statement | Header and label lines are skipped when quoting | Same review |
| 2026-11-18 | Incidents on a day before the first incident | "Not covered" | A day in the month of the first incident is inside the export | Coverage by the file name's months, else whole months | A failing test for the 15.7 backlog item (no incident on 22 Aug IST) |

## Build — 18 November 2026 (Phase 5 follow-ups)

My work: approved Phase 5 and decided four follow-ups. (1) Approved both confidence rules: corroboration only for the same fact from independent systems, copies never independent, and a refusal's High shown as policy confidence, not a business answer. (2) Approved the incident coverage assumption provisionally, on condition that a file name never overrides the file's contents, and that "none recorded" stays apart from "coverage unavailable". (3) Asked for a reviewed conflict registry, using only conflicts documented in ARCHITECTURE.md, validated, never fabricated or resolved automatically. (4) Left ARCHITECTURE.md sections 2 and 14 untouched, and kept the evidence registry deferred.

AI assistance (one AI coding assistant session):

- Wrote `data/conflicts_reviewed.json` (C-ARR, C-BURN, C-ATLAS-DONE, all open), the loader and its `conflicts` command, the noted-date rule in retrieval, the grouped two-sided conflict text in answers, the confidence basis, and the incident coverage rule. Added 19 tests. Full suite: 169 passing.
- To check that the tests can fail, it broke five registry guards one at a time: the date check, the one-record rule, the noted-date gate, the open/resolved wording, and the no-overwrite rule. Each made a test fail. The code was then restored.
- Ran the conflict command against the empty project database: all three conflicts were rejected as "not ingested", and nothing was written.
- Drafted ARCHITECTURE.md 16.8, decisions 25 and 26, and the revised ASSUMPTIONS.md row.

| Date | What I was establishing | What AI returned | Where it was wrong | What the record now says | How it was caught |
| --- | --- | --- | --- | --- | --- |
| 2026-11-18 | Which conflicts the file may hold | C-ARR, C-BURN and C-ATLAS-DONE, with match words from ARCHITECTURE.md and TRANSCRIPT_NOTES.md | Not wrong so far, but not yet checked against the real pack: the board match words (such as "ARR" with "5.8") are taken from how ARCHITECTURE.md writes the figures | The loader rejects any side that does not match one real record | Open until the pack is ingested and the file is loaded |
| 2026-11-18 | A test of point-in-time conflicts | Expected no conflicts at all before the tracker's release | A different test conflict, already visible then, was correctly attached | The test checks only the conflict that must be hidden | Failing test, read before changing anything |

## Build — 19 November 2026 (Day 4: real source-pack validation, Days 1-3)

My work: set the Day 4 order (real-data validation first, then agents, worry list, point-in-time checks and frontend planning), and the rule that nothing is claimed as validated on real data until it is.

AI assistance (one AI coding assistant session):

- Found the Day 1-3 release packs on the machine. It read only those three days into a disposable database outside the repository, and did not open the Day 4 pack. No pack file was changed, and the project database was not touched.
- Ran ingestion, the reviewed aliases and the reviewed conflicts, then the checks in ARCHITECTURE.md 16.9. All 39 files were handled (36 ingested, 3 templates skipped, 0 failed). All three reviewed conflicts matched their intended records.
- Fixed six defects that only the real files showed, with 8 new tests. Full suite: 177 passing. The new leak test was checked to fail without its fix.
- Drafted ARCHITECTURE.md 16.9.

| Date | What I was establishing | What AI returned | Where it was wrong | What the record now says | How it was caught |
| --- | --- | --- | --- | --- | --- |
| 2026-11-19 | The launch kit on real data | "Status lines could not be read" | The Phase 5 reader expected "Item: Status"; the real kit is a two-column table | The reader also reads the table layout: 3 of 5 items ready, press note Draft, launch date TBC | Real-data run |
| 2026-11-19 | GA statements on real data | One email; the board updates were missing, and ledger rows appeared in recorded-by mode | The search included "date", Jira rows used up the result limit, and "GA" matched "GADS" | Board updates quoted; no ledger rows | Real-data run |
| 2026-11-19 | Conflicts on a feature-complete question | All three conflicts in the answer | One board page is a side of all three | Only conflicts about the question change an answer; the others are listed as notes | Real-data run |
| 2026-11-19 | Privacy of 09.eml | The evidence endpoint served the printed copy, which holds 09.eml's text | Copies were left out of search and citations, but not out of that endpoint | The endpoint no longer returns copies | The AI assistant, reading the printout text during validation |

## Build — 19 November 2026 (Day 4: approved follow-ups)

My work: approved four decisions from the real-data run. (1) Read the invoice date 01/10/2026 as 1 October 2026, keeping the string. (2) Add a reviewed contractor record for S. Patil, kept apart from employees and from Snehal and Sneha. (3) Add the T6b change as announced, with no effective date, and keep Nikhil Bose's current line. (4) Add Pria and Vicky as reviewed aliases at M, and leave Sid unresolved.

AI assistance (one AI coding assistant session):

- Implemented the four decisions with no schema change: a day-first date rule for invoices only, `data/org_reviewed.json` with its loader and `org` command, pending-change wording in the manager and department answers, and two alias rows.
- Added 14 tests and updated the alias-file test for the two new rows. Full suite: 191 passing. One guard was broken on purpose to check its test fails; the code was then restored.
- Re-ran Days 1-3 into a fresh disposable database. All reviewed files loaded against the real records. The project database was not touched.
- Drafted ARCHITECTURE.md 16.10 and the ASSUMPTIONS.md row for the invoice date.

| Date | What I was establishing | What AI returned | Where it was wrong | What the record now says | How it was caught |
| --- | --- | --- | --- | --- | --- |
| 2026-11-19 | Tests for the contractor record | A test line meant to check the contractor's role and invoice | Because of operator precedence it checked only that some evidence was attached, and the payroll check ran before the contractor was loaded | Both checks rewritten; they now check the role, the invoice text, and payroll after loading | The AI assistant, rereading tests that passed on the first run |

## Build — 19 November 2026 (Phase 6: agent profiles)

My work: approved the Day 4 follow-ups and set the Phase 6 rules: exactly the 14 agents in ARCHITECTURE.md 8; profiles from evidence only, each fact with evidence, confidence and dates; "Not established" where records are silent; decision 23 enforced, including T5's remark about "Pria"; no route around the privacy and purpose controls.

AI assistance (one AI coding assistant session):

- Wrote `app/agents` (the roster, the profile builder and a command) and `app/api/agents.py`. Proposed the fixed list of eligible record systems in ARCHITECTURE.md 16.11, for my review.
- Added 16 tests on a synthetic 19-person company. It includes a transcript line about late nights, late commits, a purpose-limited email and its copy, payroll amounts, a leave type, a resignation reason, a near-duplicate name and a contractor. One negative test plants ineligible facts and checks they are dropped. Full suite: 207 passing.
- To check the tests can fail, it switched off four guards one at a time: the eligibility check, citation validation, conflict handling and pending changes. Each made a test fail. The code was then restored.
- Built all 14 profiles from Days 1-3 in the disposable database and checked them for leaks and failed checks; none were found.
- Drafted ARCHITECTURE.md 16.11 and updated the README Status section.

| Date | What I was establishing | What AI returned | Where it was wrong | What the record now says | How it was caught |
| --- | --- | --- | --- | --- | --- |
| 2026-11-19 | A test for snapshot dates | A test named as if it checked a known-now question about an earlier date | No such time frame exists; the test only checked recorded-by mode before the export | Renamed to what it checks: nothing is established before the Keka export was recorded | The AI assistant, rereading tests that passed on the first run |

## Build — 19 November 2026 (Phase 6 follow-up: decision 23 in answers)

AI assistance: while checking Phase 6 on real data, the AI assistant found that "Has Pria been doing late nights?" made the answer engine quote T5's remark. It added a refusal for working-hours questions about a named person (ARCHITECTURE.md 16.12), and one test. Full suite: 208 passing. It also reported, without changing it, that a raw person-filtered search can still return that transcript paragraph.

| Date | What I was establishing | What AI returned | Where it was wrong | What the record now says | How it was caught |
| --- | --- | --- | --- | --- | --- |
| 2026-11-19 | Decision 23 outside profiles | The Phase 5 refusal covered commit-time questions only | A question about "late nights" fell through to search and quoted the transcript | Working-hours questions about a person are refused | The AI assistant, probing the answer engine on real data |

## Build — 19 November 2026 (decision 23 boundary review and runbook)

My work: asked for a review of the profile source allowlist as a proposed decision, an investigation of how T5's remark about "Pria" can be reached, and a manual testing runbook built from the real code.

AI assistance (one AI coding assistant session):

- Mapped every route to the T5 paragraph on the disposable real-data database. The answer engine quoted it for 10 of 16 phrasings. The raw evidence layer serves it as open evidence.
- Added the three-layer rule in ARCHITECTURE.md 16.13 and updated the refusal text. Added 29 tests: every phrasing before and after the alias review date, the backstop, narrow detection, and a pinned test of the raw-layer boundary. Full suite: 237 passing. Each of five layers was switched off once to check its test fails; the code was then restored.
- Drafted the allowlist decision for my review. It is not yet in DECISIONS.md.
- Checked the runbook by running the app against a copy of the empty project database, and against the disposable database. Startup and every read left both files byte-for-byte unchanged. Port 8000 on this machine is used by another service, so the runbook uses port 8010.

| Date | What I was establishing | What AI returned | Where it was wrong | What the record now says | How it was caught |
| --- | --- | --- | --- | --- | --- |
| 2026-11-19 | Whether 16.12 closed decision 23 in answers | 16.12 refused working-hours questions about a named person | Indirect and reworded questions still quoted the remark ("What has Pria been doing?", "Who works late?", "Does Priya stay late?") | Three-layer rule in 16.13 | The AI assistant, testing 16 phrasings on real data |
| 2026-11-19 | The runbook's first live check | Requests sent to port 8000 | Another service on this machine answers on 8000; the cockpit could not bind there | The runbook sets VELOXA_PORT=8010 | The health reply came from a different service |

## Build — 19 November 2026 (Phase 6 review: disclosure rules)

My work: approved decision 27 with its scope as drafted. Approved two privacy requirements: remarks about a named person's working hours (decision 28), and personal circumstances (decision 29). Set the test list, and the rule that stored records stay unchanged.

AI assistance (one AI coding assistant session):

- Wrote `app/retrieval/disclosure.py` and applied it to search, evidence detail, citation checks, conflict quotes and the answer engine. Added an operational exemption for on-call, rota, incident, deploy and release wording, in both the rule and the refusal. Drafted decisions 28 and 29 and ARCHITECTURE.md 16.14.
- Added 37 tests in `tests/test_disclosure.py`: every path for both remarks, alternate searches and questions, operational questions, other sentences of a record, a sentence that cannot be separated, a table row, and unchanged stored records. Updated three 16.13 tests that pinned the old boundary. Full suite: 274 passing. Each of seven layers was switched off once to check a test fails; the first run showed the row rule had no failing test, so one was added.
- On the disposable real-data database: 4 of 1,841 rows affected; no withheld text on any path; stored evidence hash unchanged. The project database file hash is unchanged.

| Date | What I was establishing | What AI returned | Where it was wrong | What the record now says | How it was caught |
| --- | --- | --- | --- | --- | --- |
| 2026-11-19 | Withholding the leave register's marriage row | Sentence splitting at full stops | "Employee: F." stayed visible beside the marker, because "F." was read as a sentence end | Table rows are one unit; an initial does not end a sentence | Failing evidence-detail test |
| 2026-11-19 | Tests for search and answers | Checks for single words such as "wedding" | The search echoes the asker's own words, and the refusal text says "late nights", so the checks failed on correct output | Tests check fragments of the withheld sentences | Reading the failures before changing code |

## Build — 19 November 2026 (Decision 30: Git commit records)

My work: wrote decision 30 and its seven rules, set the required tests, and asked for a review of exam leave and of the payroll question routing.

AI assistance (one AI coding assistant session):

- Added the `on_call` handler (rota only; uncertainty without a rota row), a shared commit-record rule, its use in the search fallback and `statements()`, and an engine backstop that does not depend on the classification. Added a narrow payroll-run routing rule. Appended decision 30 as given, ARCHITECTURE.md 16.15 and two assumption rows.
- Added 33 tests in `tests/test_commit_records.py` and four commit rows to the shared test company. Full suite: 307 passing. Each of five safeguards was switched off once, and a test failed each time.
- On the disposable real-data database: no Git citation on 25 questions where the rule applies; three repository-history questions still used git_log.csv; stored evidence and commit fingerprints unchanged. Reviewed the exam leave row and proposed no new rule.

| Date | What I was establishing | What AI returned | Where it was wrong | What the record now says | How it was caught |
| --- | --- | --- | --- | --- | --- |
| 2026-11-19 | Wording of a one-week on-call answer | "for the week of 17 Aug 2026: week of 17 Aug 2026: ..." | The week was named twice | One week is named once; a day inside a week says which week it falls in | Reading the real-data answers |
| 2026-11-19 | A test that "Who ran payroll in February?" finds the right record | A check that the question leaves the payroll handler | It passed with "no record": the test transcript has no date, so the February filter left it out | The test also asks "Who ran payroll?" and checks the quoted sentence | Printing the test answers before trusting a first-time pass |

## Build — 19 November 2026 (Phase 7: CEO worry list)

My work: set the Phase 7 scope, candidate areas, hypotheses to check, safeguards, tests and stop condition. Required that no LLM generates or ranks a worry, and that fewer than three is shown rather than padding.

AI assistance (one AI coding assistant session):

- Checked each hypothesis against the Day 1-3 records on the disposable database. Wrote five candidate rules, three evaluated-and-excluded areas, and a deterministic score. Every worry goes through the answer engine's existing citation, disclosure, conflict and confidence checks. Added `/api/worries`, a one-page interface at `/`, and `python -m app.worries`. Drafted ARCHITECTURE.md 16.16.
- Added 19 tests in `tests/test_worries.py` with their own synthetic company and privacy traps. Full suite: 326 passing. Each of eight safeguards was switched off once, and a test failed each time.
- On the disposable real-data database: worry lists at seven time frames; no employee name, Git, payroll, leave or withheld text at any of them; API equal to engine; evidence and commit fingerprints and the project database hash unchanged.

| Date | What I was establishing | What AI returned | Where it was wrong | What the record now says | How it was caught |
| --- | --- | --- | --- | --- | --- |
| 2026-11-19 | Records that mention a failing service | A search for the service name excluding Jira and PagerDuty | It returned a git_log row, so a commit author and time could appear in a worry | Worry rules leave Git out of every search, and the engine rejects any worry citing a Git record | Privacy test on the synthetic company |
| 2026-11-19 | A test that payroll lines never become a cost worry | A rising payroll series in the test ledger | One payroll date was built as an invalid date and dropped, so the test passed without testing anything | Dates written out; payroll rises faster than any other cost | Switching the payroll exclusion off and seeing no test fail |
| 2026-11-19 | A note when the kit's owner can't be linked | A note quoting the owner's name as written | It put a first name into a worry | The note no longer quotes the name | Name scan of the real-data worry lists |
| 2026-11-19 | Expected order in the ranking test | An order guessed before running | The guess was wrong: the test ledger's last cloud bill was over 92 days old, so recency was 0 | The test pins the order the formula gives, with the scores | Reading the scores before changing the test |

## Build — 19 November 2026 (Phase 8: temporal and end-to-end validation)

My work: approved the worry list scoring and eligibility rules as decisions 31 and 32; set the AWS check, the ten validation areas, the user journey and the stop condition.

AI assistance (one AI coding assistant session):

- Appended decisions 31 and 32. Checked the six AWS ledger lines and the arithmetic. Made the cost rule break at a missing month, disclose netted credits and quote the narration; 2 tests added.
- Wrote the real-data checks (47) and the end-to-end journey (13), run on disposable databases. Added the agent picker and an empty page icon, which the journey needed. Full suite: 328 passing. Drafted ARCHITECTURE.md 16.17.

| Date | What I was establishing | What AI returned | Where it was wrong | What the record now says | How it was caught |
| --- | --- | --- | --- | --- | --- |
| 2026-11-19 | A past profile for someone who has left | A check expecting him active as recorded by 15 Oct, then departed as recorded by 31 Oct | No Keka record existed by 15 Oct, and 31 Oct is his last day, so active was right | The check expects no record by 15 Oct, active on 31 Oct and departed from 1 Nov | Reading each failure against ARCHITECTURE.md 8 and 16.3 before changing code |
| 2026-11-19 | No withheld text in any output | A sentence split of the withheld rows | The split cut a leave row at an initial, and the fragment matched other visible rows | The check uses the disclosure rules' own units | Reading the reported leak |
| 2026-11-19 | Raw search still serves Git rows | A search for a word not in any commit message | It found nothing, which looked like a failure | The check searches a word the messages contain | Reading the commit messages |

## Build — 19 November 2026 (Day 4: voice notes T6c and T6d, submission readiness)

My work: inspected the Day 4 folder and set the expected behaviour for T6c and T6d: no resignation ranking, no private messages, the report kept unverified, no identity or date assumed. Set the tests and the Day 5 readiness checks.

AI assistance (one AI coding assistant session):

- Ingested the two voice notes into a disposable database. Added the T6c refusals and the continuity view, the T6d reported-event record and the impact answer, and a fix to conflict relevance. Drafted decisions 33 and 34, ARCHITECTURE.md 16.18, Day 4 transcript notes and two assumptions. Updated README.md.
- Added 33 tests in `tests/test_t6cd.py`. Full suite: 361 passing. Each of five new safeguards was switched off once, and a test failed each time. Real-data checks: 47 of 47. Browser journey: 17 of 17. A clean copy installed, passed all tests and rebuilt the demo database identically. Repository audit found no secrets, source-pack files or payroll data.

| Date | What I was establishing | What AI returned | Where it was wrong | What the record now says | How it was caught |
| --- | --- | --- | --- | --- | --- |
| 2026-11-19 | Which conflicts belong in the T6d answer | The existing relevance rule | "Notice period two months" matched C-BURN's "two point two lakhs a month" | Number and time words alone don't make a conflict relevant | Reading the real-data answer |
| 2026-11-19 | The name in T6d before the alias is known | The first capitalised unknown word | It picked "Bad" from "Bad news" | The name next to the departure word is used | Reading the 09:59 answer |
| 2026-11-19 | The ranking refusal | A speculation check placed first | T6c went to "speculation", because "Deepa" counted as a named person | Ranking language is checked before a single person's intentions | Failing T6c tests |
| 2026-11-19 | Recording T6d in the reviewed file | Rewriting the file through a JSON library | It reformatted every existing record | The file was rewritten by hand, with the earlier records as they were and one new section | Reading the diff before going on |
| 2026-11-19 | A provenance test | An assertion that could never fail | It checked nothing | It compares the stored hash with the file's own hash | Re-reading the test after it passed first time |

## Build — 19 November 2026 (final review: leave records, T6d record, submission checks)

My work: approved decisions 33 and 34 in principle with two clarifications; asked for the org file diff to be checked, the leave-row exposure to be investigated and fixed at its cause, and the voice-note requirement to be checked against the brief.

AI assistance (one AI coding assistant session):

- Checked the org file against its 18 Nov version, as recorded in the session, without Git. Compared the HR and organisation records and Priya Nair's profile before and after T6d.
- Found 17 leave rows open in search, evidence detail and answers. Fixed the rule in the shared disclosure layer, not with a word list. Added 20 tests and four leave rows to the test company. Drafted the decision 29 clarification and ARCHITECTURE.md 16.19, and appended the approval of 33 and 34.
- Checked the brief: a response to every CEO voice note is a must-have, so T6c and T6d responses are missing from `voice_notes/`. Drafts were given for review only; no file was created.
- Full suite: 381 passing. Real-data checks: 47 of 47. Browser journey: 19 of 19. Clean-copy setup re-run after the change.

| Date | What I was establishing | What AI returned | Where it was wrong | What the record now says | How it was caught |
| --- | --- | --- | --- | --- | --- |
| 2026-11-19 | Which leave rows users could see | Earlier checkpoints named only the exam row as open, and the decision 30 review proposed no rule for it | 17 rows were open, including five personal half-day rows for one engineer. Decision 11 already calls a leave pattern personal data | Every leave row is withheld, whatever its type | A probe of every output path on the real records, asked for in the final review |

## Build — 19 November 2026 (voice-note responses T6c and T6d)

My work: approved the clarifications to decisions 29, 33 and 34, and the T6c and T6d responses with their safeguards. Asked for the leave-pattern evidence to be removed from T6a.

AI assistance (one AI coding assistant session):

- Wrote `voice_notes/T6c.md` and `voice_notes/T6d.md` from the approved drafts, quoting the transcripts exactly. T6c keeps "slag messages" as transcribed, with the reading as Slack stated as an interpretation. T6d calls "Pria" a probable, not established, match; labels the Jira figures as the 31 October export; and works out no last working day.
- Removed the `Leave_Register` sentence from concern 2's evidence in `voice_notes/T6a.md`, and added a dated note there. No application code uses the leave pattern, and no worry or answer cites leave rows.
- Appended the approvals to DECISIONS.md. No application logic or source data changed. Full suite re-run.

## Build — 19 November 2026 (setup and run workflow)

My work: diagnosed the empty dashboard with the AI assistant, located the release pack, and asked for a reliable setup, load, start and verify workflow without changing business logic.

AI assistance (one AI coding assistant session):

- Read the running server's working directory and settings, and inspected the databases read-only. The server was serving an empty database that its own startup had created. Hash-compared the release pack folder with the validated copy: 41 files, identical.
- Wrote `setup.ps1`, `setup-demo-data.ps1`, `start.ps1`, `verify.ps1`, `scripts/common.ps1` and `app/readiness.py`. Added a test isolation fixture and 22 tests. Updated `.env.example` and README.md; drafted ARCHITECTURE.md 16.20.
- Ran the workflow for real: the demo database was loaded once, with the expected counts and the validated fingerprint. `verify.ps1` passed, and the browser journey passed 19 of 19. Full suite: 403 passing.

| Date | What I was establishing | What AI returned | Where it was wrong | What the record now says | How it was caught |
| --- | --- | --- | --- | --- | --- |
| 2026-11-19 | Whether the server runs from `.venv` | A check comparing the listening process's executable with `.venv` Python | On Windows the venv launcher starts the base interpreter, so the check would have failed a correct server | The launcher is matched in the command line or as the parent process | Inspecting the running process |
| 2026-11-19 | The agent count in `verify.ps1` | `@(Invoke-RestMethod ...)` | Windows PowerShell 5.1 returns a JSON array as one object, so it counted 1 | The response is piped through `ForEach-Object` first | The first `verify.ps1` run |
| 2026-11-19 | Configuration defaults | Treating the example values (`data`, port 8000) as unset | It hid a wrong setting instead of reporting it | Explicit values are used; a data folder inside the repository is refused with a message | Review before the first run |
