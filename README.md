# FAA Part 107 course

An adaptive, LLM-tutored course for the FAA Part 107 remote pilot knowledge test.
Content is grounded in the CFR and FAA guidance; the model teaches over it rather
than being the authority on the rules.

Runs from this folder with no packages to install. Python 3.8 or newer is the only
prerequisite, plus a model backend (below).

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
tools/           fetch_sources, build_kb, enhance_kb, probe_retrieval, check_integrity, check_links, package
tests/           the test suite; fixtures live under tests/fixtures
```

Design principles behind these choices are in `LLM_COURSEWARE_DESIGN_AND_PRINCIPLES.md`,
and the build plan is in `IMPLEMENTATION_PLAN.md`.
