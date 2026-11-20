# Veloxa CXO Cockpit

An evidence-backed executive cockpit for **Veloxa Technologies**, built for the Hiyaku Systems 5-day hackathon (16–20 November 2026). Individual entry.

The CEO asks one question and gets a short answer that cites the specific records behind it, states a confidence level, and says "I don't know" or "the sources disagree" when that is the honest answer. The cockpit opens on her worry list, as she asked in voice note T6a: up to three ranked concerns, each backed by evidence and carrying its own weakest link. If only two are well supported it shows two rather than padding the list, and the question box stays on the same screen. The same records ground 14 employee agents, one per person in Engineering, Finance, People & Ops and Marketing. The CEO picks one and asks about their role, work or history. Each answer comes from that person's records, with citations and confidence. It is a briefing about the person, not the person speaking, and it invents nothing (see `DECISIONS.md`, decisions 24 and 35).

Veloxa is a fictional B2B SaaS company in Bengaluru with 19 staff and about 66 customers. Its data room is contradictory: machine-generated call transcripts that mishear names and figures, and system exports that are better but have quirks of their own. Nobody will say which source is right. Deciding what to trust is the problem this system is built around.

## Status

Day 5 of 5 — 20 November 2026, final submission. Built and checked:

- ingestion of the release packs for Days 1-4;
- evidence search;
- question answering with citations and confidence;
- the 14 agent profiles, and questions to each agent answered from that person's records;
- the worry list;
- a one-page interface.

453 automated tests pass. The release pack is not in the repository; you supply it (see step 2 below and `DECISIONS.md`, decision 8). No LLM is needed, and no API key.

Not built: invented agent personas, personal details about anyone, and agents that act after the data ends (`SYSTEM_DESIGN.md`, section 9).

## Set up and run (Windows PowerShell)

Four scripts in the repository root do everything. Each prints PASS, WARN or FAIL lines and says what to do when something is missing.

| Script | When | What it does |
| --- | --- | --- |
| `.\setup.ps1` | Once, and after pulling new requirements | Creates `.venv` if missing, installs `requirements.txt`, checks the release pack (read only), writes `.env`. Never loads data |
| `.\setup-demo-data.ps1` | Once | Loads Days 1-4 and the three reviewed files into the demo database. Refuses a database that already holds data |
| `.\start.ps1` | Every time | Starts the cockpit with `.venv` Python. Refuses an empty or missing database, or a port in use |
| `.\verify.ps1` | Any time | Checks the interpreter, the database and, if the cockpit is running, the API |

### 1. Prerequisites

- Windows with Windows PowerShell 5.1 (built in) or PowerShell 7.
- Python 3.11 or later on `PATH`. It was built with 3.13. Check with `python --version`.
- The release pack zip from the organisers. It is not in this repository.
- Scripts must be allowed to run. `Get-ExecutionPolicy -Scope CurrentUser` should say `RemoteSigned`. If it does not, run this once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

From a fresh clone, the whole sequence is (each step is explained below):

```powershell
git clone <repository URL> veloxa-cxo-cockpit
cd veloxa-cxo-cockpit
Expand-Archive -Path '<path to the release pack zip>' -DestinationPath 'C:\veloxa-pack'
$pack = (Get-ChildItem 'C:\veloxa-pack' -Recurse -Directory -Filter 'Day1_Mon_16Nov').Parent.FullName
.\setup.ps1 -SourcePack $pack
.\setup-demo-data.ps1
.\start.ps1
# then, in a second PowerShell window in the same folder:
.\verify.ps1
```

### 2. First-time installation and the release pack location

The release pack is supplied separately, never committed (`DECISIONS.md`, decision 8). Extract the zip anywhere outside the repository, for example:

```powershell
Expand-Archive -Path '<path to the release pack zip>' -DestinationPath 'C:\veloxa-pack'
```

`-SourcePack` must name the folder that directly holds `Day1_Mon_16Nov`, `Day2_Tue_17Nov`, `Day3_Wed_18Nov` and `Day4_Thu_19Nov`. Zips often add one or two wrapper folders. To find the right folder:

```powershell
(Get-ChildItem 'C:\veloxa-pack' -Recurse -Directory -Filter 'Day1_Mon_16Nov').Parent.FullName
```

Then, from the repository root, pass the folder that command printed:

```powershell
.\setup.ps1 -SourcePack '<folder printed above>'
```

