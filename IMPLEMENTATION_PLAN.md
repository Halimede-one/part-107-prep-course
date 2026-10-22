# Part 107 Course: Implementation Plan (v3.2)

Status: construction complete through Phase 6; content written for all 77 units (Tasks B to F on October 17, 2026), none of it vetted yet. The release to instructors for vetting is planned in `docs/plans/instructor-release.md`. Supersedes v3.1.

This version implements the principles in LLM_COURSEWARE_DESIGN_AND_PRINCIPLES.md against Part 107.

## Changelog, v3.1 to v3.2 (October 16, 2026)

Decisions taken (plan and as-built record: `docs/plans/instructor-interface.md`):
1. Every unit with a Guided lesson offers all three gears. A unit's own `<unit>.gear1.md` or `<unit>.gear3.md` takes priority; without one, the tutor builds that gear from the Guided lesson. (Section 12.4, amended.)
2. The tutor's first Foundational lesson for a unit is saved as that unit's `.gear3.md`, marked as a draft in its header. Later students get it; while it is a draft, the tutor also gets the Guided lesson and the reference facts as the ground truth. An instructor's first save removes the draft mark.
3. Lesson files carry a version number in their header. The version and the draft mark never reach the model.
4. The instructor workspace, on only when the course starts with `--instructor`: edit a lesson file by hand or with an authoring assistant, save with a vetting answer recorded in `STATUS.md`, and store diagrams as image files. The README section "Improving the tutor" is the guide for instructors.

## Changelog, v3 to v3.1 (October 9, 2026)

Decisions taken:
1. Terminal gear: a unit is parked after the second consecutive miss at its deepest gear. The student moves on; parked units return at the next task boundary. Readiness stays closed while any unit is parked. (Section 12.3, rewritten.)
2. Knowledge base: two layers. The source layer is built mechanically from the PDFs with pdftotext; the explanation layer is written by the model from each source chunk, tagged `kind: explanation`, and cites the source chunk. (Section 9, amended.)
3. Gear-3 exemplars: UA.I.B.K16 and UA.I.E.K3 with K3a to K3d. (Section 12.4, amended.)

Built in this version:
4. Spaced review at task boundaries: up to three mastered units from other tasks, least recently attempted first, one re-check question each; a miss demotes the unit to gear 2. (Section 12.3.)
5. The practice exam, the readiness gate, and the `mock_gate` debrief stage. The exam may be taken at any time after intake; readiness, not the attempt, is gated. (Section 9 and new Section 12.7.)
6. Tools: `build_kb.py`, `enhance_kb.py`, `check_integrity.py`, `check_links.py`, `package.py`. (Section 5.)
7. Fixes from the consistency review: the Anthropic web-search tool is now wired behind `supports_web_search`, off by default until verified locally; the block parser accepts prose around the JSON; the model string is current; an empty last table cell no longer drops the cell.

Deferred to local work:
8. Build the knowledge base from the real PDFs, run the enhancement pass, author Tasks B to F, vet all content and the exam against the source text, check links, and test with a real model. The README has the steps.

## What changed from v2

1. **Granularity (principle 10).** Mastery is tracked at all 77 Regulations units (65 codes plus 12 lettered sub-elements), not the 65 top-level codes. objectives.md is already updated.
2. **Knowledge base and free-form Q&A (principle 7).** A new module lets the student ask anything and get an answer sourced from a chunked corpus of the authoritative texts, with citations and links. Retrieval is standard-library lexical search, so the zero-dependency zip holds.
3. **Cite and link everywhere (principle 3).** Every factual statement the model produces, in lessons, feedback, and answers, carries a source citation and link, not just Q&A answers.
4. **Backend-dependent web fallback.** The Claude backend may use web search as a cited fallback for Q&A; the local Gemma backend answers from the knowledge base only and admits gaps.

Everything else from v2 stands: the fixed HTML shell the model populates, the stdlib zip-distributable server, the configurable backend (Claude default), on-the-fly questions with fact-anchoring, the fixed vetted mock, and deterministic scoring of vetted items.

## 1. Goal and success criteria

Teach the Regulations area end-to-end through a fixed interactive web interface that a language model drives: it presents lessons and questions, reacts to answers, remediates weak units, adapts practice, and answers the student's free-form questions from the authoritative sources with citations. Mastery is tracked per unit; readiness is gated behind a fixed, vetted mock.

