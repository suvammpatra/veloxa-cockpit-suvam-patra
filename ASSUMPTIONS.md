# ASSUMPTIONS.md

These are the assumptions the Veloxa CXO Cockpit rests on, each tied to the source line behind it. Confidence is H, M or L, and each entry says what evidence would overturn it.

| Date | Assumption | Source it rests on | Confidence | What would change my mind |
| --- | --- | --- | --- | --- |
| 2026-11-16 | 19 staff, not 180 | Both board updates give "Team 19"; Employee_Master lists VX001-VX019 | H | A roster or export showing 20 or more |
| 2026-11-16 | The 14 agents are Engineering 5 + Finance 3 + People & Ops 3 + Marketing 3, i.e. 19 minus the CEO, Sales and Support | Brief says "14 people across engineering, finance, HR and marketing"; the four departments total exactly 14 | M | A transcript or note treating Manoj Kumar, Divya Reddy, Imran Siddiqui or Kavya Narayan as a subject of questions |
| 2026-11-16 | The fiscal year runs April to March, so November 2026 is FY27 | The payroll workbook sheet covering Jan-Mar 2026 is named "Payroll Q4", which only works on an April-March year | M | A dated finance header saying otherwise |
| 2026-11-16 | The board's "monthly burn" means gross monthly cash outflow | GL outflow across selected cost centres averages Rs.39.0 L/month, the same order as the board's Rs.44-46 L | M | An explicit finance definition of burn |
| 2026-11-16 | "Vicky" in T2 means Vikram Menon | He is the only Vikram in Employee_Master | M | Any record using the nickname |
| 2026-11-16 | T2's "two backend roles" are the Cohere Recruiting search | Same count, same timing, 50% advance invoiced Jun 2026, and hiring was later paused. Day 2 (17 Nov): Hiring_Tracker has REQ-014 and REQ-015, both backend, opened 18 May 2026 and on hold since 12 Aug (06.eml) | M | A record naming different roles |
| 2026-11-16 | A five-person floor for payroll aggregates | The CFO's rule plus the fact that Finance, Marketing and People & Ops have three people each | M | A leak found in testing |
| 2026-11-16 | The transcript summariser attributed speakers correctly | There is no audio, only MeetNotes AI summaries | L | A transcript name that contradicts a role in Employee_Master |
| 2026-11-16 | Sapphire Residency Hotel is a sales cost, not summit cost | GL cost centre SAL-TRV and the narration "Sales offsite" | M | An invoice or GSTIN showing it is the events firm |
| 2026-11-17 | The Keka Hire tracker is the best hiring record supplied, not a complete one; hiring answers cite it and say Lever is missing. Revised 17 Nov, first entered as "The Keka Hire tracker is the complete hiring picture" | Hiring_Tracker.xlsx header: "Hiring tracker (Keka Hire). Exported 31-Oct-2026." T3 Key points: hiring runs on "Liver" (Lever). No Lever export is in the data room, and REQ-012 is missing from the tracker's numbering | M | A Lever export, or any requisition that exists only in Lever |
| 2026-11-17 | P. Nair's September half-days are an observed pattern worth watching, not evidence of dissatisfaction or intent to leave. Revised 17 Nov, first entered as "The five September half-days point to one specific engineer, not routine leave" | Observed: Leave_Register has five "Personal (half day, PM)" entries on 3, 8, 15, 17 and 24 Sep 2026, all approved by VM; no one else has a repeated half-day pattern. Not observed: any reason for the leave | M | A routine reason for the leave lowers it; a resignation, a 1:1 note or a further pulse drop raises it |
| 2026-11-17 | T3's unnamed engineer is P. Nair. Inference only; not shown in the cockpit (DECISIONS.md 11) | For: the half-day pattern above; she is the Staff Engineer T1 says "basically holds the routing thing together"; Engineering pulse fell 3.9 to 3.1 in Jul-Sep with 4 of 5 responding; 11.eml (29 Sep) has Deepa suggesting Vikram does 1:1s, naming no one. Against: T3 names no one, and 10.eml (18 Sep) has Arjun Das asking Deepa to make his remote arrangement permanent | M | Any record naming the engineer, or one tying Deepa's concern to Arjun Das's request |

