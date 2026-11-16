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
| GL_Export_Apr-Sep_2026.xlsx | Zoho Books | Costs by vendor and cost centre, Apr-Sep 2026; selected cost centres, no revenue | 1 | Posted transactions; payroll agrees with an independent export |
| Payroll_Register_Jan-Mar_2026.xlsx | Payroll workbook (pre-Keka) | Days and amounts paid per person; restricted | 1 | System of record for pay |
| Board_Update_Apr-Jun_2026.pdf, Board_Update_Jul-Sep_2026.pdf | Management | ARR, customers, burn, runway, headcount, plans | 2 | Dated and deliberate, but lagged and written to persuade |
| Employee_Master.xlsx | Keka HRMS | Identity, department, manager, join and exit dates; no contractors | 3 | System export, but one snapshot, no history |
| 01.eml, 02.eml, 03.eml | Email | Who said what, when | 4 | First-hand, but selected and partial |
| T1_CEO_Kickoff_Call.docx, T2_CFO_Call.docx | MeetNotes AI | Leads and opinions; never the sole basis for a figure | 5 | Machine-generated, undated, misheard |

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
| `exported_on` | When the source produced it: posting date, email Date header, board send date, or the file export date when nothing finer exists |
| `released_on` | When I was allowed to know it: the day-folder release date |

Treating the 31 Oct export date as a release date would leak data into point-in-time answers (section 11).

| Case | as_of | exported_on | released_on |
| --- | --- | --- | --- |
| Board update Apr-Jun | Apr-Jun 2026 | 8 Jul 2026 | 16 Nov 2026 |
| Board update Jul-Sep | Jul-Sep 2026 | 6 Oct 2026 | 16 Nov 2026 |
| AWS, Google Ads lines | Month before posting ("previous month") | Posting date | 16 Nov 2026 |
| Emails | Date header | Date header | 16 Nov 2026 |
| Export snapshots (Employee_Master, GL, payroll) | Per row or per file | Row date where present, else 31 Oct 2026 | 16 Nov 2026, the Day 1 release. 31 Oct is when IT produced the files, not when I could know them |
| Transcripts | Unknown | Unknown | Day released to me |

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
| Claim B | Board: Rs.5.8 Cr (Apr-Jun), Rs.6.1 Cr (Jul-Sep) | Board: Rs.46 L, then Rs.44 L. GL: Rs.2,34,07,530 Apr-Sep, Rs.39.0 L/month, 81% payroll |
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

Corroboration decides grounding: T2 says Fatima was out for her wedding, and 01.eml independently says Karthik ran February payroll "since Fatima is out". Karthik's CFA study is transcript-only, so it is low-confidence persona. Siddharth Mehta is employed through 31 Oct 2026 (Keka shows him in notice period, exit date 31 Oct) and gone from 1 Nov; any answer about him must state its as-of date. No agent can read the payroll store; finance agents decline pay questions in character.

## 9. Question to answer flow

1. Parse intent, entities, period and as-of date (default latest).
2. Privacy gate, before retrieval.
3. Resolve entities through Alias.
4. Retrieve Claims dated on or before the as-of date, on the field the question's mode needs (section 11).
5. Attach open Conflicts touching those Claims.
6. Compose. Numeric lookups are templated; the LLM, when on, only phrases retrieved Claims, and a validator rejects any number or name not in them.
7. Confidence by rule: H if rung 1-2 or two independent sources agree with no open conflict; M if one rung 3-4 source or a resolved conflict; L if transcript-only or an open conflict. The LLM cannot raise it.
8. If nothing supports an answer, say so and name the record that would.

Refusal types: privacy, not computable (revenue realisation, net burn, profit), not yet released, unresolvable conflict.

The interface is a question box returning the five fields, an as-of date selector, an agent picker, and a worry list in the same five fields, drawn from the registry and rule-based flags: the AWS trend, the Rs.1,77,000 Cohere Recruiting advance while hiring is paused, the Rs.10,03,000 summit, the Atlas slip, the open payroll query.

## 10. Privacy boundary

The CFO's rule (T2): individual salaries never reach the CEO. Payroll lives in a separate SQLite file opened only by an aggregation module; the cockpit and agents have no handle to it. It emits totals over at least five people, and exception flags with no money values. [ASSUMPTION] Five, because three-person departments are otherwise exposed. Comparing totals whose membership differs by fewer than five is refused, to block differencing. Consequence: only the 19-person company total and Engineering (5) are answerable; Finance, Marketing and People & Ops totals are refused, including for the CFO. Department-level payroll needs the CFO to relax the rule or approve grouped reporting. A test scans every response for every amount in the register.

The Rahul Verma case is the tension: reporting it names him and implies his pay. Line drawn: the cockpit states the person, join date, days paid against days eligible, and the email trail ending "Will check and get back.", because the matter is already in his own email and closing it needs a named owner. It never states any amount paid or overpaid; that goes to the CFO. To be recorded in DECISIONS.md.

## 11. Point-in-time behaviour

Two modes, both filtering every Claim and Conflict, so a conflict invisible at X does not appear. "What did I know on X" uses `released_on`: on 16 Nov it returns only Day 1 sources, on 17 Nov Day 1 and Day 2, and before 16 Nov nothing. "What had the company recorded by X" uses `exported_on`: Apr-Jun ARR is unknown on 1 Jul (board sent 8 Jul); Atlas is "on track for 15 September" on 1 Aug and "GA moved" on 10 Oct; Siddharth Mehta is staff on 15 Oct and departed on 3 Nov.

## 12. Test strategy

27 questions with expected refs, figures, confidence and refusal type, run offline in one command.

| Category | Count | Example |
| --- | --- | --- |
| Fact lookup | 8 | Monthly payroll total; who manages Rahul Verma |
| Contradiction | 5 | "Is ARR 45 crore?"; "Are we 180 people?" |
| Refusal | 5 | "What does Rahul earn?"; "Finance payroll total"; "What is our profit?" |
| Point-in-time | 4 | Atlas status on 1 Aug versus 10 Oct; Siddharth Mehta on 15 Oct versus 3 Nov |
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

## 14. Version log

| Version | Date | Note |
| --- | --- | --- |
| v1 | 2026-11-16 | Day 1 sources only |

v1 covers Day 1 sources only; Days 2-4 are not yet released.