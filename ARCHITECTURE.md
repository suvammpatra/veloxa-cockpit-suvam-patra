# ARCHITECTURE.md: Veloxa CXO Cockpit

## 1. What this is

The CEO asks one question and gets a short answer in the five Connection Worksheet fields, citing its records, stating confidence, and saying when sources disagree or are silent. The same records ground 14 interviewable agents.

Veloxa has 19 employees: both board updates say 19, and Employee_Master lists VX001 to VX019. The brief's "180" is not used. Ananya Rao is the user. Fourteen are agents: Engineering 5, Finance 3, People & Ops 3, Marketing 3. The other five (Ananya, Manoj Kumar and Divya Reddy in Sales, Imran Siddiqui and Kavya Narayan in Support) stay in the model as Persons, so manager chains, the SAL-TRV cost centre and headcount all reconcile; they simply have no agent.

The brief describes a 10-day format with live reviews; the challenge email sets a compressed 5-day version with no live sessions, and the email governs where they differ.

Sibling logs: ASSUMPTIONS.md, TRANSCRIPT_NOTES.md, DECISIONS.md and AI_LOG.md.

Stack: one Python process, FastAPI and SQLite, one start command. The LLM sits behind a flag; with it off, the system and tests run offline with no API key.

Not building: dashboards or a multi-page UI; revenue, net burn or profit figures (no export contains revenue); any view of an individual's pay; live connectors, authentication or multiple users; Docker or a database server; agents living past 31 Oct 2026 (stretch, deferred).

## 2. Sources and trust ladder

The ladder is a tiebreak, not a blanket ranking: each source is first authoritative for its own domain. Rahul Verma's join date comes from Keka, not the higher-ranked payroll register, because Keka owns dates.

| File | System | Authoritative for | Rung | Why |
| --- | --- | --- | --- | --- |
| GL_Export_Apr-Sep_2026.xlsx | Zoho Books | Costs by vendor and cost centre, Apr-Sep 2026; selected cost centres, no revenue | 1 | Posted transactions; the Apr-Sep monthly payroll line equals the March 2026 register total to the rupee, but FS enters both, so it is a consistency check, not independent corroboration (section 9) |
| Payroll_Register_Jan-Mar_2026.xlsx | Payroll workbook (pre-Keka) | Days and amounts paid per person; restricted | 1 | System of record for pay |
| Board_Update_Apr-Jun_2026.pdf, Board_Update_Jul-Sep_2026.pdf | Management | ARR, customers, burn, runway, headcount, plans | 2 | Dated and deliberate, but lagged and written to persuade |
| Employee_Master.xlsx | Keka HRMS | Identity, department, manager, join and exit dates; no contractors | 3 | System export, but one snapshot, no history |
| Resignation_Letter_SM.pdf | Employee document | One person's stated reason for leaving, dated | 3 | Dated and deliberate, but it is their own account |
| Leave_Register.xlsx | Google Sheet, People & Ops | Leave taken, dates, approver | 3 | Hand-maintained, so transcription risk |
| Hiring_Tracker.xlsx | Keka Hire | Requisitions, status, status date | 3 | System export, but T3 says hiring runs on "Liver" (Lever) and no Lever export exists |
| Pulse_Survey.xlsx | Culture Amp | Team-level engagement scores, quarterly | 3 | Instrument-collected, but team-level only and all comments suppressed |
| 01.eml, 02.eml, 03.eml, 06.eml, 07.eml, 10.eml, 11.eml | Email | Who said what, when | 4 | First-hand, but selected and partial |
| T1_CEO_Kickoff_Call.docx, T2_CFO_Call.docx, T3_Head_of_People_Call.docx | MeetNotes AI | Leads and opinions; never the sole basis for a figure | 5 | Machine-generated, undated, misheard; T3's good audio quality did not stop its headcount figures being wrong |

The brief and README define scope; the three templates are working files, never evidence. Other README folders are not yet released.

## 3. Data model

Person is keyed by Emp ID. Transcripts never carry one, so every transcript name passes through Alias before it can attach to a fact.

```
Department 1---* Person (Emp ID) *---1 Person [manager]
Alias *---1 {Person | Vendor | Project}
Vendor 1---* FinancialTxn [cost centre, amount, as_of, exported_on, released_on]
SourceRecord 1---* Claim *---1 {Person | Vendor | Project | Department}
Claim *---* Conflict
```

FinancialTxn is keyed by voucher plus ref. Claim holds subject, attribute, value, unit, the three dates in section 4, source locator and extractor (rule or LLM). Project has one row: Atlas (routing engine v3).

Alias examples: "Pria" to Priya Nair (VX007); "Kartik" to Karthik Subramanian (VX010); "Fatima Shaikh" to Fatima Sheikh (VX014, Keka spelling); "Joho books" to Zoho Books; "Kayka" to Keka. "Vicky" to Vikram Menon (VX004) is medium confidence. [ASSUMPTION] He is the only Vikram in Employee_Master, but the nickname is unconfirmed. "Sapphire Events Pvt Ltd" and "Saphire Event Mgmt" resolve to one vendor: their two MKT-EVT lines (Rs.5,42,800 and Rs.4,60,200) make the Rs.10,03,000 summit. "Sapphire Residency Hotel" is kept separate: its Rs.38,940 line is a sales offsite on SAL-TRV, not summit cost.

## 4. Temporal model

Every Claim and FinancialTxn carries three dates:

| Date | Meaning |
| --- | --- |
| `as_of` | The period the record describes |
| `exported_on` | When the source produced it: posting date, email Date header, board send date, or the file export date when nothing finer exists. Where only a file export date exists, that date is the snapshot's own time, not the time each row was recorded; any historical answer resting on such a file discloses that. |
| `released_on` | When I was allowed to know it: 10:00 IST on the day the folder is released (challenge email, section 3) |

Treating the 31 Oct export date as a release date would leak data into point-in-time answers (section 11).

| Case | as_of | exported_on | released_on |
| --- | --- | --- | --- |
| Board update Apr-Jun | Apr-Jun 2026 | 8 Jul 2026 | 16 Nov 2026 |
| Board update Jul-Sep | Jul-Sep 2026 | 6 Oct 2026 | 16 Nov 2026 |
| AWS, Google Ads lines | Month before posting ("previous month") | Posting date | 16 Nov 2026 |
| Emails | Date header | Date header | 16 Nov 2026 |
| Export snapshots (Employee_Master, GL, payroll) | Per row or per file | Row date where present, else 31 Oct 2026 | 16 Nov 2026, the Day 1 release. 31 Oct is when IT produced the files, not when I could know them |
| Transcripts | Unknown | Unknown | Day released to me |

`released_on` is stored as an IST timestamp. The table shows only the date.

Periods are stored as date ranges. [ASSUMPTION] The fiscal year runs April to March and November 2026 is in FY27: the payroll sheet is named "Payroll Q4" for Jan-Mar 2026, which only works on an April-March year, so T2's "twenty-six" is the mishearing.

So the 37% AWS rise, Rs.1,81,200 to Rs.2,48,310, describes March to August usage.

## 5. Ingestion and reconciliation pipeline

| Stage | What happens | Guessing allowed |
| --- | --- | --- |
| Register | Each file becomes a SourceRecord | No |
| Parse | Deterministic parser per type; every row, page or paragraph gets a locator | No |
| Resolve | Names map through Alias | Yes, for transcript names and vendor spellings, with confidence; unresolved stays unresolved |
| Extract | Exports become Claims by rule; emails and transcripts may use LLM extraction, reviewed and committed so offline runs match | Yes, for transcript units and meaning, flagged, never auto-accepted |
| Reconcile | Claims on the same subject, attribute and period are marked agrees, bounds, or conflicts | No; conflicts are stored, not settled |

Export amounts, dates and IDs are never imputed. Later drops re-run Register through Reconcile and re-score existing Claims; nothing is overwritten in place, so a Day 3 export that contradicts a Day 1 claim appends a Conflict rather than replacing the record.

## 6. Evidence and citation model

An evidence ref (E001 onwards) points to file, sheet/page/row, the fact in my words, entities, date as written and normalised to IST, and confidence. It mirrors the Evidence_Index template, so any printout comes from the table the cockpit reads.

Every response has exactly these fields, in order:

1. Question asked
2. Your claim (one sentence), ending with confidence H, M or L
3. Chain of evidence (refs, in order), in reasoning order
4. Weakest link, and why
5. What would change your mind

The worksheet implies this shape whether or not there is a session, and it forces every answer to name its weakest link and falsifier.

## 7. Conflict registry

A Conflict stores both claims, resolution, rule, confidence, what would overturn it, and status. Overturning appends; nothing is deleted.

| Field | C-ARR | C-BURN |
| --- | --- | --- |
| Claim A | T1: "forty-two crore, maybe forty-five"; T2: "forty-eight" at start of year | T2: "two point two lakhs a month"; T1: "two point two", no unit |
| Claim B | Board: Rs.5.8 Cr (Apr-Jun), Rs.6.1 Cr (Jul-Sep) | Board: Rs.46 L, then Rs.44 L. GL: Rs.2,34,37,530 Apr-Sep, Rs.39.0 L/month, 81% payroll |
| Resolution | Board's Rs.5.8-6.1 Cr stands as the only period-labelled figure. Leading hypothesis for the transcript: T2's "forty-eight" was monthly revenue in lakhs, not ARR; Rs.48 L x 12 = Rs.5.76 Cr, about 1% from the Apr-Jun board figure. T1's 42-45 crore has no reconciling reading yet. Untestable: no export contains a revenue line | Board. GL Rs.39.0 L/month corroborates within about 12%; the gap is unexported cost centres. T2 is impossible: payroll alone is Rs.31.75 L/month |
| Confidence | M | T2's figure rejected: H, since payroll alone is Rs.31.75 L/month. Board's Rs.44-46 L as the monthly burn: M, because it rests on one management document and the word "burn" is never defined in it |
| Would overturn | A revenue export or invoice register that disagrees with the board, or shows monthly revenue far from Rs.48 L | A full-ledger export materially different from the board, or a different finance definition of burn |

[ASSUMPTION] Board burn is gross outflow, because the GL's partial gross outflow is already the same order.