Entries are revised in place with a dated note when proved wrong. Nothing is deleted.

## Day 3 — 18 November 2026

| Date | Assumption | Source it rests on | Confidence | What would change my mind |
| --- | --- | --- | --- | --- |
| 2026-11-18 | "Snehal" in the rota and the incidents export is the Patil Infra contractor, "S. Patil" | Invoice PIS-114: "On-call SRE support, S. Patil", monthly retainer. GL JV-0902: Patil Infra Services, "On-call support, 18-31 Aug". Snehal first appears in the rota for the week of 17 Aug and first answers an incident on 27 Aug (INC-206). 08.eml (24 Aug): "The contractor starts on the rota this week." Employee_Master excludes contractors and has no Snehal | M | A record giving Snehal's surname, or a second contractor |
| 2026-11-18 | Contractors are people the cockpit knows about, but not staff. "19 staff" stands | Employee_Master: "employees only (contractors are not in Keka)". Both board updates: Team 19. T5 lists Snehal with the team | M | A finance or board definition of "team" that includes contractors |
| 2026-11-18 | pnair@users.noreply.github.com is Priya Nair (VX007) | She is the only Nair in Employee_Master. The address commits only to atlas-engine, the engine she leads (04.eml). It starts committing late at night in June 2026, as her company address does | M | A GitHub account record showing a different owner |
| 2026-11-18 | Jira initials PN, RV, AD and SK are Priya Nair, Rahul Verma, Arjun Das and Sneha Kulkarni | Each matches exactly one Engineering person in Employee_Master. Ticket summaries carry the same initials, e.g. "(pn-1)" | H | A Jira user list that maps them differently |
| 2026-11-18 | The Jira, git, PagerDuty and rota files are 31 Oct snapshots with no history | README.txt: "Exported by IT on 31 Oct 2026", listing engineering/ as "Jira (ATLAS), git history, PagerDuty, on-call rota". Jira shows current status only. Its last Resolved date is 17 Sep and no ticket was created after 1 Aug | M | A dated Jira history export. Until then, a ticket's status on an earlier date comes only from Created and Resolved, and a reopened ticket is invisible |
| 2026-11-18 | The on-call rota shows the plan; the incidents export shows who actually responded | Rota header: "team wiki table, copied". Its week of 17 Aug disagrees with 08.eml and INC-205 (TRANSCRIPT_NOTES.md, Day 3) | M | A rota edit history |
| 2026-11-18 | Priya Nair's late and weekend commits from June 2026 are a sign of work concentrated on her, not evidence of dissatisfaction or intent to leave | Observed: commit times in git_log.csv (TRANSCRIPT_NOTES.md, Day 3). PN holds 35 of 62 Atlas tickets and 7 of 8 In Progress. T5: "Pria has been doing late nights". Not observed: hours worked, or how she feels. Whether the cockpit shows this at all is not decided (DECISIONS.md 11) | M | Her commits stopping, or a resignation, would raise it. A record that the late work was planned would lower it |
| 2026-11-18 | 09.eml is a request to talk about Atlas ownership, nothing more | Text: "Can we talk about Atlas ownership sometime this week? Need some time with you." Sent 1 Sep, 23:47 IST. No reply is in the records | H | A reply, a 1:1 note, or a change of assignee in Jira |
| 2026-11-18 | The CRO in T6b is a role with no holder yet | No CRO in Employee_Master (19 staff). No CRO requisition in Hiring_Tracker. T4: "I hear" | M | A Keka record or offer letter naming a CRO, or a Lever export with a CRO requisition |
| 2026-11-18 | T6b's change has no effective date | The note is undated and says "Or the month after, still finalising". T4 gives no date either | H | A dated announcement, or a Keka export showing the new manager |