v1 is done when a simulated student can be taught the area, quizzed with adaptive practice, remediated on the specific units they miss, advanced only at a per-unit mastery threshold, gated behind the fixed mock, and can at any point ask a free-form question and get a cited answer.

## 2. Scope (v1)

Status by component, as of v3.1: everything below is built and tested except where marked. Content is authored for 14 of 77 units (Task A, K16, K3 family) and is unvetted; the knowledge base is built locally from the PDFs.

In scope:
- Curriculum content for Regulations, grounded and cited, at 77-unit granularity.
- A vetted reference of precise regulatory facts (ground-truth answers keyed by unit, with links) and a fixed, vetted mock exam.
- A knowledge-base corpus of the Regulations-relevant authoritative source text, chunked and tagged with citations, for free-form Q&A.
- The fixed HTML shell and its content blocks, including an ask box and a cited-answer block.
- A standard-library Python server with a configurable backend, stdlib lexical retrieval, and a Q&A route.
- The tutor prompt hierarchy, including a Q&A stage and the global cite-and-link rule.
- A progress ledger at 77-unit granularity.
- An integrity-check script.
- A scripted startup and zip packaging.

Out of scope for v1:
- The other four areas (and their source text in the knowledge base).
- Sectional-chart interactivity.
- Real-time streaming.
- Semantic or embedding-based retrieval (would break the zero-dependency promise; see assumption 5).
- Embedding any API key in the distributed archive.

## 3. Architecture and loop

Components:
- **UI shell** (static HTML, CSS, a little JS): renders a fixed set of content blocks, posts answers and questions back, and renders citations as links.
- **Server** (Python standard library only): serves the shell, receives answers and questions as POSTs, writes them to files, runs lexical retrieval for Q&A, and calls the configured model.
- **LLM client**: an adapter layer selected by config. Anthropic (Claude) default, local Ollama alternative, each exposing a capability flag for web search.
- **Retrieval**: a stdlib lexical search over the knowledge-base chunks.
- **Prompt hierarchy** (Markdown): the tutor's behavior at each step, including Q&A and the global citation rule.
- **Content, reference facts, knowledge base, and mock** (Markdown): the vetted source of truth. See Section 9 for how the three content artifacts differ.
- **Progress ledger** (Markdown): per-unit mastery and attempt history.

The teaching loop is turn-based, as in v2. Alongside it, at any point the student can submit a free-form question; the server retrieves the most relevant knowledge-base chunks, the model answers from them with citations and links, and if the answer is not in the corpus the model says so.

## 4. Assumptions (flagged; correct any of these)

1. **Source of truth is authoritative FAA material** (SOURCES.md), with the CFR authoritative for precise facts.
2. **Grounding boundary is facts plus readiness gate** (confirmed). The model teaches and generates practice freely; precise-fact keyed answers anchor to the vetted reference; the mock stays fixed and vetted.
3. **Granularity is maximal.** All 77 Regulations units are tracked. Questions target the most specific applicable unit. Pure-grouping parents (for example K21) are covered by their sub-elements.
4. **Cite and link everywhere.** Lessons, feedback, and Q&A answers attribute each factual statement to a source and link to it. Content and reference facts carry the citation metadata that makes this possible.
5. **Retrieval is stdlib lexical search, not embeddings.** The corpus is small and section-structured, so keyword scoring picks the right chunks. This keeps the zero-dependency zip intact. If you want semantic retrieval, that relaxes the no-dependency rule and is a separate decision.
6. **Knowledge base is scoped to the Regulations-relevant sources for v1**: 14 CFR part 107 subparts A to D, 14 CFR part 89, 14 CFR parts 47 and 48, and the relevant chapters of AC 107-2 and FAA-G-8082-22. Other areas' source text is added when those areas are built.
7. **The three content artifacts are distinct** (Section 9): reference facts are the compact per-unit answer key for anchoring; the knowledge base is the fuller chunked corpus for Q&A; curriculum content is the authored teaching material. All three carry links.
8. **Q&A is in v1 but separable.** It is its own set of phases and can be deferred to right after the loop is proven if you prefer; say so and I will resequence.
9. **Backend web-search capability.** Anthropic supports a cited web-search fallback for Q&A; Ollama and the Claude Code backend (with tools disabled) do not, so on those backends Q&A is knowledge-base-only and the model admits gaps. The key is read from an environment variable and never placed in the archive.
10. **Standard library only, zip-distributable**, turn-based cadence, deterministic scoring of reference and mock items, content drafted section by section. (All from v2.)