Also registered: 180 versus 19 people; the fiscal-year label (see section 4); Rahul Verma's days paid versus join date. Atlas GA ("on track for 15 September" in July, "moved" in October) is change over time, stored as two dated claims, not a conflict.

## 8. The 14 agents

| Department | Agents |
| --- | --- |
| Engineering | Vikram Menon, Priya Nair, Arjun Das, Sneha Kulkarni, Rahul Verma |
| Finance | Meera Iyer, Karthik Subramanian, Fatima Sheikh |
| People & Ops | Deepa Joshi, Rohan Banerjee, Lakshmi Pillai |
| Marketing | Nikhil Bose, Aisha Khan, Siddharth Mehta |

Three memory layers. Grounded facts: read-only Claims the agent is party to, plus their department's, filtered on both dates. Persona: invented life detail, each item to be logged in ASSUMPTIONS.md as invented, with the grounded facts it must not contradict. Conversation memory: per agent, never cited as evidence.

Invented persona detail and recorded fact are kept apart. When an agent speaks about its own life, invented material is marked as invented; when the cockpit answers a question about a person, it draws only on Claims that carry an evidence ref and never on persona. An answer that mixes the two labels which part is which.

Corroboration decides grounding. Fatima Sheikh's absence is supported three ways: T2 says she was out for her wedding, 01.eml records Karthik running February payroll "since Fatima is out", and the leave register shows 15 days of Marriage leave from 9 to 27 February 2026. Karthik's exam study is no longer transcript-only either: the leave register shows five days of Exam leave from 25 to 29 May 2026, so it is grounded fact rather than low-confidence persona. That the exam is the CFA still rests on T2 alone. Siddharth Mehta is employed through 31 Oct 2026 (Keka shows him in notice period, exit date 31 Oct) and gone from 1 Nov; any answer about him must state its as-of date. No agent can read the payroll store; finance agents decline pay questions in character.

## 9. Question to answer flow

1. Parse intent, entities, period and as-of date (default latest).
2. Privacy gate, before retrieval.
3. Resolve entities through Alias.
4. Retrieve Claims dated on or before the as-of date, on the field the question's mode needs (section 11).
5. Attach open Conflicts touching those Claims.
6. Compose. Numeric lookups are templated; the LLM, when on, only phrases retrieved Claims, and a validator rejects any number or name not in them.
7. Confidence by rule: H if rung 1-2 or two independent sources agree with no open conflict; M if one rung 3-4 source or a resolved conflict; L if transcript-only or an open conflict. The LLM cannot raise it.
8. If nothing supports an answer, say so and name the record that would.

Independence is checked before corroboration counts. The GL's Apr-Sep payroll line equals the March 2026 payroll register total to the rupee, and FS enters both, so their agreement is a consistency check within one process, not two independent sightings of the same fact, and it does not by itself justify H. Claims count as independent only when they originate in different systems or different people, not when one is derived from the other.

Refusal types: privacy, not computable (revenue realisation, net burn, profit), not yet released, unresolvable conflict.

The interface opens on the worry list (T6a; voice_notes/T6a.md): up to three items, each in the same five fields, ranked by a fixed rule so unchanged records give an unchanged order, with the date of the latest record shown and lower-ranked items still reachable (DECISIONS.md 11-16). The question box returning the five fields, an as-of date selector and an agent picker stay available. Items are drawn from the registry and rule-based flags: the AWS trend, the Rs.1,77,000 Cohere Recruiting advance while hiring is paused, the Rs.10,03,000 summit, the Atlas slip, the open payroll query; Day 2 adds the two backend reqs on hold since 12 Aug, the Engineering pulse drop and the marketing backfill.

## 10. Privacy boundary

The CFO's rule (T2): individual salaries never reach the CEO. Payroll lives in a separate SQLite file opened only by an aggregation module; the cockpit and agents have no handle to it. It emits totals over at least five people, and exception flags with no money values. [ASSUMPTION] Five, because three-person departments are otherwise exposed. Comparing totals whose membership differs by fewer than five is refused, to block differencing. Consequence: only the 19-person company total and Engineering (5) are answerable; Finance, Marketing and People & Ops totals are refused, including for the CFO. Department-level payroll needs the CFO to relax the rule or approve grouped reporting. A test scans every response for every amount in the register. No formal complementary suppression is implemented. The five-person floor plus the differencing rule is the whole control, and a long sequence of overlapping aggregate queries could in principle narrow it. This is recorded as a known limit, not claimed as airtight.

The Rahul Verma case is the tension: reporting it names him and implies his pay. Line drawn: the cockpit states the person, join date, days paid against days eligible, and the email trail ending "Will check and get back.", because the matter is already in his own email and closing it needs a named owner. It never states any amount paid or overpaid; that goes to the CFO. To be recorded in DECISIONS.md.

## 11. Point-in-time behaviour

Two modes, both filtering every Claim and Conflict, so a conflict invisible at X does not appear. "What did I know on X" uses `released_on`: on 16 Nov it returns only Day 1 sources, on 17 Nov Day 1 and Day 2, and before 16 Nov nothing. "What had the company recorded by X" uses `exported_on`: Apr-Jun ARR is unknown on 1 Jul (board sent 8 Jul); Atlas is "on track for 15 September" on 1 Aug and "GA moved" on 10 Oct; Siddharth Mehta is staff on 15 Oct and departed on 3 Nov.

A question with only a date is read as the end of that day, 23:59 IST. A question with a time is compared exactly. So at 09:59 on 17 Nov only Day 1 is known. From 10:00, Day 2 is known too.

## 12. Test strategy

28 questions with expected refs, figures, confidence and refusal type, run offline in one command.

| Category | Count | Example |
| --- | --- | --- |
| Fact lookup | 8 | Monthly payroll total; who manages Rahul Verma |
| Contradiction | 5 | "Is ARR 45 crore?"; "Are we 180 people?" |
| Refusal | 5 | "What does Rahul earn?"; "Finance payroll total"; "What is our profit?" |
| Point-in-time | 5 | Atlas status on 1 Aug versus 10 Oct; Siddharth Mehta on 15 Oct versus 3 Nov; 17 Nov at 09:59 versus 10:00 |
| Entity resolution | 3 | "What is Pria working on?" |
| Open items | 2 | "What payroll issues are unresolved?" |

## 13. Risks and open questions

| Item | Current position | Would change on |
| --- | --- | --- |
| Board burn definition | Gross outflow | A finance definition saying otherwise |
| Trust ladder order | As in section 2 | A later export contradicting GL or board in its own domain |
| Group-size threshold | Five | A leak found in testing |
| "Vicky" alias | Vikram Menon, medium | A record using the nickname |
| T2's "two backend roles" | [ASSUMPTION] The Cohere roles; same count and timing | A record naming different roles |
| Sapphire Residency Hotel | Separate vendor; not summit cost | Invoices or GSTIN showing it is the events firm |
| Apr-Sep payroll detail | GL total only | Keka payroll data released |
| Lever export | Never supplied; Keka Hire tracker may be partial | A Lever export showing more requisitions than the tracker |

## 14. Version log

| Version | Date | Note |
| --- | --- | --- |
| v1 | 2026-11-16 | Day 1 sources only |
| v1.1 | 2026-11-17 | Persona/record separation, source independence, stated privacy limits, export-date semantics, Day 2 corroboration |
| v1.2 | 2026-11-17 | Day 2 source check: GL total, payroll comparison periods, exam-leave, Lever and resignation-letter wording corrected; worry list as landing view (T6a); `released_on` as a 10:00 IST timestamp |

v1.2 covers Day 1 and Day 2 sources; Days 3-4 are not yet released.

## 15. Day 3 addendum (18 November 2026)

Sections 1-14 are unchanged. This addendum records what the Day 3 sources add. Design changes they point to are not made here and stay open until approved.

### 15.1 New sources

| File | System | Authoritative for | Rung | Why |
| --- | --- | --- | --- | --- |
| Jira_Export_ATLAS.xlsx | Jira | Atlas tickets: status, points, assignee initials, epics; the GA fix-version date and when it last changed | 3 | System export, but a status snapshot with no history; assignees are initials |
| git_log.csv | GitHub | Commits: author email, UTC time, repo | 3 | System record, but an email is not a person and a commit count is not output |
| Incidents_Aug-Oct_2026.xlsx | PagerDuty | Incidents: severity, UTC times, service, responder | 3 | System export; responders are first names only |
| OnCall_Rota.xlsx | Team wiki | Planned on-call weeks | 4 | A hand-copied table; its week of 17 Aug disagrees with 08.eml and INC-205 |
| Invoice_PIS-114.pdf | Vendor invoice | Contractor cost and service | 2 | Dated and formal; the earlier invoice it mentions (PIS-108) matches GL JV-0902 |
| Atlas_Launch_Kit_v1.pdf | Marketing document | Launch asset status on 21 Jul 2026 | 3 | Dated, but never updated in the records |
| 04.eml, 05.eml, 08.eml, 09.eml | Email | Who said what, when | 4 | As in section 2 |
| Email_Printouts.pdf | Email | Nothing new | - | The same eleven messages as the .eml files: a copy, not a second source |
| T4_Head_of_Marketing_Call.docx, T5_VP_Engineering_Call.docx, T6b_CEO_Voice_Note.docx | MeetNotes AI; auto-transcribed WhatsApp | Leads and opinions | 5 | Undated; T5 has a four-minute gap |

### 15.2 Identity

- Git author emails and Jira initials are new name forms. priya.n@veloxa.in and pnair@users.noreply.github.com both point to Priya Nair, the second at M. PN, RV, AD and SK are Priya Nair, Rahul Verma, Arjun Das and Sneha Kulkarni (ASSUMPTIONS.md, Day 3).
- Snehal is not in Employee_Master, which excludes contractors. Probably S. Patil of Patil Infra Services (M).
- Sneha (VX012) and Snehal share rota weeks, so they are two people. Under the section 5 rule an unresolved name stays unresolved; the two are not merged.

### 15.3 Time zones

Section 6 already normalises dates to IST. Day 3 is where it matters. Incidents ("Z") and git ("+00:00") are in UTC; emails carry +0530; Jira, the rota and the GL are dates only. Read as UTC, INC-205 falls on 22 Aug instead of 23 Aug IST, INC-209 and INC-211 each move a day, and commit 310404b46f lands on 2 Jun instead of 3 Jun. [ASSUMPTION] A rota "Week of" date is a Monday, and the week runs Monday to Sunday IST.

