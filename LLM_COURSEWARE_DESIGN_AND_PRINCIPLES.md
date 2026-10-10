# LLM-Assisted Courseware: Design and Principles

Status: v0.4, October 9, 2026. Living document. Abstracted from building the FAA Part 107 course (the reference implementation) and revised as that build and later courses teach us more.

## Purpose

This document holds the portable design principles for building a course that a language model teaches adaptively. It is meant to be handed to any new LLM-assisted course, whatever the subject. It is not tied to Part 107; Part 107 is only the first instance we used to work the principles out.

Division of labor: this document holds what is portable, the principles below. Each course keeps its own implementation plan, authoritative sources, content, and question bank. When something a course teaches us is general, it comes back here. When it is subject-specific, it stays in that course.

## Core thesis

An LLM-assisted course pairs a vetted body of authoritative knowledge with a language model that teaches it. The model's job is pedagogy: explain, question, diagnose, remediate, and adapt. It is not the authority on the facts. Almost everything below follows from keeping those two roles separate: the sources hold the truth, the model runs the teaching.

## Principles

### Truth and grounding

**1. The model tutors; the sources hold the truth.**
For any subject with precise, consequential facts, content is grounded in authoritative source material and the model teaches over it. A model left to generate facts from its own recall will occasionally state a wrong one with full confidence, which is worse than a dull but correct statement, because the student cannot tell the difference. (Part 107: the model never states a regulatory limit from memory; it draws from the CFR and FAA guidance.)

This extends to how the corpus is built. The source layer of a knowledge base is ingested mechanically from the documents, never transcribed by a model, so it stays ground truth and can be rebuilt when the source changes. A model-written layer of explanations and illustrations is valuable, and it is kept as a second layer: derived from one source chunk at a time, forbidden to add facts, tagged as derived, and citing the chunk it came from. Retrieval serves both; the tutor is told which is which, and the source layer wins on conflict.

**2. Establish a source hierarchy with explicit precedence.**
Name the authoritative sources and rank them, so that when two disagree the resolution is a rule rather than a guess. Primary law or standards outrank explanatory guidance. When sources conflict, the higher one wins and the discrepancy is flagged for a human, not smoothed over by the model. (Part 107: the CFR is ground truth for any precise fact; the Advisory Circular and study guide explain but do not override it.)

**3. Cite and link every factual claim, everywhere.**
Citation is a course-wide policy, not a feature of the question-answering corner. Lessons, feedback, and answers all attribute each factual statement to a source and link to it. This lets the student verify, keeps the model honest, and makes errors traceable.

**4. The competency blueprint is a map, not an answer source.**
A domain's skill or exam framework tells you what must be known and how it is organized. It rarely states the answers. Keep the two separate: the framework drives structure and coverage; the primary sources supply the facts. (Part 107: the ACS lists "altitude limitations" as a testable item but never states the 400-foot rule; the rule lives in part 107.)

**5. Bound the model's freedom: presentation is free, facts and the readiness assessment are fixed.**
Give the model wide latitude in how it teaches, including examples, framing, scenarios, adaptive difficulty, and questions generated on the fly, and bind it only where correctness decides outcomes: precise facts anchor to the vetted sources, and the final readiness assessment stays fixed and vetted. Dynamic where it teaches, grounded where it counts.

**6. Be deterministic where correctness must be reliable.**
Scoring of vetted items should be a lookup against a known key, not a model judgment, so that it stays correct no matter which model drives and can be unit-tested. Model-scored practice is acceptable where adaptive value matters more than scoring precision, but the signals that gate progress and readiness should rest on deterministic checks.

**7. Ground free-form questions in the corpus; allow cited web fallback; admit the gaps.**
Let students ask anything, but answer from a retrieved slice of the authoritative corpus, cite and link it, and paraphrase rather than reproduce. If the answer is not in the material, the model says so instead of inventing one. Web search is a fine fallback when it too cites, and when authoritative sources still take precedence over it.

### Pedagogy

**8. Mastery learning is the engine.**
Teach a unit, assess it, diagnose what was missed, remediate exactly that, re-assess with fresh items, and advance only when a mastery threshold is met. Revisit earlier units on a spaced schedule. This is mastery learning in the tradition of Bloom: the student does not move on until they have the piece in hand.

Two practical rules keep this from trapping a learner. Natural boundaries in the material (the end of a task or chapter) are the moment for spaced review: a few mastered units from earlier, least recently checked first, one question each, with a miss sending the unit back for re-teaching. And a unit the learner keeps missing at the deepest available depth is set aside rather than cycled forever: the course moves on, brings the unit back at the next boundary with a fresh angle, and keeps the final readiness decision closed until it is mastered. Progress is never blocked by one unit; readiness is. (Part 107: review of up to three units at each task boundary; parking after the second miss at the deepest gear.)