## 5. Proposed file layout

New standalone repo, distributed as a zip of the same folder. Additions to v2 are marked.

```
part107-course/
  README.md                       # setup, backends, key handling, prerequisites
  config.json                     # provider, model, endpoint (key from env)
  start.sh                        # launch the server and open the browser
  server.py                       # stdlib server: serve, receive posts, write files, retrieve, call model
  llm_client.py                   # adapters: anthropic (default), ollama; each with a web-search capability flag
  orchestrator.py                 # routing decisions: which unit, which gear, which stage
  mockexam.py                     # practice exam attempts, lookup scoring, readiness
  retrieval.py                    # NEW: stdlib lexical search over the knowledge-base chunks
  ui/
    index.html                    # fixed shell
    styles.css
    app.js                        # renders blocks, posts responses and questions, renders citations, light poll
  prompts/
    orchestrator.md               # global rules: grounding, cite-and-link, precedence, gears, output contract
    teach.md
    quiz.md
    score_diagnose.md
    remediate.md
    qa.md                         # NEW: answer free-form questions from retrieved chunks, cite and link, admit gaps
    mock_gate.md
    block_schema.md               # content-block types the model may emit (incl. ask and cited-answer blocks)
    response_schema.md            # the fixed shape the page posts back (answers and questions)
  curriculum/
    regulations/
      objectives.md               # the 77 tracked units (done)
      <unit>.md                   # grounded, cited teaching content
  reference/
    regulations-facts.md          # per-unit ground-truth answers, with source and link (Markdown table)
  knowledge-base/                 # NEW
    sources.json                  # manifest: which PDFs, how sections are headed, how to link a section
    pdfs/                         # the source PDFs, downloaded locally, not committed
    regulations/
      <source>-<section>.md       # source layer: chunked text from the PDF, kind: source
      <source>-<section>.explained.md  # explanation layer: model-written, kind: explanation, cites its source chunk
      index.md                    # chunk manifest, regenerated by build_kb.py
  mock/
    regulations-mock.md           # fixed, vetted, ACS-weighted exam (Markdown table)
  progress/
    student-ledger.template.md    # per-unit mastery and attempt history (77 units)
  sources/
    SOURCES.md                    # authoritative references and precedence (done)
  tools/
    build_kb.py                   # pdftotext over the manifest PDFs into source chunks (needs poppler locally)
    enhance_kb.py                 # the explanation layer, one companion chunk per source chunk, via the configured model
    check_integrity.py            # coverage (77 units), content headers, facts, exam items, chunk metadata, prompts
    check_links.py                # requests every cited link once and reports failures (needs network)
    package.py                    # the distributable zip, gated on the integrity check
  curriculum/regulations/STATUS.md  # per-unit vetting status and review notes, kept out of the content files
```

## 6. The HTML shell, content blocks, and chrome

Built once, never regenerated by the model. Two kinds of elements:

Model-emitted content blocks (the teaching flow): lesson, question (quiz), feedback, and cited-answer. Every block that carries factual content also carries a citations field, which the shell renders as links. The model emits blocks; the page renders them and posts answers and questions back in the fixed schema.

Shell-owned elements (not drawn by the model; driven by state or a fixed flow): an intake step at session start that asks the student's level and sets the default gear; a persistent ask box for free-form questions; and the course map, a persistent, unobtrusive progress view (Section 12) that reads ledger state through a `/state` endpoint and redraws each turn. Keeping these in the shell rather than in model output is what keeps them reliable and honest.

## 7. The prompt hierarchy

The orchestrator is split in two, which is what keeps the adaptive behaviour testable. `orchestrator.py` decides which unit, gear, and stage come next, purely from the ledger, and `orchestrator.md` is the system prompt prepended to every stage that binds how the model may answer.