### 15.4 T6b: what the current model cannot do

- Section 3 holds one manager per Person, and Employee_Master is one snapshot with no history (section 2). A move would overwrite the old line, so questions about earlier dates would get the new org.
- T6b gives no effective date and names no CRO. No CRO exists in any record.
- The section 10 floor counts current members. After a move, two totals for the same team label could differ by one person.
- Agents, and the "manager to ask" in a worry item (DECISIONS.md 11), read the manager line.

How to handle each of these is not yet decided. Nothing above is changed.

### 15.5 Atlas status

- The GA date is a dated series, as section 7 says: 15 Sep (04.eml, 2 Jun; board, 8 Jul; Jira original), then 15 Dec (Jira, changed 2 Sep by "vikram"), then "moved" with no date (board, 6 Oct). The 15 Dec claim has exported_on 2 Sep, from Jira's "Last Changed".
- New conflict, C-ATLAS-DONE: the 6 Oct board update says "the engine itself is feature-complete"; Jira shows 5 core-engine stories not Done. Resolution: Jira for ticket status, the board for what the board was told. Confidence M, because a status snapshot cannot show a reopened ticket.
- T5's "on track" is stored with an unknown date. It cannot be placed before or after 2 Sep.

### 15.6 Worry list: Day 3 inputs

Atlas now spans departments, each part with its own evidence ref. Marketing: the kit has been mostly ready since 21 Jul, planned for 22 Sep, and its owner left on 31 Oct. Engineering: GA is 15 Dec, 115 of 233 points are open, and 62 of them are assigned to one person. Reliability: three SEV1s in August, Atlas performance work paused on 24 Aug (08.eml), and Sneha's four hardening tickets still To Do at export. People: two backend reqs on hold since 12 Aug, after the July condition in 04.eml was already missed. Finance: the on-call contractor at Rs.1,41,600 a month including GST. No SEV1 is recorded in September or October; that is a correlation with the contractor joining, not a measured effect.

### 15.7 Proposed test backlog

Approved on 18 Nov as backlog. Not counted in section 12; the existing test strategy is unchanged.

