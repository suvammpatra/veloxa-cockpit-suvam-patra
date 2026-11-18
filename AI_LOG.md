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