- **Orchestrator** (top): reads the ledger, picks the current unit and level, dispatches to a stage prompt, and enforces the global rules: cite and link every factual statement, anchor precise facts to the reference, honor source precedence (CFR wins), the per-unit mastery threshold, and the fixed mock gate.
- **Stage prompts:** teach, quiz, score-and-diagnose, remediate, qa, and mock-gate. Each takes the relevant curriculum, reference, knowledge-base, or mock slice and emits the next block, or for scoring reads the response and updates the ledger.
- **qa.md:** answer only from the retrieved chunks, cite and link each, paraphrase rather than reproduce, and if the answer is not in the chunks say so. On a web-search-capable backend, web results are an allowed fallback that must also be cited and that never overrides an authoritative source.
- **Templates:** the block schema (including ask and cited-answer blocks) and the response schema.

## 8. LLM configuration

`llm_client.py` selects an adapter from `config.json` and exposes a `supports_web_search` capability:
- **Anthropic (distribution default):** an HTTPS POST to the Messages API; key from an environment variable; `supports_web_search` true, using the API web-search tool for the Q&A fallback.
- **Claude Code (build and iteration):** shells out to headless `claude -p` with `--output-format json`, which draws on the signed-in Claude plan rather than API billing. The tutor system prompt replaces the Claude Code default outright, and tools are disabled, since this spawns an agent on the student's machine and a tutor has no business touching their files. `supports_web_search` false by default; enabling the WebSearch tool would change that.
- **Ollama (offline):** an HTTP POST to a local endpoint; no key, offline; `supports_web_search` false, so Q&A stays knowledge-base-only.
- **Mock (testing):** canned blocks, no model, used by the test suite.

The three real backends have distinct roles. Claude Code is for our own build and prompt iteration, where it removes the marginal token cost of Phase 3. Anthropic is the distribution default, since each student supplies their own key. Ollama is the free offline student path.

Two constraints on the Claude Code backend, both flagged rather than designed around:
- It is not a distribution path. Plan allocation is per-user and cannot be pooled, and Anthropic points shared production automation at an API key. Students cannot run through one subscription.
- The billing treatment is in flux. Anthropic paused a planned change that would have moved `claude -p` onto a separate credit pool, and has said it will announce before anything takes effect. This is survivable precisely because it is one adapter behind a swappable interface.

Both are HTTP or subprocess calls from the standard library. The README documents each backend, key handling, and prerequisites.

## 9. Content, reference facts, knowledge base, and mock

Three content artifacts, distinct jobs:

- **Curriculum content** (`curriculum/regulations/<unit>.md`): the authored teaching material per unit, grounded and cited. Per unit: the objective and its code, a plain-language explanation, a worked example or scenario, common misconceptions, and citations with links. Drafted section by section for review. Pure-grouping parents get a short framing that links their sub-elements.
- **Reference facts** (`reference/regulations-facts.md`): the compact, per-unit answer key for precise facts, used to anchor the model's keyed answers and enforce the fact guardrail. Markdown table with columns for unit, the fact, the ground-truth answer, and a source link.
- **Knowledge base** (`knowledge-base/regulations/`): the fuller chunked corpus of the Regulations-relevant source text (assumption 6), each chunk tagged with its source, section, and canonical link, plus an index the retrieval reads. This is what free-form Q&A retrieves from and what lessons can cite beyond the distilled facts. These are US government works, so shipping the text is fine.
- **Mock** (`mock/regulations-mock.md`): a fixed, vetted, ACS-weighted Regulations exam for the readiness gate. The finer 77-unit granularity drives the formative loop; the mock is summative.

Coverage rule: every tracked unit has curriculum content and at least one reference-fact entry (grouping parents covered by their sub-elements); the knowledge base covers the Regulations-relevant sources; the mock reflects the area's weighting.

## 10. Testing approach