## Build — 18 November 2026

| Date | Assumption | Source it rests on | Confidence | What would change my mind |
| --- | --- | --- | --- | --- |
| 2026-11-18 | An incident export covers the months in its file name (Incidents_Aug-Oct_2026.xlsx: August to October 2026). With no such name, it covers the whole months of its first and last incident. A day inside the coverage with no incident is answered "none recorded"; a day outside it is "not covered" | The header recorded in TRANSCRIPT_NOTES.md (Day 3) reads "PagerDuty incident export", with no period. The file name gives one. README.txt lists PagerDuty among the files IT exported on 31 Oct 2026 (ASSUMPTIONS.md, Day 3) | M | A header or README line that states a different period, or an incident in the file outside the named months |
| 2026-11-18 | Revision of the row above, approved provisionally at the Phase 5 checkpoint. A file name sets coverage only when every incident in the records falls inside the months it names. When its own incidents contradict it, coverage is the whole months of the first and last incident, and the answer says the name was not used. Inside coverage with no incident: "none recorded". Outside it: "coverage unavailable", never a count of zero | As above. A file name is a label someone typed; the rows are what the system exported | M | As above, or the real export showing incidents outside the months its name gives |

## Day 4 — 19 November 2026

| Date | Assumption | Source it rests on | Confidence | What would change my mind |
| --- | --- | --- | --- | --- |
| 2026-11-19 | Invoice_PIS-114.pdf's date "01/10/2026" is 1 October 2026, day first. Approved 19 Nov 2026. The string is kept as written | The vendor is in Pune and bills in Indian format. The invoice is for "September 2026 (monthly retainer)", so 1 Oct fits; 10 Jan would put it before the work. Its earlier invoice PIS-108 matches GL JV-0902 (18-31 Aug) | H | A vendor statement or GL posting dating PIS-114 otherwise |
| 2026-11-19 | An on-call rota row covers seven days: its "Week of" date and the six days after | OnCall_Rota.xlsx rows are seven days apart and each "Week of" date is a Monday | M | A rota note or wiki page giving another hand-over day or length |
| 2026-11-19 | "Who ran (processed, handled) payroll" asks who did the payroll work, not what anyone was paid | The question's own words; 01.eml uses "Ran Feb payroll" for the work | H | A request to read such a question as being about pay |
| 2026-11-19 | "Version three" in T6d means Atlas | Board_Update_Apr-Jun_2026.pdf calls Atlas "routing engine v3"; Jira epics "Core routing engine v3" and "Public API v3" are in project ATLAS | H | A record naming a different version three |
| 2026-11-19 | T6c and T6d are known from 19 Nov 2026 10:00 IST and have no recording date, so "this morning" is not dated | The Day 4 release rule (ARCHITECTURE.md 4). The documents' internal date matches T6b's and is a template date | H | A dated original of either voice note |

## Clarification — 19 November 2026: the September leave pattern

This clarifies two entries dated 2026-11-17 above: the assumption about the September half-day leave pattern, and the assumption about T3's unnamed engineer, which cites that pattern. Both entries stay as written.

- The September leave observation in those entries is historical context. It is not admissible evidence now.
- Under the clarified decision 29, approved on 19 November 2026, every leave-register row is withheld whole from user-facing output, whatever its leave type.
- The pattern must not be used in answers, citations, evidence detail, agent profiles, risk assessments or worry list items.
- The source data is unchanged. Leave_Register.xlsx and its stored rows are as ingested; only what the cockpit may show has changed.
- Concern 2 in `voice_notes/T6a.md` was updated on 19 November 2026 to remove this evidence.
- This clarification adds no new inference about the employee or their circumstances, and it does not re-assess the earlier entries.
