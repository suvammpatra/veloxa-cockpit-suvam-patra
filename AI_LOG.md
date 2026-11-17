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

AI assistance (Claude Code, one session):

- Applied my dictated edits to ARCHITECTURE.md (v1.1 and the Day 2 source rows), TRANSCRIPT_NOTES.md (the T3 rows and two paragraphs), ASSUMPTIONS.md (two rows), DECISIONS.md (decision 11) and README.md. It also typed two dictated edits into `voice_notes/T6a.md`: the paragraph under the section 5 table, and "3.9 to 3.1 in the Jul–Sep quarter" in row 2.
- While applying them, flagged two real problems: row 2 of T6a still cites "4.0 to 3.1" in its Evidence cell, and decision 11 keeps the engineer unnamed while TRANSCRIPT_NOTES.md and ASSUMPTIONS.md name P. Nair.
- At my request, reviewed the six docs against the Day 1 and Day 2 source files and corrected the factual errors below. It did not open the Day 3 or Day 4 packs. It added 10.eml and 11.eml to the evidence on the unnamed engineer; the conclusion and its M rating are still mine. It drafted the wording of decisions 12-16 from my T6a reasoning and the decision 8 status note, and reviewed T6a without editing it.
- After I approved it, wrote the release-time change into ARCHITECTURE.md and decision 2: `released_on` becomes a 10:00 IST timestamp, with a 09:59 versus 10:00 test. The 10:00 rule comes from the challenge email.
- At my request, applied the seven T6a corrections from its review to `voice_notes/T6a.md`: 3.9 not 4.0, four of five responding, 11.eml added, the full 06.eml line, no November date for T1, Atlas moved past 15 September with no new date, no hint at which engineer, and no claim that the letter names Atlas. The reasoning and conclusions in T6a are still mine.
- The review also found two Day 1 errors whose origin is not recorded: the GL Apr-Sep total in ARCHITECTURE.md (Rs.2,34,07,530; the 28 lines sum to Rs.2,34,37,530) and "Kayka" filed under T2's Summary instead of its Key points. Both are corrected in place and not counted below.

| Date | What I was establishing | What AI returned | Where it was wrong | What the record now says | How it was caught |
| --- | --- | --- | --- | --- | --- |
| 2026-11-17 | Applying the Day 2 documentation edits | Applied my dictated wording as given, checking it for internal consistency but not against the source files | Several lines did not match the files: "Liver" and "twenty-two open roles" are in T3's Key points, not its Summary; the GL payroll line (Apr-Sep) was described as matching "the register", which covers Jan-Mar; the leave register says "Exam", not CFA; the Keka Hire tracker was assumed complete; the resignation letter was called "signed" (it has a typed name only) | Corrected in ARCHITECTURE.md, ASSUMPTIONS.md and TRANSCRIPT_NOTES.md | Claude Code's source review later the same day, at my request |
| 2026-11-17 | Whether the Sid paragraph in TRANSCRIPT_NOTES.md names three sources | Said it named only two | The paragraph opens with T3's "Sid from marketing" line, then the letter and Employee_Master: three | Paragraph unchanged | Claude Code, re-reading T3 during the source review |