1. **Coverage.** Every one of the 77 units has content and a reference-fact entry; the knowledge base covers the scoped sources; the mock is ACS-weighted.
2. **Reference and mock integrity.** Each reference fact has a ground-truth answer and a working link; each mock item has one keyed answer, distinct distractors, a rationale, a link, and a unit mapping.
3. **Knowledge-base integrity.** Every chunk has source, section, and a canonical link, and appears in the index.
4. **Server, scoring, and retrieval unit tests.** Deterministic lookup scoring is correct; a POST writes the right file; config selects the right adapter and capability; retrieval returns the expected chunk for representative questions; a missing key or down endpoint fails clearly.
5. **Framework behavior (golden transcripts).** Strong, weak, and misses-specific-units students verify correct routing, per-unit mastery gating, remediation targeting the exact units, on-the-fly questions that anchor facts, cited factual statements throughout, and a mock gate that fires only above the margin.
6. **Q&A behavior.** An in-corpus question is answered with citations and links; an out-of-corpus question is declined rather than guessed. On the Claude backend, a question needing a web fallback is answered with a citation and the authoritative source still wins on conflict. On the Ollama backend, Q&A stays knowledge-base-only and admits gaps.
7. **Grounding.** On a precise-fact question the keyed answer matches the reference; source precedence is honored on conflict.
8. **End-to-end acceptance.** A full run reaches readiness via the fixed mock, with Q&A available throughout.
9. **Packaging.** Unzip into a clean folder, set the env key, run start.sh, confirm the loop and Q&A work on the default backend; switch to Ollama and confirm the loop and knowledge-base-only Q&A run offline.

After the slice is built I will supply the concrete golden-transcript scripts, the Q&A test set, and the coverage checklist.

## 11. Phased plan (with per-phase done-tests)

**Phase 0: decisions and sources. DONE.** SOURCES.md and objectives.md exist; objectives.md marks all 77 units.

**Phase 1: UI shell.** Build `ui/`, the block set (lesson, question, feedback, progress, ask, cited-answer), and the block and response schemas, static and model-free.
Done-test: the shell renders each block type from a hand-written sample, renders citation links, and posts well-formed answer and question files.

**Phase 2: server, LLM client, and retrieval.** Build server.py, llm_client.py with all adapters and the capability flag, retrieval.py, config.json, start.sh, and the Q&A route, using a mock adapter and a stub knowledge base for testing.
Done-test: the server serves the shell, receives an answer POST and a question POST, writes both, retrieval returns the stub chunk, and the mock adapter returns a block; config switches adapter and capability; a missing key, a missing `claude` binary, or an unreachable endpoint is handled gracefully.

**Phase 3: prompt hierarchy. DONE.** orchestrator.md holds the global rules and the output contract; teach, quiz, score_diagnose, remediate, and qa are the stage prompts; orchestrator.py makes the routing decisions.
Done-test met: a dry run on the three-unit stub routes teach, quiz, score, remediate, and advance correctly; downshifts a missed unit one gear at a time and leaves other units alone; flags a unit after repeated misses at the deepest gear; keeps the answer key off the client; refuses to teach a unit with no vetted content; and answers an in-corpus question with a link while declining an out-of-corpus one.

Two things this phase deliberately left out. `mock_gate.md` waits for Phase 5, since writing a prompt against an exam format that does not exist yet invites getting it wrong. Spaced review of mastered units (design principle 8) is not implemented; it needs its own decision about scheduling and demotion, and is proposed for a phase after the content lands.

**Phase 4a: knowledge base. TOOLS DONE, RUN LOCALLY.** `build_kb.py` chunks the manifest PDFs into the source layer; `enhance_kb.py` adds the explanation layer. The chunker, the companion writer, and retrieval over both layers are tested, including an end-to-end run on a generated PDF. The live build needs the PDFs and runs on the local machine.
Done-test met for the tools; the knowledge-base integrity check runs against the real corpus locally.

**Phase 4b: content and reference facts. TASK A AND EXEMPLARS DONE, REST LOCAL.** Gear-2 content for the 8 Task A units, gear-2 and gear-3 for UA.I.B.K16 and UA.I.E.K3 with K3a to K3d, and 29 reference facts for those 14 units. All draft, tracked in STATUS.md. Tasks B to F are authored locally against the built knowledge base, one task per batch.
Done-test for the authored units: the integrity check passes with `--allow-incomplete`. Accuracy is a human check against the source text, not yet done.

**Phase 5: mock and gate. DONE, EXAM UNVETTED.** A 20-item practice exam weighted by task, lookup scoring, a whole-attempt timer, attempts recorded in the ledger, readiness computed from the ledger, and the `mock_gate` debrief stage.
Done-test met: the weighting is reported by the integrity check; the gate requires two attempts at 85 percent or above plus every unit mastered and none parked; the key never reaches the browser; an early submit scores unanswered items as wrong. The items themselves await vetting.