**9. Adapt by shifting instructional gears, not by lowering the bar.**
Serve multiple speeds through the same material with an ordered set of instructional gears, from fast and minimal to slow and finely scaffolded. Default to the fastest gear, so a learner who already knows the material can refresh quickly by passing the checks. When a learner fails a unit, downshift that unit to a deeper gear that re-presents it with a different representation and finer steps, not merely more slowly. The mastery bar and the readiness assessment are identical across gears, so a faster gear means less time for someone who already knows it, never an easier standard. The number of gears scales with the material's depth. This rests on the expertise-reversal effect, where scaffolding that helps a novice wastes an expert's time, and it mirrors tiered intervention, from universal to targeted to intensive. (Part 107: Fast-track, Guided, and Foundational gears; a rusty student fast-tracks most units and drops to a deeper gear only on the few they miss.)

**10. Make the learner's progress and current depth visible to them.**
Give the learner an ambient, honest view of their own state: which units are mastered, which are in progress, where they are now, at what depth they are working each unit, how much depth is available, and the path they took to get there, including any units they revisited at a deeper gear. Seeing which units required a deeper gear is useful metacognition, not a mark of failure, and a visible sense of progress supports motivation. Keep it unobtrusive and draw it from the same state the system uses, so it never drifts from reality. (Part 107: a course map in a corner of the interface, showing per-unit mastery and gear, drawn from the ledger.)

**11. Use the domain's competency framework as the atomic unit.**
Track mastery against the smallest named competencies the domain provides, so that a miss maps to a specific thing to re-teach and readiness is a measurable function of unit mastery. If the domain has no such framework, define one before building content. (Part 107: the ACS codes.)

**12. Maximize tracking granularity; it is the competency signal.**
Track at the finest meaningful grain the framework offers, because granularity is what tells the tutor precisely which piece to iterate on and re-test. Finer tracking costs more authoring and checking, and that cost is usually worth paying, because coarse tracking hides exactly the information adaptivity needs. (Part 107: track the lettered sub-elements, so a miss points at "cloud clearance" rather than at the "operating limitations" umbrella.)

**13. Gate readiness behind a fixed, vetted assessment above a margin.**
Do not tell a student they are ready until they pass a fixed, human-vetted assessment at a level comfortably above the real-world pass line. The ready signal has to map to the real outcome, which it cannot do if it rests on questions the model both invented and graded leniently. Gate the readiness decision, not the attempt: let the learner sit the assessment whenever they like, since an early attempt is informative and harmless, and compute readiness in one place from recorded state. The model may explain a result; it never decides readiness. (Part 107: a fixed mock, 85 percent across two attempts, against a real 70 percent pass line; readiness also requires every unit mastered and none set aside.)

### Architecture

**14. Keep the interface a fixed shell the model populates, not markup it generates.**
Build the interface once as a stable shell that renders a small set of content blocks, and have the model emit those blocks rather than write the interface each turn. This keeps the interface reliable, makes weaker models viable, and confines the model's variation to content. The distinction extends to chrome: persistent elements such as a progress view are part of the shell and are driven by state, not drawn by the model. (Part 107: lesson, question, feedback, and progress blocks; the course map is shell chrome fed from the ledger.)

**15. Structure the tutor as a prompt hierarchy, not one monolithic prompt.**
Express the tutor as a small tree: an orchestrator that reads state and dispatches, stage prompts with bounded jobs (teach, quiz, score and diagnose, remediate, gate), and shared templates. Each part does one thing, which makes behavior legible and testable.

**16. Persist student state in a simple, human-readable, inspectable form.**
Store progress in a plain, portable record that the model reads and a human can open and audit. State is the spine of adaptivity, and it should never be a black box. (Part 107: a Markdown ledger of per-unit mastery, gear, and attempt history.)

**17. Design model-agnostic; prove with the strongest model, then localize.**
Keep the content, prompts, formats, and interface independent of any one model so the driver can be swapped. Prove the course with the most capable model available, then move to a local or cheaper one behind the same files once the loop and content are validated. This buys portability and avoids betting early reliability on a weak model.

**18. Prefer the simplest architecture that delivers the pedagogy.**
Choose the least machinery that meets the teaching goal. Where the course is distributed, minimize dependencies so it runs from a folder. Never embed secrets such as API keys in a distributed artifact; take them from the environment. Respect content licensing: government works are free to ship, most other content is not.

### Quality and process