- The pack is only read. Nothing is written into it.
- Put the path in single quotes. If the path itself contains a single quote, write it twice, as in `'D:\Packs\O''Brien'`.
- `setup.ps1` records three values in `.env`, which is not committed:
  - `VELOXA_SOURCE_PACK`: the release pack folder;
  - `VELOXA_DATA_DIR`: the demo data folder. The default is `veloxa-demo-data` next to the repository; change it with `-DataDir '<folder>'`;
  - `VELOXA_PORT`: the port, by default `8010`; change it with `-Port <number>`.
- Running `setup.ps1` again is safe. It keeps `.venv` and the values already in `.env` unless you pass new ones.
- The demo data folder must be outside the repository. The repository's own `data\cockpit.db` is never used.

### 3. Demo data (first time only)

```powershell
.\setup-demo-data.ps1
```

It checks the four day folders and that the target database is missing or empty. It then loads, in this order:

| Day folder | Release day (known from 10:00 IST) | Export date given |
| --- | --- | --- |
| `Day1_Mon_16Nov` | 2026-11-16 | - |
| `Day2_Tue_17Nov` | 2026-11-17 | 2026-10-31 |
| `Day3_Wed_18Nov` | 2026-11-18 | 2026-10-31 |
| `Day4_Thu_19Nov` | 2026-11-19 | - |

After the four days it loads `data\aliases_reviewed.csv`, `data\conflicts_reviewed.json` and `data\org_reviewed.json`, then prints a summary. The expected result is 38 sources, 1,847 evidence rows, 20 people (19 employees and 1 contractor), 21 aliases, 18 reporting lines, 19 memberships, 3 conflicts, 9 claims (1 reported event), 62 Jira tickets and 11 incidents.

Running it again on a loaded database does nothing. If a folder holds some other data, it stops instead of loading twice. The release pack is only read.

### 4. Start the cockpit

```powershell
.\start.ps1                 # then open http://127.0.0.1:8010/
.\start.ps1 -Port 8011      # if 8010 is taken
```

It checks the database (read only) before starting, and prints the URL. Stop it with Ctrl+C in its window.

The page opens on the worry list. Each worry shows its confidence, any open conflict, what would change it, and its evidence; each evidence key opens the record. Below is the question box. The Agents link in the sidebar opens the Agents workspace. The "As of" box changes the date for everything on the page; leave it empty for now. "Recorded by" shows only what the company had recorded by that date.

Questions that show the rules:

| Question | What happens |
| --- | --- |
| When is Atlas GA? | 15 Dec 2026 in Jira, moved from 15 Sep, with sources quoted |
| Is the Atlas engine feature-complete? | The open conflict C-ATLAS-DONE, both sides cited, Low confidence |
| Who was on call in the week of 17 Aug 2026? | From the on-call rota only, never from commit records (decision 30) |
| Does Priya work late? | Refused: no judgement of anyone's hours (decisions 23, 28) |
| Can you make a list of everyone ranked by who's likely to quit? … | T6c. Refused: no resignation ranking and no private messages; offers the continuity view (decision 34) |
| What is our workforce continuity? | Departures, requisitions, contractors and concentrated work, with no one scored |
| Bad news, Pria resigned this morning. … What does this do to version three? | T6d. The report is kept unverified, "Pria" is linked only at medium confidence, and the Atlas (v3) work and dates come from records. The answer lists what is not established (decision 33) |

Set "As of" to 2026-11-19 09:59 and ask the T6d question again: the report is not known yet. At 10:00 it is.

**Asking an agent.** Click Agents in the sidebar, then search for a person by name, department or status. Their profile appears on the left, in four tabs: Overview, Workload & Projects, Historical Events, and Evidence & Sources. The interview panel stays on the right (on a phone, at the bottom of the screen). Ask about their role, manager, history, projects, workload or pending changes. The answer:

- starts "From records about <name> …, not <name> speaking";
- lists each fact with its evidence keys, labelled verified (High confidence) or, below High, disputed (an open conflict), inferred (a name link below High) or lower confidence;
- says "Not established in available records" for anything the records do not hold, such as personal life, opinions or feelings;
- refuses pay, working hours, performance, intentions and private messages, exactly as the main question box does.

| Agent and question | What happens |
| --- | --- |
| Priya Nair: What is she working on? | Her Atlas tickets and epics from the 31 Oct Jira export, with keys. Labelled disputed: the open conflict C-ATLAS-DONE touches that export |
| Rahul Verma: What is his workload? | His open Atlas tickets and story points at the 31 Oct Jira export, with keys |
| Meera Iyer: What is her workload? | Not established: no workload record covers Finance |
| Any agent: What are their hobbies? | Not established; nothing is invented |
| Any agent: How much do they earn? | Refused (individual pay) |

