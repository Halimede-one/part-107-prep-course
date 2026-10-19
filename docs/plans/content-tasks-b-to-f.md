# Content for Tasks B to F: plan

Status: approved and completed October 17, 2026; vetting remains. Route: the lessons are written in a Claude Code session against the knowledge base, one task per batch. The user reviews each batch.

## Context

63 of the 77 tracked units have no Guided lesson and no reference fact: Task B 35, C 4, D 1, E 16, F 7. The tutor declines to teach a unit without a Guided lesson, so a student is blocked at 2.1 (UA.I.B.K1). The 14 authored units are drafts, not vetted. Commit bce7ce6 emptied the body of UA.I.A.K4.md; the text is in commit 51606b7.

The knowledge base holds every source the missing units need: 14 CFR 107 subparts B to D, part 89, part 48, the sections of parts 91 and 99 that part 107 references, and AC 107-2A. No fetch is needed.

## Decisions

- Route: the files are written in the session, one task per batch. The instructor workspace is for review and vetting.
- Order: restore K4, then Task B, Tasks C and D, Task E, Task F.
- Every tracked unit gets its own Guided file, grouping parents included. B.K4, B.K6, B.K14, and B.K21 get a short framing lesson that links their sub-elements. B.K15 summarizes and points at Task E. The tutor cannot teach a unit without a file.
- Lesson pattern as Task A: a header with one `source:` line per source and `version: 1`; then the objective, a plain-language explanation, a worked example, and the common misreading. Every number as the source states it.
- One to three reference facts per unit in `reference/regulations-facts.md`, each with its section and link.
- `STATUS.md` gets one row per unit. The Gear 2 and Reference facts cells say `v1 drafted`; the status is `draft`. Open questions go in the Notes column.
- The practice exam stays at 20 items. Its weighting matches the unit counts.

## Steps

1. Restore K4 from commit 51606b7, keeping the version line. Verify: `python3 tools/check_integrity.py --allow-incomplete` reports no errors.
2. Task B: 35 lessons and their facts. Verify: the integrity check, the unit tests, and a teach of two units with the real model.
3. Tasks C and D: 5 lessons. Same checks.
4. Task E: 16 lessons. Same checks.
5. Task F: 7 lessons. Same checks. Then the strict integrity check must pass.
6. Vetting, by the user: each row marked vetted in `STATUS.md`, in the workspace or by hand. Then a full run with a real model and `python3 tools/package.py`.

## Testing

- `python3 tools/check_integrity.py --allow-incomplete` after each batch; without the flag after Task F.
- `python3 -m unittest discover -s tests` after each batch. The tests copy a fixture curriculum, so new content cannot break them; the run confirms the loaders still parse every file.
- A teach of two units per batch with the real model, through the running course.

## As built

### K4 and Task B, October 17, 2026

- K4: the body came back from commit 51606b7. The `version: 2` line is kept, and the STATUS row says that the v2 grammar edits were lost.
- Task B: 35 Guided lessons (every unit from 2.1 to 2.28 except 2.16, which existed), 67 reference facts, and 35 STATUS rows with `v1 drafted` cells. Facts per unit run from 1 to 6; registration (2.1) has 6 because it carries the most numbers.
- Sources beyond the CFR: AC 107-2A chapters 5 and 7, AIM 3-4, FAA-G-8082-22 chapter 9, the Pilot's Handbook chapter 14, and two faa.gov pages. Each lesson lists its sources in the header.
- Open questions for the vetting step are in the Notes column of STATUS.md for 2.1, 2.8, 2.9, 2.13, 2.14a, 2.18, 2.19, 2.23, 2.26, and 2.27.
- Checks: the integrity check with `--allow-incomplete` reports 0 errors (the 28 units of Tasks C to F still warn); 221 unit tests pass, 1 skipped; a real-model teach of 2.1 and 2.21b returned lesson blocks in 21 and 22 seconds, with the content from the files, and the altitude lesson came with a diagram.
- The smoke test ran on a copy of the course in the session scratchpad on port 8117, so the student ledger and the responses log stayed untouched. The course reads lesson files on each request, so the running course serves new files without a restart.
- Not in this plan: the per-unit question bank in `questions/regulations/` (the workspace's Questions tab) is empty for every unit. It is optional; the tutor writes questions from the lesson and the facts.

### Tasks C to F, October 17, 2026

- Written in one pass after the Task B review: Tasks C and D, 5 lessons and 15 facts; Task E, 16 lessons and 32 facts; Task F, 7 lessons and 18 facts; 28 STATUS rows.
- Sources beyond the CFR: AC 107-2A chapters 5, 6, and 8, and the FAA pages on becoming a remote pilot, Part 107 waivers, operations over people, and remote identification. Each lesson lists its sources.
- Open questions for vetting are in the Notes column of STATUS.md for 3.3, 3.4, 4.1, 5.1, 5.5, 5.13, 5.16, 6.1, 6.3, and 6.5. Two are currency findings: the FAA waivers page (June 2026) differs from AC 107-2A on the decision time and the application system, and 107.160(d) still cites the reserved 107.5.
- Checks: the strict integrity check passes, 77 of 77 units with content and facts, 0 errors, 0 warnings. A real-model teach of 3.3, 4.1, 5.6, 5.16, 6.2, and 6.6 on the scratchpad copy returned lesson blocks in 16 to 28 seconds. The unit tests pass after one assertion in `tests/test_phase2.py` was updated: it asserted that UA.I.F.K7 had no content.
- Remaining: vetting by the user, a full run with a real model, and packaging.