| Category | Test |
| --- | --- |
| Point-in-time | Atlas GA date known on 1 Sep versus 3 Sep (exported_on, from Jira's "Last Changed" of 2 Sep) |
| Point-in-time | Nikhil Bose's manager on 31 Oct (the CEO), and again once the T6b change is confirmed |
| Entity resolution | "What did Snehal do in August?" must not return Sneha's SEV1s |
| Contradiction | "Is the Atlas engine feature-complete?" must cite C-ATLAS-DONE |
| Refusal | Two payroll totals for one group whose membership changed by one person |
| Time zone | "How many incidents on 22 Aug?" gives 0 in IST; INC-205 is 23 Aug IST |

## 16. Implementation addendum (18 November 2026)

Sections 1-15 are unchanged. This addendum records what the code does at each verified build checkpoint. Where the code narrows a rule above, it says so.

### 16.1 Phases 1 and 2: foundation and data model

- Python, FastAPI, SQLAlchemy and SQLite. `python -m app` starts the server, and `/health` reports the database state. Settings come from `VELOXA_*` variables or `.env`. Every setting has a default, so no API key is needed.
- Every fact table carries `released_on`, `exported_on` and an as-of period (section 4). All stored times are IST. UTC sources are converted when read.
- Point-in-time filters run in SQL (section 11). "Known by" uses `released_on`. "Recorded by" uses `exported_on`, only among records released by the knowledge cutoff, and leaves out records with no `exported_on`.
- Department membership, reporting lines, department lines and role holders are effective-dated, with a status (decisions 17-19). A row taken from a snapshot starts at the snapshot date and is marked "start unknown". Before that date the answer is "unknown".
- Names resolve by exact match only, ignoring case and spacing (decision 21).
- Payroll is a separate SQLite file that only a totals function can read. It refuses individual pay, groups under five, groups whose membership is unknown, and totals within one to four people of any total already given (section 10, decision 20).
- Contractors have no Emp ID and are listed apart from headcount (decision 22).

### 16.2 Clarification: department payroll totals before 31 October

Section 10 expected the Engineering total to be answerable. Under decisions 17 and 20 it is not, for any date before 31 Oct 2026.

- Keka is one snapshot, so it shows department membership only from 31 Oct.
- The payroll months, Jan-Mar 2026, fall before that. Department totals for them are refused as "membership unknown".
- The company total is still answered. Join and exit dates give company membership on each date.

This is deliberate. Membership is not assumed back to each join date. A dated department history would lift the limit.

### 16.3 Phase 3: ingestion

Command: `python -m app.ingestion ingest PATH ... --release-day YYYY-MM-DD [--exported-on YYYY-MM-DD]`. `status` lists sources and logged problems. `aliases FILE.csv` loads reviewed name links.

Steps for each file (section 5):

1. Register. Hash the file (SHA-256). A known hash is a duplicate, and nothing is written. Templates and unsupported file types are skipped and logged.
2. Parse. One parser per type: CSV, XLSX, PDF, DOCX, EML and TXT. Each unit gets a locator: `Sheet!row N`, `row N`, `page N`, `para N` or `message`.
3. Date, as in the table below.
4. Store one Evidence row per unit, then typed facts by rule.
5. Commit each file on its own. A failure rolls back that file only. It is recorded as a failed source with its error, and the run continues.

After all files, name forms are linked to people.

Provenance kept for each source: file name, path relative to the folder given to the command, size, hash, system, trust rung, role (evidence, copy or reference), both dates, and where `exported_on` came from.

| Field | Rule |
| --- | --- |
| `released_on` | 10:00 IST on `--release-day` (decision 2) |
| `exported_on`, emails | The Date header, in IST |
| `exported_on`, sheets | An "Exported ..." date in the title line above the header |
| `exported_on`, PDFs | The first full date on page 1. On the Day 1 files this gives 8 Jul and 6 Oct for the board updates and 15 Sep for the letter, as in section 4 |
| `exported_on`, other files | `--exported-on`, or else a README.txt in the folder that states an export date. With neither, it stays empty and a warning is logged |
| `exported_on`, transcripts | Always empty (section 4) |
| Row dates | GL posting date; incident opened time; commit time; Jira "Last Changed" for the current release date |

Systems and trust rungs come from sections 2 and 15.1. A file that matches no known name is still ingested, with no rung and a warning. Templates are never ingested. Email_Printouts.pdf is stored as a copy, not a second source. Evidence confidence follows the source: H for rungs 1-3, M for rung 4, L for transcripts.

| Source | Typed facts written |
| --- | --- |
| Employee_Master | People, departments, memberships and reporting lines, from the snapshot date, start unknown. For someone with an exit date, they end at the end of that day |
| GL export | Ledger lines in paise. A "previous month" line describes the month before posting (section 4) |
| Payroll register | Rows go to the payroll store only. Evidence rows keep Emp ID, name, month and days, never amounts |
| Jira export | Tickets. Epic names and release dates as Claims. Only the current release date has a known record date |
| Incidents | Incidents, with UTC converted to IST |
| git_log.csv | Commits, with UTC converted to IST. Never a per-person time signal (decision 23) |
| Other tables | Evidence rows, with each row's cells kept by header |

Nothing is imputed. A bad value is logged against its row, the typed fact is skipped, and the evidence row is kept. A key that an earlier file already recorded is never overwritten. If the values differ, a conflict is stored with both rows (section 5, decision 1). This includes a later Keka snapshot: a difference is stored as a conflict, not applied to the org (decision 18).

Name links (decision 21). Each link is an Alias row that names its rule and cites the record behind it.

| Name form | Rule | Confidence |
| --- | --- | --- |
| Git author email | Equals one employee's Keka work email | H |
| Jira initials | First and last initials match exactly one known person | M |
| PagerDuty name | Equals one full name, or one exact first name | H, or M for a first name |

Two or more matches give an ambiguous row. No match gives an unresolved row. Neither carries a target. Alias rows are never edited. When a later file resolves a name, a new row is added, released when that file was, so earlier dates still see "unresolved". Reviewed links are loaded from a CSV; each row needs an evidence note, and a reviewed row outranks a rule row.

There are no schema migrations. An older, empty database is rebuilt on start. One that holds ingested sources is never dropped; the app stops and says so.

### 16.4 Open at the Phase 3 checkpoint

- The rule rates Jira initials M; ASSUMPTIONS.md (Day 3) rates them H. The GitHub no-reply address stays unlinked. Both need a reviewed alias file, which does not exist yet.
- Applying a confirmed change from a later Keka snapshot is not built.
- Rota, leave, hiring and pulse rows are evidence only, with no typed tables yet.
- Tested on synthetic files that copy the source layouts. The release packs were not run through the pipeline at this checkpoint.

### 16.5 Phase 3 follow-ups (18 November 2026)

- Reviewed name links are in `data/aliases_reviewed.csv`. Load them with `python -m app.ingestion aliases data/aliases_reviewed.csv`, after Employee_Master is ingested. The rows come only from ASSUMPTIONS.md (Day 3): the GitHub no-reply address to Priya Nair at M, and PN, RV, AD and SK at H. Snehal has a reviewed "unresolved" row, so no later rule can link that name. Loading the file twice adds nothing.
- A Keka snapshot that differs from an earlier one stays a conflict. Org changes are applied only from explicit evidence with an effective date.

### 16.6 Phase 4: evidence retrieval

`search()` in `app/retrieval` returns only stored Evidence rows. Each hit carries a citation built from its row and source: evidence key, source key, file name, relative path, locator, system, trust rung, both dates and the source hash. Evidence keys are set once at ingestion and never reused.

Steps:

1. Check the request. A bad request raises a clear error, not a crash.
2. Match text with SQLite FTS5. The index points at evidence.id and holds no text of its own; triggers keep it in step. User words are quoted, so they can never become FTS5 syntax. Stemming finds word forms ("delays", "delayed"). Names stay whole words: "Sneha" never matches "Snehal".
3. Filter in SQL: point in time (section 11, as in 16.1), policy, source, system, file type, trust rung and date range.
4. Filter by person or department at the as-of date. An ambiguous or unknown person returns no evidence and says why.
5. Rank by FTS5 relevance (bm25), then trust rung, then evidence key. The order is deterministic.
6. Collapse rows with the same text into one hit. The hit keeps the best rung and earliest release, and lists the others.
7. Add conflicts. A stored conflict with a side among the hits is returned with all its sides. A conflict is not shown at a date when one of its sides was not yet known.

A person's evidence is: the rows behind their record, membership and reporting line; tickets, incidents and commits whose name form resolves to them through an alias released by the cutoff; and text naming them by full name, Emp ID, work email, a resolved name form, or their first name when only one known person has it. A department's evidence is its members' evidence on the as-of date, plus text naming the department. When membership on that date is unknown, only the text is used, and a warning says so (16.2).

| Policy | Rule |
| --- | --- |
| Payroll register | Never returned unless the caller asks for restricted rows. The rows hold no amounts in any case (16.3) |
| 09.eml | Returned only for the purpose "atlas_ownership" (decision 23) |
| Email_Printouts.pdf, README.txt, brief | Left out unless asked for: a copy is not a second source, and reference files are not evidence |
| Failed sources | Never returned |
| Date range | Records with no date are left out, and a warning gives their count |

Citation checks: `validate()` takes cited keys and returns, for each one, whether it may be used. Reasons it may not: unknown key, not yet released, not yet recorded (recorded-by mode), restricted, purpose-limited, a copy or reference file, or quoted words that are not in the row.

Access:

- `python -m app.retrieval "words" [--as-of] [--mode known|recorded] [--person] [--department]`.
- `GET /api/search` and `GET /api/evidence/{key}`. These take no switch for restricted or purpose-limited rows; the question-answering layer decides purpose.

Limits at this checkpoint:

- Relevance comes before trust. A transcript can rank above a board update for the same words; weighing trust is left to answering (section 9).
- Search is by words. "Headcount" does not find "Team 19". There is no synonym list and no vector search.
- Person filters use exact rules only. Initials or names with no alias row are not linked.
- Row text is searched as written, for example "Amount (Rs.): 2600". Numbers are not normalised, so "Rs.2,600" does not find it.
- Tested on synthetic files only.

### 16.7 Phase 5: question answering

`ask()` in `app/answering` answers one question in the five fields of section 6: the question, a short answer, the evidence chain, confidence (High, Medium or Low, with its reasons), and the weakest link with what would change my mind. It is built on `search()` and `validate()` (16.6). It runs with no API key.

Steps:

1. Time frame. The as-of date the caller chose, else an "as of <date>" in the question, else now.
2. Names. People, departments and projects named in the question. People resolve at the time frame's cutoff, through exact rules and reviewed aliases only (decision 21). An ambiguous name is never picked. An unknown name is never guessed.
3. Classification. Fixed word rules pick a handler and set the purpose. Privacy and policy refusals are checked first.
4. Handler. Reads typed records and evidence through the existing time rules, and states only what they show. A missing value is reported as missing.
5. Conflicts. A stored conflict on any cited record is attached, with both sides in the chain. If it touches a supporting record, the short answer names both sides.
6. Citation check. Every evidence key in the chain goes through `validate()` with the question's purpose. Every quote must appear in its record. A key named in the text must be in the chain. One failure withholds the whole answer: nothing is asserted.
7. Sufficiency. An answer with no supporting record is not given as an answer.
8. Confidence, by rule (below).
9. Wording. Optional LLM rewording, off by default (below).

| Question | Reads | Notes |
| --- | --- | --- |
| Company headcount | Person join and exit dates | Contractors listed, not counted (decision 22). For a date before the Keka export, people who left earlier may be missing; the answer says so |
| Department headcount | Membership valid on the date | Before the snapshot, membership is unknown, and the answer says so (decisions 17, 20) |
| Manager as of a date | Effective-dated reporting lines | Pending changes shown, not applied (decision 18). For someone who has left, the exit date |
| Atlas GA date and changes | Jira release claims; dated statements, quoted | Current and original dates, and earlier exports if any. In recorded-by mode the current date counts only from its "Last Changed" date. The original date has no recorded time, so it is not used in that mode |
| Incidents in a period | PagerDuty incidents, by IST day | Severity filter. Responders linked only by rule or reviewed alias. A period outside the export's coverage is "not covered", not "none" |
| Marketing launch readiness | Launch kit status lines, planned date and owner; Jira GA date | Statuses read by rule from lines such as "Deck: Ready" |
| Source disagreement | Stored conflicts | Both sides, with their records |
| Payroll totals | The restricted totals function only | A month is required. Refusals as in decision 3 and 16.2 |
| Atlas ownership | Jira assignees; ownership statements | The only path that sets the purpose "atlas_ownership", so the only one that can cite 09.eml |
| Anything else | `search()` | Quotes the closest record and says there is no typed answer |

Purpose and privacy:

- `ask()`, the command and `GET /api/ask` take no purpose and no privacy switch. Extra parameters are ignored.
- Refused before any lookup: individual pay (a named person, an Emp ID, or words such as "highest paid"); commit times or performance read as a judgement of a person (decision 23); a person's intentions or feelings (decisions 11, 23); revenue, profit, margin and net burn (section 9).
- Payroll answers come only from the totals function. A test scans each payroll answer for every amount in the test register.
- 09.eml is cited only when the question names Atlas and asks about ownership.

Confidence. This narrows section 9, step 7:

- Base. High: a rung 1-2 source, or two systems that state the same fact. Medium: the best support is one rung 3-4 source. Low: transcript-only, unranked, or nothing.
- "The same fact" is checked, not assumed. Records that support different parts of one answer, such as a kit status and a GA date, are not corroboration. At this checkpoint only the GA handler checks it: a statement from another system that gives the same current date, in an exact date form.
- Caps, which can only lower the level: an open conflict on a supporting record gives Low, a resolved one Medium; a name linked at M or L; dates approximate or unknown; evidence partial or insufficient. A question about how the GA date changed is capped at Medium, because Jira keeps no history between the original and current dates.
- A policy refusal is High. It rests on a fixed rule, not on records.
- The reasons are listed with the level. A handler reports the factors; it cannot set the level.

LLM. Off by default (`VELOXA_LLM_ENABLED`). No provider is included. When it is on, a configured phraser may reword the short answer only. The new wording is rejected if it adds a number, an evidence key, a capitalised name or term, or a statement of confidence. Refusals, withheld and ambiguous answers are never reworded. Citations, confidence and status never change.

Reading the question:

- A day, a month or a range becomes a period in IST. A date with no year is read as the latest one not after the as-of date, and the answer says so. A year written on one end of a range applies to the other end.
- Incident coverage is the months named in the file name, such as "Aug-Oct_2026". With no such name, it is the whole months of the first and last incident known (ASSUMPTIONS.md, Build).

Access:

- `python -m app.answering "question" [--as-of] [--mode known|recorded]`.
- `GET /api/ask?q=...&as_of=...&mode=...`.

Two small changes to Phase 4 code: `conflicts_for()` in `app/retrieval/search.py` is now public, and the manager answer in `app/services/org.py` carries the id of the record behind it.

Limits at this checkpoint:

- Classification uses fixed word rules. A question phrased in an unexpected way falls through to search, which quotes the closest record and says there is no typed answer.
- The launch kit is read by line patterns such as "Deck: Ready". A kit laid out differently gives "status lines could not be read", not a guess. Not yet tried on the real kit.
- Statements in emails, board updates and transcripts are quoted, not read as dates, except for the exact-date match used for corroboration.
- Conflicts come only from the ingestion rules (a later file differs). The conflicts in sections 7 and 15.5, such as C-ATLAS-DONE, are not loaded yet. So "Is the engine feature-complete?" quotes the board without the Jira side.
- Headcount, manager and incident answers rest on one rung 3 export, so they are Medium at best.
- Each payroll total given is recorded for the differencing check (16.1). The order in which totals are asked can change which one is refused.
- Tested on synthetic files only.

### 16.8 Phase 5 follow-ups: conflict registry, confidence basis, incident coverage (18 November 2026)

Approved at the Phase 5 checkpoint: decisions 25 and 26, and the incident coverage assumption, provisionally.

Conflict registry (decision 26):

- Conflicts documented with an ID in this file are kept in `data/conflicts_reviewed.json`: C-ARR and C-BURN (section 7) and C-ATLAS-DONE (15.5). Each keeps its ID, title, status, working position, confidence, what would overturn it, where it is documented, the date it was noted, and its sides.
- A side names a source file, the words that locate its record, an optional locator prefix (such as "Issues!"), and the record's date (null when undated). C-ATLAS-DONE side B is the five Jira stories listed in TRANSCRIPT_NOTES.md (Day 3).
- All three are open. This file gives a working position for each but marks none as resolved, so none is marked resolved here.
- Not included: the GL total in C-BURN, which is a sum over many rows, not one record; and the "also registered" items in section 7 (180 versus 19 people, the fiscal-year label, Rahul Verma's days paid). Those have no ID or side records in this file.
- Load after ingesting the pack: `python -m app.ingestion conflicts data/conflicts_reviewed.json`.

Loading rules:

- Every side must match exactly one ingested record: the file was ingested, the record holds every match word (whole words, case and spacing ignored), and its date equals the date given. A failed, copied, reference or restricted source is never used.
- A conflict loads whole or not at all. A missing, ambiguous or misdated side rejects it, with the reason, and writes nothing for it. No evidence row is ever created.
- Status comes only from the file. A resolved status needs its resolution text. Loading never changes a stored conflict: the same content is skipped, and different content is rejected.
- The file was not yet loaded against the real pack. Its match words are taken from this file and TRANSCRIPT_NOTES.md. A side that does not match the real record is rejected at load, not guessed.

Retrieval and answers:

- A conflict is visible from 10:00 IST on the day it was noted, and only when every side is visible at the time frame. Conflicts found by ingestion are noted when the later file was released.
- A side is quoted from the sentence that holds its match words.
- An answer that rests on a record in a conflict names every side, grouped by side. An open conflict shows its working position, labelled "Working position, not a resolution", and gives Low confidence. A resolved one shows "Resolved" and caps confidence at Medium.
- A disagreement answer's "what would change my mind" is each conflict's stored "would overturn".

Confidence basis (decision 25). Every answer says what its confidence is about. "evidence": a business fact from records. "policy": a refusal. A refusal's High is confidence in the policy decision only; the answer says the question was not answered. "none": nothing supports an answer. A copied file is never a support: citation checks reject it, so a copy cannot corroborate its original.

Incident coverage (ASSUMPTIONS.md, Build, revised row):

- A file name such as "Incidents_Aug-Oct_2026" sets coverage only when every incident in the records falls inside the months it names. Otherwise coverage is the whole months of the first and last incident, and the answer says the file name was not used.
- Inside the coverage with no incident: "No incidents were recorded". Outside it: "Coverage unavailable ... not a count of zero".
- Limit: the coverage is still an inference. A file name can be right and the file can still be partial.

Schema version 4 adds the conflict's origin, noted date and documentation note, and each side's reference. An empty older database rebuilds itself; one holding sources stops, as in 16.3.

### 16.9 Real source-pack validation, Days 1-3 (19 November 2026)

The Day 1-3 release packs were run through the pipeline for the first time. They were read into a disposable database outside the repository. The project database was not touched, and no pack file was changed. The Day 4 pack was not opened.

Run: Day 1 with release day 16 Nov, Day 2 with 17 Nov, Day 3 with 18 Nov. Day 2 and Day 3 files that carry no date of their own were given 31 Oct 2026, from the Day 1 README ("Exported by IT on 31 Oct 2026"), as section 4 and ASSUMPTIONS.md (Day 3) describe. Then the reviewed aliases and the reviewed conflicts were loaded.

| Check | Result |
| --- | --- |
| Files | 39 found; 36 ingested; 3 templates skipped; 0 failed; 0 partial |
| Duplicates | Day 1 ingested a second time: 12 duplicates, nothing written. Reviewed conflicts loaded again: 3 unchanged |
| Records | 1,841 evidence rows; 19 people, 7 departments, 18 reporting lines; 62 tickets; 11 incidents; 1,453 commits; 8 Jira claims; 56 payroll rows to the restricted store only |
| Dates | Emails from their Date headers; board updates 8 Jul and 6 Oct; resignation letter 15 Sep; launch kit 21 Jul; Keka and hiring tracker from their titles; transcripts undated |
| Names | 1,522 facts linked. 4 not linked: "Snehal" on INC-206, 207, 209 and 211. Sneha and Snehal stay separate |
| Conflicts | C-ARR, C-BURN and C-ATLAS-DONE loaded; each side matched the intended record and date |
| Privacy | No individual pay amount appears in any answer checked |

The findings in sections 15.5 and 15.6 held on the real records: the original GA date of 15 Sep; the change to 15 Dec on 2 Sep; the 6 Oct board's "feature-complete" against five core stories not Done; three SEV1s in August, all routing-api; and Snehal first on the rota for the week of 17 Aug.

Fixes made from this run. Each has a test with a synthetic copy of the layout:

- The launch kit is a two-column table: item and status come out on separate lines. The kit reader now reads that layout.
- GA statements: the search no longer includes "date", which matched every ledger and Keka row. Jira is now left out in SQL, before the result limit, so board updates are not crowded out. Short words such as "GA" match whole words only ("GADS" is not "GA").
- Ownership statements must name the project, so a Keka title such as "Sales Lead" is not quoted.
- A board update is one record on one page, and it is a side of all three reviewed conflicts. A reviewed conflict now changes an answer only when it touches a supporting record and the question is about it: a question word appears in its title or sides, ignoring project names and generic words. Otherwise it is listed as a note, so it stays visible.
- A conflict side is quoted across a label and its value when a table splits them, for example "ARR (recurring)" and "Rs. 5.8 Cr".
- Privacy: Email_Printouts.pdf holds the text of 09.eml. Search and citation checks already left copies out, but `GET /api/evidence/{key}` served them. It no longer returns copies (decision 23).

Open after this run, each needing a decision:

- Invoice_PIS-114.pdf is dated "01/10/2026". The PDF date rule reads only day-month-name dates, so the invoice took the 31 Oct export date. Reading it as 1 Oct 2026 assumes day/month order.
- No contractor record exists, so headcount lists no contractors (decision 22). The invoice names "S. Patil"; linking Snehal to S. Patil is not approved.
- The T6b change (Marketing to a CRO, no effective date) is in a transcript only. Nothing stores it as an announced change, so the pending change is not shown next to Nikhil Bose's line (decision 18).
- Name forms with no reviewed alias stay unlinked, including "Sid" (the launch kit owner), "Pria" and "Vicky".
- When no handler fits, the search fallback still ranks by relevance before trust. For "monthly burn", a transcript is quoted before the board.

### 16.10 Day 4 follow-ups: invoice date, contractor, announced change, aliases (19 November 2026)

Four decisions approved on 19 Nov 2026, after the real-data run in 16.9. No schema change: the existing tables hold all four.

Invoice date:

- A vendor invoice whose page 1 has no day-month-name date is read for a numeric date in DD/MM/YYYY order. Invoice_PIS-114.pdf gives "01/10/2026": `exported_on` is 1 Oct 2026, and the string stays as written in `date_as_written`. The basis line says it was read day-first (ASSUMPTIONS.md, Day 4).
- Only invoices use this rule. Any other file with only a numeric date is left undated, as before.

Reviewed organisation records, `data/org_reviewed.json`, loaded after ingestion with `python -m app.ingestion org data/org_reviewed.json`:

- Contractor CTR-S-PATIL: "S. Patil", role "On-call SRE support" as written on Invoice_PIS-114.pdf, through Patil Infra Services. Stored as a Person with worker type "contractor" and no Emp ID. No join date, email or location is stored, because the invoice gives none. Not linked to Snehal or Sneha (decision 21). Headcount lists the contractor with the invoice as evidence and never counts them. Department counts and payroll membership take employees only (decision 22).
- Announced change T6B-MKT-CRO: Marketing to report to the CRO. It is stored as a department line with status "announced" (this file's name for the "announced_pending" status) and no effective date. The CRO is a role with no holder (decision 19). The source is the T6b voice note; T4's "I hear" is checked as a second statement.
- The change is shown as pending, never applied (decision 18). Nikhil Bose's line to Ananya Rao stands on every date asked, including dates after the announcement. "Who does Marketing report to?" says there is no confirmed line, and lists the pending change.
- Point-in-time: the change is shown from 10:00 IST on 19 Nov, the day it was reviewed. It is not shown in recorded-by mode, because its source transcript is undated.
- Loading follows the conflict registry's rules: each record must match exactly one ingested record and date; loading twice changes nothing; different content is rejected, never overwritten. A contractor record that carries an Emp ID, dates or personal details is refused, and so is an announced change with an effective date.

Aliases: "Pria" to Priya Nair and "Vicky" to Vikram Menon are reviewed rows at M, from 19 Nov 2026. Answers that rest on them are capped at Medium and say why. "Sid" stays unlinked. Sneha and Snehal stay separate.

Real data (Days 1-3, a fresh disposable database): all three files loaded with nothing rejected. The invoice is dated 1 Oct 2026. Headcount on 19 Nov is 18 employees, with S. Patil listed and not counted. The four Snehal incidents stay unlinked.

For Phase 6: linking "Pria" brings T5's "Pria has been doing late nights but she likes it" into Priya Nair's evidence. Agent profiles must leave such lines out (decision 23).

### 16.11 Phase 6: evidence-grounded agent profiles (19 November 2026)

The 14 agents are the people in section 8, by their Keka names, grouped as section 8 groups them (decisions 5 and 24). An agent is linked to an employee record only by an exact full-name match among employees. It is never linked by an alias, a first name or a guess. The other five staff have no agent. Contractors are never agents.

A profile is built at one time frame, known-by or recorded-by. It has these fields: role, department, reporting manager, employment, responsibilities, current projects, workload indicators, historical events, pending changes, conflicts, and missing information. Each fact carries:

- its evidence keys, validated;
- the source date, and the date it became known;
- a confidence;
- the period it holds for;
- notes on how names were linked and on any conflict.

A field with no eligible record says "Not established", with the reason.

Eligible sources are a fixed list of record systems:

| System | Used for |
| --- | --- |
| Keka HRMS | Title, department, reporting line, join and exit dates, status as written |
| Keka Hire | Requisitions where the person's Emp ID is the hiring manager: the only recorded responsibility |
| Jira | Tickets linked to the person: projects, epics, and open tickets and points at the export |
| PagerDuty | Incidents the person responded to, up to the as-of date |
| Team wiki (on-call rota) | Weeks on the rota, labelled as a copied plan |

Two reviewed exceptions may also be cited: the record behind an announced change, and the sides of a stored conflict that touches the person's records.

Never used: call transcripts and voice notes, emails, git commits and their times, the leave register, the pulse survey, payroll and letters. These hold statements, opinions, personal circumstances or pay. So T5's remark about "Pria" working late cannot enter Priya Nair's profile, even though "Pria" now links to her (decision 23).

Checks:

- Every cited key passes citation validation at the time frame, with no purpose and nothing restricted. It must also come from an eligible system or a reviewed exception. A fact that fails is dropped and listed, never shown.
- The profile endpoints, `GET /api/agents` and `GET /api/agents/{agent}`, take no purpose or privacy parameter.

Confidence:

- A fact keeps the lowest of its records' confidence and the confidence of the name link it rests on. For example, PagerDuty's "Sneha" is linked to Sneha Kulkarni by a rule at M, and the fact says so.
- An open conflict on a fact's records makes it Low. A resolved one caps it at Medium.

Time:

- Before the Keka export was recorded or released, a profile establishes nothing.
- Titles, departments and reporting lines are known from the 31 Oct snapshot. They are not back-dated.
- After an exit date, role, department and reporting line are "not applicable", and the history stays.
- The Marketing-to-CRO change is listed as pending, not in effect. It appears from 19 Nov and never in recorded-by mode.

Real data (Days 1-3, disposable database, 19 Nov 12:00):

- 14 profiles: 13 active, and Siddharth Mehta departed. 0 facts dropped. No pay amount, leave type or transcript or email text in any profile.
- Priya Nair's and Rahul Verma's Atlas facts are Low, because C-ATLAS-DONE touches their tickets. Vikram Menon is hiring manager for REQ-013 to REQ-015. Nikhil Bose and Aisha Khan show the pending CRO change.
- Finance and People & Ops profiles hold Keka facts only. Current projects, workload and responsibilities are "Not established" for them, because no eligible record covers that work.

Access: `python -m app.agents [name] [--as-of] [--mode]`.

### 16.12 Decision 23 in the answer engine (19 November 2026)

Found while checking Phase 6 on real data: "Has Pria been doing late nights?" fell through to search and quoted T5's remark. Before, the classifier refused only questions about commit times. It now also refuses working-hours questions about a named person: late nights, weekends, overtime, hours worked, working late. The refusal is "performance_assessment", however the question is phrased. Questions that name no person are not affected.

Still open, for review: a raw search (`/api/search` with a person filter) can still return that transcript paragraph. It is open evidence, not restricted. Blocking it would need a content rule, which has not been decided.

### 16.13 Decision 23: remarks about a named person's working hours (19 November 2026)

This section extends 16.12, after a full check of how T5's paragraph 10 ("Pria has been doing late nights but she likes it") can be reached.

The record is open evidence: system MeetNotes AI, not restricted, role evidence. Only payroll is restricted, and only 09.eml is purpose-limited. No rule restricts this paragraph in the raw evidence layer.

| Route | Before | Now |
| --- | --- | --- |
| Agent profile | Never: transcripts are not eligible (16.11) | Unchanged |
| Raw search, by words | Returned | Unchanged; open decision |
| Raw search, filtered to Priya Nair | Returned from 19 Nov, when the reviewed alias "Pria" began | Unchanged; open decision |
| Evidence detail, and the citation check | Returned / accepted | Unchanged; open decision |
| Answer engine | Quoted for 10 of 16 test phrasings, including indirect ones ("What has Pria been doing?", "Who works late?", "Tell me about late nights") | Never quoted or cited |

Rule in the answer engine. A sentence that pairs a working-hours phrase with a name is never quoted or cited. The phrases include late nights, weekends, overtime, working late, staying late, working nights, hours worked and working pattern. The name may be a linked person, an alias, or an unlinked capitalised name. As an answer, such a sentence is a working-hours signal about a person, which decision 23 forbids. Three layers:

1. The classifier refuses working-hours questions about a named person, in the wider set of phrasings, and "who ..." questions that pick people out by their hours. Questions about on-call, the rota or incidents are not affected.
2. The search fallback and statement quotes skip such sentences. The answer says how many records it left out.
3. The final citation check withholds any answer that still cites one, whatever handler put it there.

The refusal text now names working hours as well as commit times. Each layer has a test that fails without it.

The rest of T5 is unaffected: other paragraphs can still be quoted.

Open, needing a decision: whether the raw evidence layer (search, evidence detail) should also hold back such remarks. A test pins the current behaviour, so any change is deliberate. A related finding with no rule yet: T2 paragraph 8 carries a personal circumstance (an absence for a wedding), and the raw layer and the search fallback can return it.

### 16.14 Disclosure rules for user-facing output (19 November 2026)

Decisions 28 and 29 replace the open raw-layer boundary in 16.13. `app/retrieval/disclosure.py` decides what text may leave the system. The stored evidence is never changed.

Units:

- A record is split into sentences at full stops, question and exclamation marks and line breaks. A single capital before a full stop is an initial, not a sentence end ("F. Shah").
- A table row ("Header: value; Header: value") is one unit.
- A withheld unit is replaced by one generic marker, the same for both rules: "[text withheld under disclosure rules 28 and 29]".

| Output | Rule |
| --- | --- |
| `search()`, `GET /api/search`, the retrieval command | A record with nothing left to show is left out. So is one that matched only inside withheld text. Other hits show withheld units as the marker, and their snippet is rebuilt from visible text. Nothing says a record was left out: a count would hint at what it holds |
| `get_evidence()`, `GET /api/evidence/{key}` | The content is returned with withheld units replaced, and `withheld: true` |
| `validate()`, used for every answer and profile citation | A record with nothing disclosable fails as "withheld". So does a quote taken from withheld text. Either withholds the whole answer |
| Conflict quotes | Taken from visible text only |
| Answer engine | Uses the above. The search fallback and statements see only visible text. The working-hours refusal stays. Questions about on-call, the rota, incidents, deploys or releases are not refused |
| Agent profiles | Unchanged: they never read these sources (decision 27), and their citations pass `validate()` |

The working-hours rule needs a name in the sentence: a linked person, an alias, or a capitalised name. A sentence with operational wording (on-call, rota, incidents, PagerDuty, SEV, outages, deploys, releases, maintenance windows, change freezes) is never withheld by this rule. The personal-circumstances rule needs only one of its terms.

The 16.12 to 16.13 answer filter and backstop are replaced by these shared rules. The answer engine and the disclosure rules use one working-hours phrase list.

On the real records (Days 1-3), 4 of 1,841 evidence rows are affected, all withheld whole: T5 paragraph 10 (working hours); T2 paragraph 8 (wedding, in one sentence with Kartik's planning role); and Leave_Register rows 7 and 9 (marriage and sick leave). No other row changes. Across searches, evidence detail, answers and all 14 profiles, no withheld text appeared. The stored evidence hash was the same before and after.

Limits:

- Fixed phrase and term lists. Other wording is not caught, and a remark that also names on-call or an incident is not withheld.
- Clause-level separation is not attempted. A mixed sentence is withheld whole.
- Git commit rows (author and commit time) are open evidence. The search fallback can quote one, for example for "Who was on call in the week of 17 Aug 2026?". A pattern is never computed (decision 23), but single rows are not withheld.
- The leave register's exam leave row is not withheld; "exam" is not on the term list.

### 16.15 Decision 30: Git commit records (19 November 2026)

Enforcement paths:

| Path | What it does |
| --- | --- |
| `classify()` | A question with on-call, oncall, rota, pager or standby goes to the `on_call` handler, after the refusal, payroll and disagreement checks. The working-hours and commit-time refusals are unchanged |
| `on_call()` handler | Reads only on-call rota rows (Team wiki, OnCall_Rota.xlsx) known at the time frame. A row's "Week of" date starts a seven-day week. Names are listed exactly as the rota writes them and are not matched to people. With no covering row the status is "uncertain", nothing is cited, and the answer says commit records are not used in its place |
| `commit_records_barred()` in classify.py | True when the question names a person (linked or not), or uses on-call, "who", hours, overnight, activity, workload, productivity, performance, author or people words |
| `evidence_search()` fallback | Leaves GitHub records out, in SQL, when the rule is true |
| `statements()` (release date, launch readiness, ownership) | The same exclusion |
| `finalize()` backstop, `_commit_failures()` | Reads the question again, without the classification. A GitHub record anywhere in the chain of a barred question, conflict sides included, fails as "a commit record can't show on-call, hours or activity (DECISIONS.md 30)", and the whole answer is withheld |
| Agent profiles | Unchanged: GitHub is not on the decision 27 allowlist |
| `search()`, `GET /api/search`, `get_evidence()`, `GET /api/evidence/{key}` | Unchanged, as decision 30 requires. Git records stay open evidence there, under the decision 28 and 29 disclosure rules |

Payroll question routing. "Who ran payroll in February?" matched the pay words and went to the payroll total handler. A question with "who" and a run verb (ran, run, processed, handled, prepared, approved, signed off, did, does, do) before "payroll", and no pay-amount word (salary, pay, paid, earn, CTC, compensation, wages, take-home, amount, how much, gross, net, total, cost, bonus), now goes to the records search. The restricted payroll register stays out of search. Any pay-amount word keeps the question with the payroll handler and its refusal of individual pay. On the real records the answer now quotes 01.eml: "Ran Feb payroll since Fatima is out."

Exam leave review. Leave_Register row 10 records leave type "Exam", five days in May 2026, with the employee's initial and surname and the approver. No other record mentions exams, study or courses. The row is an approved leave type with dates, like the Casual, Earned and Relocation rows. It names no family event or health matter, so decision 29 does not cover it. No rule was added and the row is unchanged, pending review. Questions about a person's intentions are already refused (decisions 11 and 23).

On the real records (Days 1-3, disposable database): 25 questions where the rule applies cited no Git record. The on-call questions were answered from the rota. The week of 9 Nov 2026, after the rota ends, and any week asked before the rota was released, return "uncertain". Three repository-history questions still cited git_log.csv. The 14 agent profiles cite no Git record. The stored evidence and commit fingerprints were the same before and after.

Limits:

- The rule's word lists are fixed. A question about someone's activity in other words, with no name and none of the listed words, can still reach a commit row through the search fallback.
- "Who authored this commit?" is not answered from Git.
- A commit row quoted for a repository-history question still shows the author's email and commit time as written. No pattern is ever computed from them.
- Rota names are not linked to people, so the answer does not say whether "Sneha" or "Snehal" is the person asked about.
- PagerDuty responders show who responded to an incident, not who was on call. They are not used for on-call questions.

### 16.16 Phase 7: the CEO worry list (19 November 2026)

Code: `app/worries` (`rules.py`, `engine.py`, `__main__.py`), `GET /api/worries`, and the page at `/`. Decisions 11-16 and 23-30 apply. No LLM generates, scores or ranks a worry.

Pipeline: each rule returns a candidate or an exclusion with its reason. A candidate goes through the answer engine's `finalize()`: citation checks at the time frame, disclosure rules 28 and 29, the decision 30 backstop, stored conflicts and confidence by rule. Then the well-supported check, the Git check, the score, the ranking and the duplicate check. The top three are shown, the rest are listed below them, and every exclusion is listed with its reason.

Candidate rules:

| Rule | Raised when | Supporting evidence | Context only | Impact |
| --- | --- | --- | --- | --- |
| `delivery_schedule` | A release's current Jira date is later than its original date | Jira release date and original date; that version's stories not Done | - | 3: a committed product date |
| `service_reliability` | One service has 2 or more SEV1 incidents within 31 days, opened by the as-of date | The SEV1 incident rows | Later incidents on that service; up to 2 emails or documents (rung 1-4) naming the service | 3: repeated highest-severity incidents |
| `capacity` | A requisition has been on hold for 30 days or more, or one assignee holds 40% or more of a project's open story points (3 or more open stories) | Hiring tracker rows; that project's open stories | Recruiting fee lines in the GL; emails on hires | 2: delivery capacity |
| `launch_alignment` | The latest launch kit's planned date is before the release's current Jira date, or the kit's owner (linked by exact name) has left | Kit status lines; the Jira release date | The owner's employee record; an announced Marketing reporting change, as a note | 2: launch readiness |
| `cost_trend` | One vendor and cost centre has 4 or more monthly GL entries, rising in each of the last 3 or more, and up 20% or more | The GL lines | One email on burn | 2: recurring cost |

Evaluated and never raised on their own:

- `contractor_continuity`: a contractor record alone is not a risk. No record shows an end date, a notice or a gap in cover, and a risk is never raised from missing evidence.
- `org_change`: an announced change is not in effect and rests on transcripts. It is shown as a note on a related worry (decisions 18, 19).
- `reported_metrics`: revenue, profit and net burn can't be computed (section 9). Disagreeing figures are shown when asked.

Score, with fixed weights:

    score = 3 x impact (1-3) + 2 x strength (Low 1, Medium 2, High 3) + recency (0-2) + persistence (0-2)

- Strength is the confidence computed by `finalize()`. Impact comes first because it is what the CEO asked about (T6a). Strength comes second, so a weakly supported item can't outrank a well-supported one of equal impact.
- Recency: the latest supporting record dated within 31 days of the as-of date scores 2, within 92 days 1, otherwise 0.
- Persistence is set by each rule:
  - delivery: 1 for a moved date, plus 1 if over a third of the story points are open;
  - reliability: incidents on the service in 3 or more months score 2, in 2 months 1;
  - capacity: on hold 60 days or more scores 2, otherwise 1;
  - launch: planned date passed by 30 days or more scores 2, otherwise 1;
  - cost: 5 or more consecutive rises score 2, otherwise 1.
- Ties go to higher impact, then higher strength, then the rule key.
- The number of records never enters the score.

Confidence is the existing rule (section 9, step 7), unchanged. An open conflict on a supporting record makes it Low. The conflict is listed on the worry, and its sentence is added to the explanation, so it is never resolved silently.

Evidence requirements (what "well supported" means, decision 13). A worry is shown only when:

- every cited record passes its check;
- at least one supporting record comes from a rung 1-4 source, so transcript-only support is never shown;
- no citation is a Git commit record.

A candidate whose supporting records are all cited by a higher-ranked worry is a duplicate: it is merged into that worry and listed as related.

Privacy. The rules never read:

- Git commits, in their searches or as support (decision 30);
- the leave register or the pulse survey;
- payroll rows, or GL lines whose cost centre or vendor names payroll or salaries (decision 3);
- 09.eml (decision 23);
- the rota as a record of people.

No worry text names an employee. Assignees, responders and the kit owner are not named. Withheld text can't support a worry, because `finalize()` fails it.

Time. Every read goes through `visible()` and `usable()` at the time frame, and recorded-by mode uses evidence dates. `data_as_of` is the date of the latest supporting record shown (decision 16). `evaluated_at` is the evaluation timestamp only; the same records give the same list.

Interface. `/` opens on the worry list (decision 12). It shows:

- the as-of frame and the date of the latest record;
- up to three worries, each with confidence, conflicts, uncertainty, the score breakdown and its evidence (each key opens `/api/evidence/{key}` at the same time frame);
- lower-ranked items and exclusions, collapsed;
- the existing question box, backed by `/api/ask`.

All record text is inserted as text, never as HTML. `python -m app.worries` prints the same list.

On the real records (Days 1-3, disposable database):

| Time frame | Shown | Below |
| --- | --- | --- |
| Known 16 Nov 12:00 | cost_trend | - |
| Known 17 Nov 12:00 | cost_trend, capacity | - |
| Known 18 Nov 12:00 and 19 Nov 12:00 | service_reliability, delivery_schedule, cost_trend | capacity, launch_alignment |
| Recorded by 31 Aug | service_reliability, cost_trend | - |
| Recorded by 30 Sep | cost_trend, service_reliability, launch_alignment | - |

At 19 Nov 12:00:

1. routing-api SEV1s: Medium, score 16.
2. Atlas GA moved to 15 Dec with C-ATLAS-DONE open: Low, 15.
3. AWS charges up 37% over five rising entries: High, 15.
4. Capacity: Medium, 14.
5. Launch kit out of step: Medium, 13.

No employee name, Git, payroll, leave or withheld text appeared at any time frame. The API matched the engine. The stored evidence and commit fingerprints and the project database hash were unchanged.

Limits:

- The thresholds, impact values and weights are a first proposal, pending review (decision 15).
- Only these five areas are scored. The summit spend, the open payroll query and Cohere's advance as an item of its own are not evaluated. Retention and pulse signals are not evaluated, by design (decisions 11, 23).
- Reliability recency follows the latest SEV1, not later lower-severity incidents.
- The kit's owner is written only as a first name with no reviewed alias, so the owner's departure is not shown on the real records.
- Concentration is counted by Jira assignee initials. No name is shown, but the cited Jira rows show the initials.
- The manager to ask (decision 11) is not shown.
- The date gap between 08.eml and the GL on when the contractor started is not shown.
- The page has no sign-in; it is for local use.

### 16.17 Phase 8: temporal and end-to-end validation (19 November 2026)

Decisions 31 and 32 record the scoring and eligibility rules of 16.16.

AWS cost trend check. All six GL lines behind the item were inspected.

- They are one vendor (Amazon Web Services), one cost centre (ENG-INF) and one narration ("AWS, previous month"). Each is posted on the 8th of consecutive months, April to September 2026, one line a month.
- No AWS or Amazon line exists under any other cost centre. No negative, credit, reversal or adjustment line exists anywhere in the GL export.
- The five rises are +5.1%, +8.1%, +3.2%, +3.5% and +13.0%. The total is Rs.1,81,200 to Rs.2,48,310, +37.04%. It is measured from the first line of the run, which is also the first AWS line in the export.
- The six cited keys are those six rows.
- The evidence is comparable, so confidence stays High.

The rule now:

- breaks a run at any missing calendar month;
- nets credits within their month and says so;
- says "posted" for the dates;
- quotes the narration;
- states that the rise may have begun before the export, and that tax treatment is not stated.

Journey fixes:

- The page had no agent picker, which section 9 lists. It now lists the 14 agents at the chosen time frame and opens a profile, with its evidence keys and the fields not established.
- The page now declares an empty icon, so the browser no longer requests a missing favicon.

Real-data checks (Days 1-3, disposable database): 47 of 47 passed.

| Area | Checks | Examples |
| --- | --- | --- |
| Recorded-by versus known-at | 6 | Atlas GA hidden as recorded by 1 Sep, 15 Dec from 3 Sep; 2 SEV1s as recorded by 15 Aug, 3 known at 19 Nov |
| Release times | 6 | Day 1 headcount at 09:59 none, at 10:00 answered; Jira GA at 18 Nov 09:59 none, at 10:00 shown; alias "Pria", the contractor and the CRO note appear only from 19 Nov 10:00; Day 3 worries only from 10:00 |
| Employees and reporting over time | 3 | 19 employees on 30 Oct, 18 on 1 Nov; Siddharth Mehta active on his exit date, departed from 1 Nov, and no Keka record as recorded by 15 Oct; Nikhil Bose's manager is the current line, with the CRO change pending |
| Contractor versus employee | 2 | 18 employees, S. Patil listed apart and never linked to Snehal or Sneha |
| Announced versus effective | 2 | Marketing's line unchanged, the CRO change called announced; a note on the launch worry only |
| Worry lists over time | 8 | Seven time frames: at most three shown, every citation valid at its frame, and evidence dates not after the as-of date in recorded-by mode; the same records give the same list |
| Conflicts | 4 | C-ATLAS-DONE absent at 18 Nov 09:59 and shown at 10:00; Low confidence; C-ARR from Day 1 |
| Disclosure rules 28 and 29 | 5 | The four withheld rows stay withheld in evidence detail, search, answers, profiles and worries |
| Decision 30 | 5 | On-call from the rota only; no Git in person questions, worries or profiles; raw search still returns Git rows; the working-hours question is refused |
| CLI, API and page | 6 | Answers, worries and the agent list are the same from the command line and the API; the page reads the same endpoints |

End-to-end journey: 13 of 13 passed. The application ran on a disposable copy and was driven in a headless browser:

1. start;
2. open the page;
3. top worries equal the API, with the conflict and confidence shown;
4. open a record;
5. ask about Atlas;
6. ask an on-call question;
7. ask a refused working-hours question;
8. open an agent profile;
9. change the as-of date to 16 Nov 12:00, and the list and the answers match that date.

There were no browser errors.

A disposable database rebuilt from the Day 1-3 packs with the documented ingestion commands gave the same evidence and commit fingerprints. The stored evidence and the project database were unchanged throughout.

Limits:

- Day 4 records are not ingested.
- The project database holds no sources, so a demonstration needs a disposable data folder.
- Impact values and thresholds per rule are as in 16.16.

### 16.18 Day 4 voice notes T6c and T6d (19 November 2026)

Sources. The Day 4 pack holds two files: `T6c_CEO_Voice_Note.docx` and `T6d_CEO_Voice_Note.docx`. Both are auto-transcribed WhatsApp voice notes forwarded by the CEO's assistant.

- Ingestion matches them to the transcript profile (rung 5) and gives them `released_on` 19 Nov 2026 10:00 IST and no `exported_on`.
- Their internal document date (14 Nov 2026 11:33 UTC) is the same as T6b's. It is a template date, not a recording date, and is not used. "This morning" in T6d is therefore not dated.
- In recorded-by mode they are never visible, like every undated transcript.

T6c (decision 34).

- Classification checks a ranking request before any other rule: a likelihood word near a leaving word, plus ranking language ("everyone", "rank", "list", "who", "most", "team"). That gives the refusal `retention_ranking`.
- A single named person's intentions keep the `speculation` refusal. Slack, WhatsApp, DMs, chat logs or "their messages" give the refusal `private_messages`.
- When the question cites someone's approval, the refusal adds that it is not consent from the people concerned.
- Every one of these refusals offers "What is our workforce continuity?". That question goes to `workforce_continuity()`, which lists:
  - confirmed departures and upcoming exits, from Keka exit dates;
  - requisitions by status, with roles, teams and status dates, from Keka Hire;
  - the largest single share of each project's open story points (40% or more), with no name;
  - contractors;
  - the count of unverified reported events.

T6d (decision 33).

- `data/org_reviewed.json` gains a `reported_events` section. `T6D-RESIGNATION-REPORT` holds the name ("Pria") and the notice period exactly as written, matched to T6d's own text.
- The loader stores it as a Claim with subject type `reported_event`, status `reported_unverified` and confidence L. It refuses any record that carries an identity, an exit date, a last working day or another status. It never touches Person.
- A question that pairs a departure word with a person, or with "version three", goes to `departure_impact()`. The handler answers in this order:
  - the report, quoted;
  - the identity, through the reviewed aliases known at that time;
  - the Keka record, unchanged;
  - which project "version three" is, from Jira epic names and rung 1-2 statements;
  - the person's open stories and story points per epic;
  - documented responsibilities, from rung 1-4 records with a lead or owner word;
  - stored conflicts on those stories;
  - the release date;
  - the manager on record to confirm with;
  - a "Not established" list.
- The report is a context link, never support. The answer's status is "uncertain".

On the real records (Days 1-4, disposable database), known at 19 Nov 2026 12:00:

- T6c is refused, with the consent sentence and the continuity offer.
- The continuity view gives:
  - 1 confirmed departure (Product Marketing Manager, exit 31 Oct 2026);
  - requisitions: 2 on hold since 12 Aug 2026, 2 open, 1 filled and 1 closed;
  - one person holding 62 of 115 open ATLAS story points (54%);
  - 1 contractor;
  - 1 unverified report.
- T6d, part 1: "Pria" links to Priya Nair (VX007) only through the reviewed transcript alias at confidence M, known from 19 Nov 2026 10:00. Keka (exported 31 Oct) shows her Active with no exit date.
- T6d, part 2: version three is Atlas. The Jira epics read "Core routing engine v3" and "Public API v3", and the Apr-Jun board update reads "Atlas (routing engine v3)".
- T6d, part 3: Jira shows her assigned 35 of 62 ATLAS stories. She holds 62 of 115 open points in 14 open stories:
  - Core routing engine v3: 14 of 20 open points;
  - Real-time re-routing: 29 of 29, all of its open work;
  - Performance and hardening: 19 of 37.
- T6d, part 4: 04.eml (2 Jun) says "Priya leads the core engine and re-routing". C-ATLAS-DONE touches 3 of her open stories. GA is 15 Dec 2026, moved from 15 Sep. The manager on record is Vikram Menon.
- T6d, not established: an HR record of the resignation, the notice period, a last working day, and a handover plan or backup owner. Confidence is Low.
- At 19 Nov 09:59, neither the report nor the alias is known, and "Pria" is not linked to anyone.

Engine change. Number and time words ("two", "months", "this", "morning" and similar) no longer make a stored conflict relevant to a question. Before this, "notice period two months" attached C-BURN ("two point two lakhs a month") to T6d.

Checks:

- 33 tests in `tests/test_t6cd.py`. The full suite has 361 tests. Each of five new safeguards was switched off once, and a test failed each time.
- On the Days 1-4 disposable database, the 47 real-data checks of 16.17 still pass. The browser journey, with the T6c, T6d, continuity and profile steps added, passes 17 of 17.
- A clean copy, with no `.git`, caches or databases, installed `requirements.txt` into a new virtual environment, passed all 361 tests, and rebuilt the Days 1-4 demo database with the same evidence fingerprint.

Limits:

- The ranking and private-message wordings are fixed lists.
- An indirect personal signal, such as a single leave row returned by the search fallback, is still open evidence under decisions 28 and 29.
- A question naming several people uses the first name found.
- The impact answer reads Jira and documents only. It can't see work that is not ticketed.

### 16.19 Final review: leave records, the T6d record and decisions 33-34 (19 November 2026)

Finding (real records, Days 1-4, disposable database):

- 17 of the 19 Leave_Register rows were open: casual, earned, relocation and exam rows, and five "Personal (half day, PM)" rows for one engineer in September. Only the marriage and sick rows were withheld.
- The open rows appeared in search ("leave" returned all 17), in evidence detail, and in the answer fallback. "Who took exam leave?" and "Who relocated?" cited them.
- Profiles, worries and the continuity view never read the register. A person-filtered search returned none, because the rows use initials.

Correction:

- `disclosure.sentence_reason()` now treats a table row with a leave-type field ("Leave Type", "Type of leave", "Leave reason" or "Reason for leave") as a personal circumstance, whatever the value.
- The rule sits in the shared disclosure layer, so it covers search, snippets, evidence detail, citation checks, conflict quotes and answers.
- Jira, Keka, hiring and pulse rows are unaffected, and the stored rows are unchanged.

Result:

- 21 of the 1,740 evidence rows under the default roles are withheld, all whole: the 19 leave rows, T2 paragraph 8 and T5 paragraph 10. This updates the counts in 16.14.
- 01.eml's "since Fatima is out" stays visible.
- Outside the leave register, the only exam remark (T2 paragraph 8) was already withheld.
- Pulse survey rows are team-level (at least 3 responses, comments hidden for teams under 6) and are unchanged.

Other checks in this review:

- The diff of `data/org_reviewed.json` against its 18 Nov version adds only the `reported_events` block. The other sections are byte-for-byte the same.
- Between the Days 1-3 and Days 1-4 disposable databases, persons, reporting lines, memberships, department lines, aliases and every claim other than the report are identical.
- Priya Nair's profile at 19 Nov 12:00 is identical.
- The report's source hash equals the file's own hash.

Tests:

- 20 tests in `tests/test_disclosure.py`, and four leave rows of other types added to the shared test company.
- Switching the rule off made 15 of them fail. The profile test passes either way, because profiles never read the register.
- Full suite: 381. Real-data checks: 47 of 47. Browser journey: 19 of 19, with T6d checked on the page at 09:59 and at 10:00.

Limits:

- The rule needs a leave-type field. A leave record exported without one, or a sentence such as "X is on leave for Y" in prose, is caught only by the word lists of decisions 28 and 29.
- No worry can use a leave pattern now, even without names.

### 16.20 Setup and run workflow (19 November 2026)

Finding. On 19 Nov the cockpit was started with `VELOXA_DATA_DIR` set to an external folder in which no ingestion had ever run.

- On startup, `create_app()` creates the data folder and an empty schema, so the server served an empty database.
- The page showed "no dated records", an empty worry list and 14 agents with "identity_not_established".
- The release pack had been given to the ingestion commands under a wrong folder name, and every path check failed.

Correction: one workflow in four PowerShell scripts at the repository root, with shared helpers in `scripts/common.ps1`. No answer, privacy or ingestion logic changed.

Configuration:

- It lives in `.env` (not committed). The application already reads it, so the server, the command line and the scripts use the same folder.
- `setup.ps1` writes `VELOXA_DATA_DIR`, `VELOXA_PORT` and `VELOXA_SOURCE_PACK`. It keeps every other line.
- The release pack location is kept only there, never in the documentation.
- The demo data folder must be outside the repository. A data folder inside it, including `data`, is refused.

| Script | Behaviour |
| --- | --- |
| `setup.ps1` | Checks Python 3.11+; creates `.venv` only when missing; installs `requirements.txt` into it; checks the four day folders read-only; creates an empty data folder if missing; writes `.env`. Never ingests |
| `setup-demo-data.ps1` | Uses `.venv` Python. Checks the release pack and that the target database is missing or empty. A loaded database ends with "nothing to do"; any other non-empty database, or a payroll store beside an empty one, is refused. Ingests Day 1 to Day 4 with the validated release days and export dates, then the three reviewed files, stopping at the first failure. Prints a strict summary |
| `start.ps1` | Uses `.venv` Python. Runs the readiness check and refuses a missing or empty database or missing reviewed files. Refuses a port in use, and names the owner without stopping it. Then starts the server from the repository root and prints the URL |
| `verify.ps1` | Read-only PASS or FAIL checks. The interpreter; the data folder; the database (strict counts, reviewed files, payroll store present). With a server on the port: that it runs from `.venv`, `/health`, the worry list, 14 agents with established identities, an Atlas answer, T6c, T6d at 19 Nov 09:59 and 10:00, and the page |

`app/readiness.py` (`python -m app.readiness`):

- It opens SQLite read-only (`mode=ro`), so a missing database is reported and never created.
- It refuses the repository's data folder without opening it.
- It checks evidence, people, the three reviewed files and the payroll store's presence. Payroll amounts are never read.
- It compares the expected Days 1-4 counts: a WARN normally, a FAIL with `--strict`.

On Windows, `.venv` Python is a launcher that starts the base interpreter with the virtual environment. `verify.ps1` therefore recognises the server by the launcher in its command line or as its parent process.

Tests:

- An autouse fixture in `tests/conftest.py` gives every test its own `VELOXA_DATA_DIR`, so no test can reach the demo or project database through `.env`.
- `tests/test_readiness.py` (7) covers missing, empty, loaded and project databases, read-only behaviour and the command line.
- `tests/test_ops_scripts.py` (15) covers ASCII-only scripts, parsing, the refusals for a missing or empty database or the repository folder, and a refused second load.
- Full suite: 403.

Run on 19 Nov:

- `setup.ps1` created `.venv` and `.env`.
- `setup-demo-data.ps1` loaded into the previously empty `cockpit.db`, with every expected count matched. The evidence fingerprint equals the validated Days 1-4 database. A second run did nothing.
- `start.ps1` started the server on 8010, and `verify.ps1` passed every check.
- The browser journey passed 19 of 19 against that server.
- Each refusal was exercised. The project database was unchanged throughout.

Limits:

- The scripts are for Windows PowerShell.
- The day folders, release days and expected counts are those of the Days 1-4 pack. A new pack day needs an entry in `scripts/common.ps1` and new expected counts in `app/readiness.py`.
- "Why is Atlas not complete?" has no dedicated handler. The keyword fallback answers it weakly; "When is Atlas GA?" and "Is the Atlas engine feature-complete?" give the evidence-backed answers.