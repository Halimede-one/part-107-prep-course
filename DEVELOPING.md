# Developing the Part 107 course

This document is for the maintainer and for developers who change the code or
rebuild the content. Instructors who vet the material start with
[README.md](README.md).

The course runs from this folder with no packages to install. Python 3.8 or
newer is the only prerequisite, plus a model backend (below).

## Run it

```bash
./start.sh                          # the provider in config.json (anthropic)
./start.sh --provider claude_code   # your Claude plan, for this run only
./start.sh --instructor             # adds the Instructor button, which edits the course material
python3 server.py --instructor --provider claude_code   # the same, without start.sh
```

Then open http://localhost:8107. `start.sh` passes its arguments to `server.py`
and opens the browser. `--provider` replaces `provider` in `config.json` for one
run. Use it instead of editing `config.json`, because that file is tracked and a
change to it would reach the next commit. With the `anthropic` provider and no
key in the environment, the server prints a note at start-up.

Without `--instructor` (or `"instructor": true` in `config.json`), the
instructor workspace does not exist, so a student's copy cannot change its
course material.

## Choosing a backend

The backend is set by `provider` in `config.json`, or by `--provider` for one run.

| Provider | Needs | Notes |
|---|---|---|
| `anthropic` (default) | `ANTHROPIC_API_KEY` in your environment, and connectivity | Best for distribution: each student supplies their own key. Billed per token. Can use cited web search for questions outside the course material once `supports_web_search` is switched on. |
| `claude_code` | [Claude Code](https://code.claude.com/docs/en/quickstart) installed and signed in to a Claude plan | Draws on your own plan instead of API billing. Personal use only: plan allocation is per-user and cannot be shared with students. Each instructor uses their own plan. The chat tutor searches the course material, and the web while `supports_web_search` is true. Tested with Claude Code 2.1.235. |
| `ollama` | [Ollama](https://ollama.com) running locally with the model in `config.json` pulled | Fully offline and free. Free-form answers are limited to the course material. |
| `mock` | nothing | Canned blocks for testing the plumbing without a model. |

Your API key is read from the environment and is never stored in this folder.

Two notes on the `claude_code` backend. It runs `claude -p` with all tools disabled
for lessons, questions, and feedback, because the course has no business reading or
writing your files. The chat and the instructor's authoring assistant get read-only
tools instead. They run in the knowledge-base folder, may also read the lessons and
the reference facts, and nothing else; with `supports_web_search` they may also search
the web. No tutor call loads your Claude Code memory, settings, or MCP servers, so
your claude.ai connectors and plugins stay out of the tutor's reach and its context.
And setting
`ANTHROPIC_API_KEY` in your shell makes Claude Code bill to the API instead of your
plan, so keep that variable out of your shell profile if you use this backend.

Web search on the `anthropic` backend is off by default. The tool format is wired
but was not verified against the current API from the build environment. Turn it on
by setting `supports_web_search` to true, ask the tutor something outside the course
material, and confirm the answer carries a web link before leaving it on.

The build tools that call the model (`tools/enhance_kb.py`, `tools/probe_chat.py`)
read `provider` from `config.json` and have no `--provider` flag. For a build pass
on your plan, set `provider` to `claude_code` in your copy of `config.json`, and do
not commit that change. `enhance_kb.py` also takes `--config` with another file.

## How the course works, in pictures

The README shows the student's path and the gears. The three diagrams below show
the system. They were drawn by hand from the code and prompts in this folder, and
they live in `docs/diagrams/` as SVG files. Update them when the code they
describe changes.

### Data flow

![Data flow: knowledge base, course content, student data](docs/diagrams/data-flow.svg)

Three kinds of data meet in the server. The knowledge base is built locally from
FAA and eCFR documents. Its source layer is cut mechanically from the documents.
A model writes its explanation layer from one chunk at a time. Those chunks are
tagged as derived, and the source text outranks them. Retrieval searches both
layers for the Ask box.

The course content is authored by hand and vetted against the source chunks. It
holds the ACS objectives, the per-unit lessons, the ground-truth facts, and the
fixed practice exam. Each tutor message carries the current unit's content,
citation links, and facts.

Student performance data lives in `progress/`, which is per run and not shipped.
The ledger is Markdown a human can read. Mastery, the current unit, and
readiness are derived from it in code. The same record feeds the course map
through `/api/state`.

### How the model teaches

![A teaching turn](docs/diagrams/llm-teaching-turn.svg)

Every model call carries the orchestrator rules, one stage prompt, and the vetted
material for the unit. The reply is one JSON block that the fixed shell renders.
The model writes the lesson, the question, and the feedback. The server checks
each question before it shows it: three distinct options, one key, and a
rationale. Where the question names a vetted fact, the keyed option must state
that fact. A question that fails is written once more. An instructor's own
questions on a unit come first and need no model call. The server keeps the
answer key and scores the student's choice by comparison. It records the attempt
and decides the next step in code. The feedback call then gives the model the
result and what happens next. The model explains a decision it did not make.

### How the model answers questions

![Ask the tutor](docs/diagrams/llm-ask-the-tutor.svg)

The chat panel takes any question at any time. The server retrieves the best
matching chunks from the knowledge base. It adds the unit on screen and recent
chat turns, and sends them with the question. On the `claude_code` backend the
model can also search the course material itself: the knowledge base, the unit
lessons, and the reference facts. It cannot read the practice exam or the
student's progress. When the course material does not cover the question, it
searches the web, official FAA and government sources first. The model answers
from that material only, paraphrased and cited with links, and streams the
answer as it writes. If no material covers the question, it says so. On the
`anthropic` backend, web search is an optional fallback and is off by default.

## Estimated AI costs

Estimated October 16, 2026, for one student working through all 77 units on the
`anthropic` backend or an equivalent Bedrock endpoint. The call counts follow the
course rules: one lesson per unit, two correct checks in a row to master it, one
re-teach per miss, 15 spaced reviews, and one debrief per practice exam. Prompt
sizes were measured from the authored Task A units. Output sizes come from the
recorded runs in `progress/metrics.jsonl`.

| Scenario | Model calls | Input tokens | Output tokens | Total tokens |
|---|---|---|---|---|
| Low: Fast-track, 10 percent miss rate, 5 chat questions | 530 | 1.4M | 0.34M | 1.7M |
| Mid: Guided, 25 percent miss rate, 15 chat questions | 760 | 2.1M | 0.68M | 2.8M |
| High: 40 percent miss rate, 30 chat questions | 1,180 | 3.5M | 1.37M | 4.8M |

Each teaching call sends about 1.8k tokens of system prompt and 0.7k to 0.9k tokens
of unit material. Each miss adds three calls. Output tokens are 55 to 66 percent of
the cost.

Cost per student on Amazon Bedrock, in US dollars. Global endpoints bill at the
first-party rate. Regional endpoints add 10 percent. The cached columns assume the
system prompt is cached, which needs a `cache_control` marker that `llm_client.py`
does not send yet.

| Scenario | Opus 5.5 global | Opus 5.5 regional | Opus 5.5 cached | Sonnet 5.5 global | Sonnet 5.5 regional | Sonnet 5.5 cached |
|---|---|---|---|---|---|---|
| Low | $12 | $14 | $9 | $6 | $7 | $5 |
| Mid | $22 | $24 | $18 | $11 | $12 | $9 |
| High | $41 | $45 | $34 | $21 | $23 | $17 |

Rates used, per million tokens: Opus 5.5 at $4 input, $20 output, $0.20 cache read,
$5 cache write. Sonnet 5.5 at $2 input, $10 output, $0.10 cache read, $2.50 cache
write. Opus 5 and Opus 4.8 cost about 25 percent more than Opus 5.5. Sonnet 4.6
costs 50 percent more than Sonnet 5.5.

Assumptions:

- The estimate was made before Tasks B to F were written. Their units were assumed
  to match the Task A sizes, plus 10 to 25 percent in the mid and high scenarios.
  The sizes were not measured again after the units were written on October 17, 2026.
- Both models think by default, and thinking bills as output. The output sizes were
  measured on Opus 5. The mid and high scenarios add 25 and 50 percent for thinking.
  Sending effort `low` holds output near the measured values.
- The chat on this backend is one call over three retrieved chunks and the unit on
  screen. It is cheaper than the recorded `claude_code` chat calls, which also
  searched the course and the web.
- The `context_tokens` recorded by the `claude_code` backend include Claude Code's
  own overhead. The API path sends 2.4k to 2.9k tokens per teaching call.
- The rates come from Anthropic's pricing page and its Bedrock endpoint rule.
  Confirm them on the AWS Bedrock pricing page before budgeting.

## Running the tests

```bash
python3 -m unittest discover -s tests -v
```

The browser tests run headless Chrome over the pages in `tests/fixtures/`. They
need `google-chrome`, `chromium`, or `chromium-browser` on the PATH, and they skip
without it. `test_pdf_to_chunks_to_retrieval` needs `pdftotext` and the Python
package `reportlab`, and it skips without them.

## Where this is up to

Built and tested: the interface shell, the server, the four backends, retrieval over
the knowledge base, deterministic scoring, the student ledger with the course map,
the adaptive tutor (teach, quiz, downshift on a miss, park after repeated misses at
the deepest gear, spaced review at task boundaries), the practice exam and the
readiness gate, and the build tools.

Written but not vetted: a Guided lesson and reference facts for all 77 units
(Task A and the gear-3 exemplars first; Tasks B to F on October 17, 2026, against
the knowledge base), Foundational files for 8 units, and the 20-item practice
exam. See `curriculum/regulations/STATUS.md`. Instructors vet them next; the
README is their guide.

Built on October 9, 2026: the knowledge base, both layers, from 39 sources (the
current eCFR text of the CFR parts, the statute, the ACS, AC 107-2A, the study
guide, the FAA sample questions, three handbook chapters, the AIM airspace and
UAS chapters, and the faa.gov guidance pages). `knowledge-base/BUILD.md` records
the build, its decisions, and two currency findings for the vetting step.

Built on October 16, 2026: all three speeds for every unit with a Guided lesson,
with the tutor's first Foundational lesson saved as a draft file, and the
instructor workspace (`./start.sh --instructor`). The plan and its as-built record
are in `docs/plans/instructor-interface.md`.

Built on October 17, 2026: the server checks each question the tutor writes, and
logs every question asked, so the tutor does not repeat one across sessions. The
workspace's Questions tab takes an instructor's guidance and own questions per
unit. The plan and its as-built record are in `docs/plans/check-questions.md`.

Built on October 22, 2026: the release to instructors. The `--provider` flag,
a refusal of POSTs from other sites, the README as the instructor guide, and this
document. The plan is `docs/plans/instructor-release.md`.

Not yet done:

- Vetting of all content and the practice exam against the source text.
- A full run with a real model from Task A to the practice exam.
- A hand check of the check questions with a real model.
- The `anthropic` backend: no course search for the chat, and web search not verified.
- Pending questions are not restored from `progress/questions.jsonl` after a restart.
- `tools/check_integrity.py` does not check the files in `questions/`.
- One chat answer on `claude_code` took 91 s on October 22, 2026, against about
  25 s on October 10. Not investigated.
- Windows, and dictation in Safari, are not tested.

## Merging an instructor branch

Instructors work on a branch named `vetting/<name>`. They commit only course
material (`git add curriculum reference questions mock`) and open a pull request
into `main`, from a fork if they have no write access.

- Give each instructor whole chapters. Each unit is one row in `STATUS.md` and a
  few rows in the facts table, so branches that touch different units merge
  without conflict.
- Two branches can each add a tutor draft for the same `.gear3.md` file. Keep one
  of them, and keep the matching `STATUS.md` cell.
- Check that a pull request does not change code, prompts, or `config.json`.
- After each merge, run the strict integrity check and the tests, then regenerate
  the vetting guide and commit it:

  ```bash
  python3 tools/check_integrity.py
  python3 -m unittest discover -s tests
  python3 tools/vetting_guide.py
  ```

## Building the content locally

These steps need the PDFs, network access, and a model, which is why they run on
your machine rather than in the build environment.

1. Run the tests: `python3 -m unittest discover -s tests`. The build passes call
   the model through `provider` in `config.json`. To draw on your plan, set it to
   `claude_code` in your copy and do not commit that change.

2. Fetch the sources: `python3 tools/fetch_sources.py`. It reads the `fetch`
   block of each entry in `knowledge-base/sources.json` and writes the PDF the
   builder expects into `knowledge-base/pdfs/`: FAA PDFs are downloaded as
   published; the CFR parts are printed from the current eCFR text, and the
   AIM, faa.gov, and Federal Register pages from their main content, with
   headless Chrome. Needs network access and Chrome or Chromium. A source
   whose PDF is present is skipped; `--redo` refreshes it. The run is noted
   in `knowledge-base/pdfs/fetch-log.json`.

3. Build the source layer of the knowledge base. Needs `pdftotext` (poppler):
   `python3 tools/build_kb.py`. Check a few chunks in `knowledge-base/regulations/`
   against the PDF: section boundaries, page numbers, and the canonical links.
   If a source's headings are not cut where you expect, adjust its `heading`
   preset or give it a custom regex in the manifest and rebuild that source.

4. Add the explanation layer: `python3 tools/enhance_kb.py`. One companion chunk
   per source chunk, written by the model from the chunk and nothing beyond it,
   tagged `kind: explanation`. Spot-check a handful for added facts; the prompt
   forbids them, and a companion that adds one should be deleted and regenerated.
   `knowledge-base/EXPLANATION-LAYER.md` describes the layer and the vetting
   procedure, and `python3 tools/check_companions.py` lists the numbers in each
   companion that its source chunk does not contain.

5. Check the links and the structure:
   `python3 tools/check_links.py` and `python3 tools/check_integrity.py`.
   On October 22, 2026, eCFR answered `429 Too Many Requests` after about 30
   requests, so 145 of 207 links showed `FAIL` without being broken. Read the
   status code before you change a link. The README does not ask instructors to
   run this check for that reason.

6. Vet the authored content. For each unit in `STATUS.md`, read the content and
   its reference facts against the source chunks and mark the row vetted, or fix
   it. Do the same for every practice-exam item. The notes column holds the open
   questions the author flagged. The README has the instructors' procedure, and
   `docs/vetting-guide.html` the per-unit checklist.

7. Run the course with a real model: `./start.sh`, choose Fast-track, work through
   Task A, miss a question on purpose to see the downshift, ask the tutor a
   free-form question, and take the practice exam. Watch the terminal for errors
   and `progress/student-ledger.md` for the state.

8. All 77 units have a Guided lesson and reference facts (Tasks B to F were
   written on October 17, 2026; see `docs/plans/content-tasks-b-to-f.md`). To add
   or revise content, follow the conventions at the bottom of `STATUS.md`, by hand
   or in the instructor workspace (see the README), and run the integrity check
   without `--allow-incomplete`.

9. Package: `python3 tools/package.py` writes `dist/part107-course-<date>.zip`,
   refusing to package a course that fails the integrity check. Unzip it somewhere
   else and run it on each backend before handing it to anyone.

## How it fits together

```
ui/              the fixed shell: renders blocks, posts responses, draws the map and readiness;
                 instructor.js is the instructor workspace
server.py        serves the shell, routes responses, scores answers, calls the model,
                 saves tutor drafts and instructor edits
status.py        changes one unit's row of STATUS.md when a lesson file is saved
orchestrator.py  which unit, which gear, which stage comes next; task boundaries and review
mockexam.py      practice-exam attempts, lookup scoring, readiness
llm_client.py    provider adapters (anthropic, claude_code, ollama, mock)
retrieval.py     lexical search over the knowledge base, for free-form questions
items.py         table parsing, vetted items, deterministic lookup scoring
ledger.py        the student ledger: mastery, gears, parking, attempts, exam attempts
prompts/         the tutor: global rules, one prompt per stage, the block and response schemas;
                 author.md is the instructor's authoring assistant
curriculum/      objectives, per-unit teaching content, vetting status
reference/       the per-unit ground-truth facts the tutor keys answers to
questions/       per-unit instructor guidance and questions, written by the workspace's Questions tab
mock/            the fixed practice exam
knowledge-base/  the source manifest and the two-layer corpus (built locally)
sources/         the authoritative references and their precedence
tools/           fetch_sources, build_kb, enhance_kb, check_companions, probe_retrieval, probe_chat,
                 check_integrity, check_links, vetting_guide, package
tests/           the test suite; fixtures live under tests/fixtures
docs/            diagrams/ (the SVG diagrams), plans/ (implementation plans with as-built records),
                 mockups/, investigations/, and vetting-guide.html (generated by tools/vetting_guide.py)
progress/        the student's ledger and logs, per run; not tracked and not packaged
```

Design principles behind these choices are in `LLM_COURSEWARE_DESIGN_AND_PRINCIPLES.md`,
the build plan is in `IMPLEMENTATION_PLAN.md`, and each later feature has its plan
in `docs/plans/`.
