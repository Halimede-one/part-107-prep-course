# FAA Part 107 course

An adaptive, LLM-tutored course for the FAA Part 107 remote pilot knowledge test.
Content is grounded in the CFR and FAA guidance; the model teaches over it rather
than being the authority on the rules.

Runs from this folder with no packages to install. Python 3.8 or newer is the only
prerequisite, plus a model backend (below).

## How the course works, in pictures

Five diagrams, drawn by hand from the code and prompts in this folder. They live
in `docs/diagrams/` as SVG files. Update them when the code they describe changes.

### The student's path

![The student's path through the course](docs/diagrams/student-journey.svg)

The student picks a pace at intake: Fast-track, Guided, or Foundational. That
choice sets the starting gear for every unit. The course then works through the
77 tracked units in order. Each unit is taught, then checked with a question.
Two correct answers in a row, on different questions, master the unit.

At each task boundary the course re-checks up to three mastered units from
earlier tasks, one question each. A miss sends that unit back for re-teaching
at the Guided gear. Units that were set aside come back here with a fresh angle.

The practice exam is open at any time. It has 20 fixed, human-vetted items and
is scored by lookup. The readiness gate is decided from the ledger, in code. It
needs every unit mastered, none set aside, and two exam passes at 85 percent or
better. The model never decides readiness.

### Faster or deeper: the gears inside one unit

![Three gears, one bar](docs/diagrams/gears.svg)

A gear is a depth of teaching, not a different standard. Fast-track states the
point in one or two sentences and goes to the check. Guided gives the full lesson
with a worked example and the common misreading. Foundational breaks the point
into its smallest steps with a different representation, such as a picture or a
memory handle. Foundational exists only where it was authored.

A student who knows the material answers two checks at Fast-track and moves on.
A miss moves only that unit one gear deeper. There the tutor teaches it a
different way, never the same explanation slower. At the deepest gear the unit
offers, the first miss brings a re-teach from a new angle. The second miss in a
row sets the unit aside. The course moves on and brings the unit back at the next
task boundary. Readiness stays closed until that unit is mastered.

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
The model writes the lesson, the question, and the feedback. The server keeps the
answer key and scores the student's choice by comparison. It records the attempt
and decides the next step in code. The feedback call then gives the model the
result and what happens next. The model explains a decision it did not make.

### How the model answers questions

![Ask the tutor](docs/diagrams/llm-ask-the-tutor.svg)

The chat panel takes any question at any time. The server retrieves the best
matching chunks from the knowledge base. It adds the unit on screen and recent
chat turns, and sends them with the question. The model answers from that
material only, paraphrased and cited with links, and streams the answer as it
writes. If the material does not cover the question, it says so. Web search is
an optional fallback on the `anthropic` backend and is off by default.

## Run it

```bash
export ANTHROPIC_API_KEY=your-key   # for the default backend
./start.sh                          # or: python3 server.py
```

Then open http://localhost:8107. If `./start.sh` reports a permission error, run
`chmod +x start.sh` once.

## Choosing a backend

The backend is set by `provider` in `config.json`.

| Provider | Needs | Notes |
|---|---|---|
| `anthropic` (default) | `ANTHROPIC_API_KEY` in your environment, and connectivity | Best for distribution: each student supplies their own key. Billed per token. Can use cited web search for questions outside the course material once `supports_web_search` is switched on. |
| `claude_code` | [Claude Code](https://code.claude.com/docs/en/quickstart) installed and signed in to a Claude plan | Draws on your own plan instead of API billing, so it costs nothing extra while you build. Personal use only: plan allocation is per-user and cannot be shared with students. |
| `ollama` | [Ollama](https://ollama.com) running locally with the model in `config.json` pulled | Fully offline and free. Free-form answers are limited to the course material. |
| `mock` | nothing | Canned blocks for testing the plumbing without a model. |

Your API key is read from the environment and is never stored in this folder.

Two notes on the `claude_code` backend. It runs `claude -p` with all tools disabled,
because the course has no business reading or writing your files. And setting
`ANTHROPIC_API_KEY` in your shell makes Claude Code bill to the API instead of your
plan, so keep that variable out of your shell profile if you use this backend.

Web search on the `anthropic` backend is off by default. The tool format is wired
but was not verified against the current API from the build environment. Turn it on
by setting `supports_web_search` to true, ask the tutor something outside the course
material, and confirm the answer carries a web link before leaving it on.

## Running the tests

```bash
python3 -m unittest discover -s tests -v
```

## Where this is up to

Built and tested: the interface shell, the server, the four backends, retrieval over
the knowledge base, deterministic scoring, the student ledger with the course map,
the adaptive tutor (teach, quiz, downshift on a miss, park after repeated misses at
the deepest gear, spaced review at task boundaries), the practice exam and the
readiness gate, and the build tools.

Authored but not vetted: teaching content and reference facts for Task A (8 units)
and for the gear-3 exemplars (UA.I.B.K16 and UA.I.E.K3 with K3a to K3d), and the
20-item practice exam. See `curriculum/regulations/STATUS.md`.

Built on October 9, 2026: the knowledge base, both layers, from 39 sources (the
current eCFR text of the CFR parts, the statute, the ACS, AC 107-2A, the study
guide, the FAA sample questions, three handbook chapters, the AIM airspace and
UAS chapters, and the faa.gov guidance pages). `knowledge-base/BUILD.md` records
the build, its decisions, and two currency findings for the vetting step.

Not yet done, all local: content for Tasks B to F, vetting of everything against
the source text, and a run with a real model. Until a unit has content, the tutor
declines to teach it, by design.

## Building the content locally

These steps need the PDFs, network access, and a model, which is why they run on
your machine rather than in the build environment.

1. Run the tests, then set `provider` to `claude_code` in `config.json` so the
   build passes draw on your plan: `python3 -m unittest discover -s tests`.

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
   `python3 tools/check_links.py` and `python3 tools/check_integrity.py --allow-incomplete`.

6. Vet the authored content. For each unit in `STATUS.md`, read the content and
   its reference facts against the source chunks and mark the row vetted, or fix
   it. Do the same for every practice-exam item. The notes column holds the open
   questions the author flagged.

7. Run the course with a real model: `./start.sh`, choose Fast-track, work through
   Task A, miss a question on purpose to see the downshift, ask the tutor a
   free-form question, and take the practice exam. Watch the terminal for errors
   and `progress/student-ledger.md` for the state.

8. Author Tasks B to F against the knowledge base, one task per batch, following
   the conventions at the bottom of `STATUS.md`. Add reference facts for each unit.
   Re-run the integrity check after each batch; drop `--allow-incomplete` once all
   77 units have content.

9. Package: `python3 tools/package.py` writes `dist/part107-course-<date>.zip`,
   refusing to package a course that fails the integrity check. Unzip it somewhere
   else and run it on each backend before handing it to anyone.

## How it fits together

```
ui/              the fixed shell: renders blocks, posts responses, draws the map and readiness
server.py        serves the shell, routes responses, scores answers, calls the model
orchestrator.py  which unit, which gear, which stage comes next; task boundaries and review
mockexam.py      practice-exam attempts, lookup scoring, readiness
llm_client.py    provider adapters (anthropic, claude_code, ollama, mock)
retrieval.py     lexical search over the knowledge base, for free-form questions
items.py         table parsing, vetted items, deterministic lookup scoring
ledger.py        the student ledger: mastery, gears, parking, attempts, exam attempts
prompts/         the tutor: global rules, one prompt per stage, the block and response schemas
curriculum/      objectives, per-unit teaching content, vetting status
reference/       the per-unit ground-truth facts the tutor keys answers to
mock/            the fixed practice exam
knowledge-base/  the source manifest and the two-layer corpus (built locally)
sources/         the authoritative references and their precedence
tools/           fetch_sources, build_kb, enhance_kb, check_companions, probe_retrieval, check_integrity, check_links, package
tests/           the test suite; fixtures live under tests/fixtures
docs/            the illustrated guide: the SVG diagrams shown at the top of this file
```

Design principles behind these choices are in `LLM_COURSEWARE_DESIGN_AND_PRINCIPLES.md`,
and the build plan is in `IMPLEMENTATION_PLAN.md`.