**Phase 6: integrity script and packaging. DONE.** `check_integrity.py` with strict and `--allow-incomplete` modes; `check_links.py`; `package.py` gated on the integrity check, excluding student state, PDFs, tests, and caches, and keeping `start.sh` executable.
Done-test met: the script flags a broken item, a missing unit, a content file without a link, an orphan explanation chunk, and a missing prompt; the zip builds with 52 files. The unzip-and-run check on each backend is a local step.

**Later (not v1):** the remaining four areas and their source text, sectional-chart interactivity, real-time streaming, optional semantic retrieval, a web-search path for the local backend, and ZeroClaw integration.

## 12. Adaptive gears and the course map

This section specifies the multiple-speed adaptive behavior and the learner-facing map. It extends the coverage rule in Section 9, the test list in Section 10, and the phases in Section 11.

### 12.1 The three gears

Each unit can be taught at one of three gears, ordered from fast and minimal to slow and finely scaffolded:

- Gear 1, Fast-track (default). Assessment-forward: a one or two line statement of the point, then straight to a check. Ace the checks to the mastery bar and the unit is done. Quick for a student refreshing.
- Gear 2, Guided. The full authored lesson: plain-language explanation, a worked example or scenario, common misconceptions, an interactive check, then the quiz.
- Gear 3, Foundational. The unit broken into its finest pieces, each taught with a different representation than Gear 2 used (a concrete analogy, a visual or mnemonic, step-by-step reasoning), with frequent low-stakes checks before the quiz. Slowest and most scaffolded.

The invariant: gears change the route, not the bar. The per-unit mastery threshold and the fixed mock are identical across gears. A faster gear is less time for someone who already knows the material, never an easier standard.

### 12.2 Per-unit gear, default, and intake

Gear is a per-unit state, not one global setting. The ledger gains, per unit, a current gear, and per session a default gear. At session start an intake step asks the student their level and sets the default gear, which defaults to Fast-track. Each new unit starts at the session default. A student refreshing therefore fast-tracks most units and drops only the few they are rusty on.

### 12.3 Transitions, parking, task boundaries, and spaced review

- Fail a unit at gear N: set that unit to gear N+1, re-present it at the deeper gear, and re-quiz with fresh items. Other units are unaffected.
- No upshifting mid-unit and no oscillation. New units start at the default gear.
- Terminal gear (the deepest available for that unit): the first miss re-teaches at the same gear from a different angle; the second consecutive miss parks the unit. The feedback says so plainly, the unit is flagged needs-attention, and the course moves on. The ask box stays open throughout.
- Task boundary: when the course is about to move forward into a later task (or past the last one), it first re-checks up to three mastered units from other tasks, least recently attempted first, with one question each. A miss demotes the unit to gear 2, and it comes back as the current unit. Then every parked unit is unparked and returns at its deepest gear with a fresh-angle framing. Boundaries fire only on forward moves, so a demotion that sends the student back to an earlier task does not trigger another round.
- End of the area: with parked units left, the done screen lists them and Continue retries them; with none, it points to the practice exam.
- Readiness stays closed while any unit is parked or unmastered.
- Optional refinement, not built: if a student downshifts on many early units, offer to reset the default gear deeper.

### 12.4 Content per gear, and the v1 cost

- Gear 2 is the authored curriculum content already planned (Section 9).
- Gear 1 is a compressed, assessment-first view the model generates from the Gear 2 source. No extra authoring. A unit may have its own `<unit>.gear1.md`, which then takes priority (v3.2).
- Gear 3 is a different representation broken into the finest pieces (often the sub-elements). Authored scaffolding is the real cost, so it is written where the material warrants it rather than everywhere. Since v3.2, a unit without a `<unit>.gear3.md` gets Gear 3 built by the model from the Gear 2 source, and the first such lesson is saved as a draft `.gear3.md` for instructors to review and improve.

For v1: build the full three-gear mechanism, ship Gears 1 and 2 for all 77 units, and author Gear 3 for a small exemplar set of hard units to prove the mechanism, expanding Gear-3 coverage later from real failure data. Exemplar set, decided: UA.I.B.K16 prior authorization in controlled airspace, and UA.I.E.K3 categories of operations over people (gear 3 on the parent, which decomposes into K3a to K3d). Gear-3 content lives alongside the unit as `curriculum/regulations/<unit>.gear3.md`. Until v3.1 a unit offered gear 3 exactly when that file existed; since v3.2 every unit with a Guided lesson offers it.