**19. Make courseware testable despite model nondeterminism.**
The teaching model is nondeterministic, but the course around it is testable. Define success criteria and verify: coverage (every unit has content and items), integrity (items are well-formed, keyed, and sourced), deterministic-scoring unit tests, golden-transcript or rubric evals for tutor behavior, grounding tests that a fact answer matches the source and an out-of-scope question is declined, an end-to-end run that reaches readiness, and a packaging test for how the course is distributed.

**20. Human-vet the authoritative content and the readiness assessment.**
The source-of-truth content and the readiness assessment are safety-relevant and are reviewed by a human before use. Draft content for review rather than generating and shipping it unseen, and flag assumptions as you go. The model's freedom is in teaching, not in deciding unreviewed what is true or what counts as ready.

Keep vetting status and review notes in a separate status file, never inside the content files. Anything in a content file reaches the model verbatim, and a note meant for a reviewer becomes something the tutor might say to a student. Track status per unit, and run a structural integrity check (coverage, citations, well-formed items) as a gate before packaging; it cannot verify truth, but it catches everything else.

**21. Treat these principles as living; revise them from evidence.**
This document is revised from what the reference course and later courses actually reveal. When a principle proves wrong or incomplete in practice, change it here and note why, so every course inherits the lesson.

## Anti-patterns

- Letting the model be the source of truth on precise facts.
- Regenerating the user interface from scratch each turn instead of populating a fixed shell.
- Declaring a student ready based on questions the model invented and graded itself.
- Tracking mastery so coarsely that a miss does not tell you what to re-teach.
- A deeper gear that is merely slower, rather than a different representation with finer steps.
- A fast track that lowers the standard instead of saving time at the same standard.
- A progress view generated by the model rather than drawn from the actual state, which can drift from reality.
- Uncited factual claims in lessons or feedback.
- A knowledge-base corpus transcribed by a model instead of ingested from the source.
- Review notes or status markers written inside content the model reads.
- Cycling a stuck learner on one unit indefinitely instead of parking it and keeping readiness closed.
- A configuration flag that claims a capability the code does not implement.
- Embedding an API key or other secret in a distributed build.
- Adding dependencies or services the pedagogy does not require.
- Resolving a source conflict by model judgment instead of the precedence rule.

## Reference implementation

The FAA Part 107 remote pilot course is the first instance built against these principles. It grounds content in the CFR and FAA guidance, uses the ACS codes as the competency framework tracked at full sub-element granularity, and teaches through a fixed block-based interface driven by a prompt hierarchy. It adapts by shifting a student between Fast-track, Guided, and Foundational gears per unit, exposes that state through a course map drawn from the ledger, scores vetted items deterministically, gates readiness behind a fixed mock, and ships as a zero-dependency folder with a configurable model backend. It is where these principles are being tested and where the first revisions to this document will come from.

## Glossary

- Grounding: tying the model's factual output to vetted source material rather than its own recall.
- Source hierarchy: the ranked list of authoritative sources and the precedence rule for conflicts.
- Competency framework (skill map): the domain's own list of what must be known, used as the unit of tracking.
- Mastery threshold: the bar a student must clear on a unit before advancing.
- Readiness gate: the fixed, vetted assessment that must be passed, above a margin, before a student is told they are ready.
- Instructional gear: one presentation of a unit at a fixed depth and pace, from fast and minimal to slow and finely scaffolded.
- Default gear: the gear new units start at, set at intake.
- Downshift: moving a unit to a deeper gear after the learner fails it.
- Content block: one of the fixed, model-populated pieces the interface renders.
- Course map: the learner-facing, data-driven view of per-unit mastery and gear.
- Prompt hierarchy: the tree of orchestrator, stage, and template prompts that defines the tutor's behavior.
- Ledger: the simple, human-readable record of a student's per-unit mastery, gear, and history.

## Revision log

| Version | Date | Change | Source of the learning |
|---|---|---|---|
| v0.1 | 2026-07-16 | Initial principles, abstracted from the Part 107 design discussion. | Part 107 planning |
| v0.2 | 2026-07-16 | Added the adaptive-gears principle and the learner-facing-progress principle, with supporting glossary terms and anti-patterns. | Part 107 adaptive-learning discussion |
| v0.3 | 2026-07-16 | Refined the learner-facing-progress principle to include available depth and the path taken, including revisits. | Part 107 progress-indicator review |
| v0.4 | 2026-10-09 | Principle 1: the corpus has a mechanically ingested source layer and a derived, tagged explanation layer. Principle 8: spaced review at natural boundaries, and parking a stuck unit while keeping readiness closed. Principle 13: gate the readiness decision, not the attempt. Principle 20: status and review notes live outside content files; a structural integrity check gates packaging. Four anti-patterns added, including a flag claiming an unimplemented capability, found in a consistency review of the build. | Part 107 Phases 4 to 6 |

Add a row when a principle changes, noting what the course revealed and what changed here.