### 5. Verify

```powershell
.\verify.ps1
```

Checks, each PASS or FAIL:

- the `.venv` interpreter;
- the data folder and the database (read only, against the counts above);
- the three reviewed files;
- with the cockpit running: who owns the port, `/health`, the worry list, the 14 agents, an Atlas answer, T6c, and T6d at 09:59 and 10:00.

Run it in a second window while `start.ps1` runs. The exit code is 0 only when everything passes.

### 6. Tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

All tests use their own temporary databases. None touches the demo data or `data\cockpit.db`.

### 7. Troubleshooting

| Message or symptom | Cause and fix |
| --- | --- |
| `...setup.ps1 cannot be loaded because running scripts is disabled` | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or `powershell -ExecutionPolicy Bypass -File .\start.ps1` |
| `The project virtual environment is missing` | Run `.\setup.ps1` |
| `source pack ... folder not found` or `folder missing` | The path in `.env` (`VELOXA_SOURCE_PACK`) is wrong. Run `.\setup.ps1 -SourcePack '<folder that holds the four day folders>'` |
| `Not starting: the demo database is not ready` with `it is empty` or `No database at` | The demo data was never loaded into this folder. Run `.\setup-demo-data.ps1` |
| `reviewed aliases`, `reviewed conflicts` or `reviewed organisation records: none loaded` | A reviewed file was not loaded. If the folder is otherwise complete, load the missing file into it with `.\.venv\Scripts\python.exe -m app.ingestion aliases data\aliases_reviewed.csv` (or `conflicts` / `org` with its file). Each file loads only once and never overwrites |
| `already holds data ... Not ingesting again` | The folder holds a partial or different load. Keep it for inspection, and load into a new empty folder: `.\setup.ps1 -DataDir '<new folder>'`, then `.\setup-demo-data.ps1` |
| `port 8010: already in use` | The cockpit is already running (open the URL), or another program uses the port: `.\start.ps1 -Port 8011` |
| An agent question returns `404 Not Found` while the agent's profile loads | The cockpit was started before the code was updated. The page is read fresh on each load, but the server keeps the routes it started with. Stop it with Ctrl+C in its window and run `.\start.ps1` again |
| `is inside the repository` | The data folder must be outside the repository. Run `.\setup.ps1 -DataDir '<folder outside the repository>'` |
| The page shows `no dated records`, an empty worry list, or agents with `identity_not_established` | The server is reading an empty database, often because it was started without `start.ps1`. Stop it, then run `.\verify.ps1` and `.\start.ps1` |
| Answers look old or Day 4 items are missing | Clear the "As of" box. Day 4 records are known only from 19 Nov 2026 10:00 |

## Command line

With `.env` written by `setup.ps1`, the command line uses the same demo database:

```powershell
$py = ".\.venv\Scripts\python.exe"
& $py -m app.readiness                                       # read-only database check (add --strict or --json)
& $py -m app.worries --as-of 2026-11-19T12:00                # the worry list (add --json)
& $py -m app.answering "When is Atlas GA?" --as-of 2026-11-19T12:00
& $py -m app.agents "Priya Nair" --as-of 2026-11-19T12:00
& $py -m app.retrieval "atlas release date" --as-of 2026-11-19T12:00
& $py -m app.ingestion status
```

The API serves the same results:

- `GET /api/worries`, `/api/ask?q=`, `/api/evidence/{key}`, `/api/search`, `/api/agents`, `/api/agents/{agent}` and `/api/agents/{agent}/ask?q=` (for example `/api/agents/priya-nair/ask?q=What is she working on?`);
- each takes `as_of` and `mode` (`known` or `recorded`);
- `/health` reports the database.

## Documentation

| File | Contents |
| --- | --- |
| `SYSTEM_DESIGN.md` | Standalone design of the system as built: components, diagrams, data model, agents, answer lifecycle, trust and safety, stack, deployment |
| `ARCHITECTURE.md` | Data model, trust ladder, conflict registry, point-in-time behaviour; section 16 records each build checkpoint |
| `ASSUMPTIONS.md` | Assumptions, dated, with confidence and what would overturn them |
| `TRANSCRIPT_NOTES.md` | Suspected mishearings and contradictions, with evidence and conclusions |
| `DECISIONS.md` | Choices that could be defended either way, and what each costs |
| `AI_LOG.md` | What was delegated to AI, where it was wrong, and what changed |
| `voice_notes/` | Written responses to the CEO voice notes T6a onward |