### 12.5 The course map

A persistent, unobtrusive element of the fixed shell (Section 6), not drawn by the model. It reads state through a server `/state` endpoint and redraws each turn, so it never drifts from reality.

Representation: a pathway model, not a grid. Each unit offers parallel routes of increasing depth, one per available gear, so the picture itself shows how much depth a unit has. The student's traversed route is highlighted; a unit they revisited at a deeper gear shows more than one highlighted route. This is a natural fit, because the gears are literally alternate paths of increasing depth through the same unit.

It must convey:
- Available depth per unit: how many gears a unit offers (some offer up to three, some only Fast-track and Guided).
- The path the student took: the route through each unit, and their route across the course.
- Revisits: where a unit was downshifted, more than one route through it is highlighted.
- State and flags: mastery (unseen, learning, mastered), the current unit, and needs-attention.

Data model: to feed this, the ledger records per unit not only the current gear but the sequence of gears traversed (the path), and `/state` exposes, per unit, the available gears, the gears traversed, the current gear, mastery, and flags. Getting this data right now is what lets the visual design slot in later without touching the data model.

The v1 shell shipped a plain placeholder grid that read the same `/state`. The design pass replaced it on October 10, 2026 with the course tree (Section 13, item 4).

### 12.7 The practice exam and readiness

The exam is a fixed, human-vetted table in `mock/regulations-mock.md`: 20 items weighted by task, one keyed answer each. An attempt presents the same items in a shuffled order under a single countdown (two minutes per item), posts each answer silently, and scores by lookup; unanswered items score as wrong. Attempts are recorded in the ledger. The model writes only the debrief, from the `mock_gate` stage, and is told the readiness status rather than asked for it.

Readiness is computed from the ledger in one place (`mockexam.readiness`): every tracked unit mastered, none parked, and two attempts at 85 percent or above. The shell shows the status and the reasons under the course map. The exam itself may be taken at any time after intake; an early attempt is informative and harmless, and local testing needs it.

### 12.6 Amendments to earlier sections

- Ledger (Section 9 and principle 16): add per-unit current gear, the sequence of gears traversed per unit (the path the map draws), and a session default gear.
- Coverage rule (Section 9): all 77 units have Gear 1 and Gear 2; the exemplar set has Gear 3. Since v3.2, every unit with a Guided lesson has all three gears; hand-written Gear 1 and Gear 3 files are added as students show the need.
- Tests (Section 10): fast-track speeds through when checks are aced; a miss downshifts only the specific unit; Gear 3 presents a distinct decomposition, not merely a slower one; the terminal policy fires after two cycles and flags needs-attention; the mastery bar and the mock are identical across gears; the course map renders per-unit mastery and gear from `/state` and updates each turn.
- Phases (Section 11): the intake step, the course map, and consuming `/state` land in Phase 1 (UI); the `/state` endpoint in Phase 2; gear-aware teach and remediate prompts and the transition and terminal logic in the orchestrator in Phase 3; the Gear-3 exemplar content in Phase 4b.

## 13. Open items

Closed in v3.1: knowledge-base scope (PDFs via pdftotext plus the explanation layer), Q&A sequencing (built in Phase 2), the gear-3 exemplar set (K16 and K3 family), the terminal-gear policy (parking).

Still open, all local:
1. Vetting. Every authored unit, every reference fact, and every exam item against the source text, recorded in `curriculum/regulations/STATUS.md`. Items flagged there carry specific questions.
2. Verify at first run: the Anthropic model string, the web-search tool format (then set `supports_web_search` true), and the PDF links in `knowledge-base/sources.json`.
3. Author Tasks B to F against the built knowledge base, one task per batch, and extend the exam if the task weighting drifts: done on October 17, 2026. The record is `docs/plans/content-tasks-b-to-f.md`.
4. Course-map visual design pass (Section 12.5): done on October 10, 2026 as the course tree. The design record (mockup, encoding, review) is `docs/mockups/course-tree/`. It added `title` and `attempts` per unit to `/state` and a `goto` request that teaches a unit the student picks from the tree at the gear they pick.
5. Tunables to revisit with real students: TERMINAL_CYCLES, REVIEW_PER_BOUNDARY, REVIEW_DEMOTION_GEAR, the pass mark, and the minutes per exam item.
