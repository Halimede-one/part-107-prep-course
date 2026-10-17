# Unit numbers: implementation plan

Status: approved and implemented, October 17, 2026. Decisions: chapter.lesson numbers such as 2.16, a display label only (the ACS code stays the key), and the ACS code shown next to the number everywhere.

## Context

Each course unit has only one name: its ACS code, for example `UA.I.A.K5`. ACS means Airman Certification Standards. People cannot say these codes easily in speech or in chat. The code is also the only key for a unit: in lesson file names, the student ledger, STATUS.md, the facts table, the mock exam table, and the API.

The decisions:

- **Format:** `chapter.lesson`, for example `2.16`.
- **Scope:** a display label only. The ACS code stays the internal key. No file renames and no ledger migration.
- **ACS code:** shown next to the number everywhere, for example `2.16 (UA.I.B.K16)`.

The result: students, instructors and developers can say "lesson 2.16". The tutor model and the UI show the same label. All existing files and saved progress continue to work.

## The numbering rule

- The chapter is the ACS task. Area I Task A is chapter 1, through Task F as chapter 6.
- The lesson is the K number, with its sub-element letter if it has one.
- The later ACS areas continue the chapter count, so numbers stay unique if those areas come into the course.

| Area | Tasks | Chapters |
|---|---|---|
| I Regulations | A to F | 1 to 6 |
| II Airspace | A, B | 7, 8 |
| III Weather | A, B | 9, 10 |
| IV Loading and Performance | A | 11 |
| V Operations | A to F | 12 to 17 |

Examples: `UA.I.A.K5` is 1.5. `UA.I.B.K16` is 2.16. `UA.I.B.K21a` is 2.21a. `UA.I.E.K3c` is 5.3c. `UA.I.F.K7` is 6.7.

Label formats:

- A unit: `2.16 (UA.I.B.K16)`. With a title: `2.16 (UA.I.B.K16) · Prior authorization required...`
- A task row and the map header: `2 (Task B) · Operating Rules`.
- Tree node for a sub-element: `2.21a (B.K21a)`. This keeps the short code the tree already uses for indented rows.

## Changes

1. **The rule, in one place.** Add to [orchestrator.py](../../orchestrator.py), next to `task_of` (line 102):

   ```python
   # The short unit number is chapter.lesson. Area I's tasks A to F are chapters
   # 1 to 6, and the later ACS areas continue the count. The lesson is the K number.
   FIRST_CHAPTER = {"I": 1, "II": 7, "III": 9, "IV": 11, "V": 12}


   def number_of(unit):
       """The short number of a unit code: UA.I.B.K16 -> 2.16, UA.I.B.K21a -> 2.21a."""
       _, area, task, element = unit.split(".")
       return "%d.%s" % (FIRST_CHAPTER[area] + ord(task) - ord("A"), element[1:])


   def label_of(unit):
       """A unit as people see it: 2.16 (UA.I.B.K16)."""
       return "%s (%s)" % (number_of(unit), unit)
   ```

2. **Send the number to the UI.** In `Ledger.state()` ([ledger.py:250](../../ledger.py#L250)), add `"number": number_of(unit)` to each unit entry. Import `number_of` from orchestrator. ledger.py already imports `lesson_files` from there.

3. **Tutor model context.** Use `label_of(unit)` in:
   - `_header()` ([orchestrator.py:262](../../orchestrator.py#L262)): `UNIT: 2.16 (UA.I.B.K16)`. The ask-box context uses the same line.
   - `author_context()` ([orchestrator.py:360](../../orchestrator.py#L360)): the same `UNIT:` line.
   - `mock_gate_context()` ([orchestrator.py:399](../../orchestrator.py#L399)): each missed unit line.

4. **Server text the student sees.** `done_block` ([server.py:597](../../server.py#L597)) lists the set-aside units with `label_of`.

5. **Prompts.** In [prompts/qa.md:12](../../prompts/qa.md#L12) and [prompts/author.md:33](../../prompts/author.md#L33), extend the line about `objectives.md` to say it also explains the unit numbers such as 2.16. Then the ask box and the authoring assistant can find a unit when someone names it by number.

6. **Course documentation.** In [curriculum/regulations/objectives.md](../../curriculum/regulations/objectives.md), add a short "How to read a unit number" paragraph after "How to read a code" (line 7). Write it as prose with inline examples, not as a table row that starts with `| UA.I.`, because the parsers read those rows.

7. **Course tree,** [ui/course-tree.js](../../ui/course-tree.js):
   - Add and export `labelOf(u)`, which returns `u.number + " (" + u.id + ")"`.
   - `layout()` (line 60): give each task row `chapter: units[i].number.split(".")[0]`.
   - `drawTask()` (line 219): label `r.chapter + " (Task " + r.task + ") · " + name`.
   - Node label (line 203): `u.number + " (" + <the existing code expression> + ")"`.
   - Node hover (line 157) and lane hover (line 177): `labelOf(u)` in place of `u.id`.

8. **App,** [ui/app.js](../../ui/app.js):
   - Add `unitLabel(id)`. It looks up the unit in `lastState` and returns `CourseTree.labelOf(u)`. It returns the bare id if the state has not loaded yet.
   - `gearTag()` (line 150): `unitLabel(block.unit)`.
   - Missed units in the mock result (line 404): map through `unitLabel`.
   - Map header (line 629): `cur.number.split(".")[0] + " (Task " + cur.task + ") · " + name`.
   - Picker title (line 663): `CourseTree.labelOf(u) + " · " + title`.

9. **Instructor list,** [ui/instructor.js:219](../../ui/instructor.js#L219): option text `u.number + " (" + u.id + ") · " + title`. The option value stays `u.id`. This is inline because the instructor fixture does not load course-tree.js.

10. **Fixtures.** Add `number` to the stub units in [tests/fixtures/course_tree.html](../../tests/fixtures/course_tree.html), [tests/fixtures/panels.html](../../tests/fixtures/panels.html) and [tests/fixtures/instructor.html](../../tests/fixtures/instructor.html). The tree reads `number` for task rows, so a stub without it fails.

## Not changed

- Lesson file names, the ledger, STATUS.md, the facts table, the mock table, API keys, DOM keys and option values. All keep the ACS code.
- The `unit` field in the model's JSON output. The server overwrites it in any case.
- The missing-content error ([server.py:635](../../server.py#L635)). `handle_answer` does not check the unit it gets, so an invalid code would make `number_of` raise an error. The message keeps the bare code.
- The "Unknown unit" error. An unknown unit has no number.
- The mock result by-task rows, the mock debrief "BY TASK" lines and the task-boundary hover text. They keep the task letter. Add the chapter there too if it is wanted later.
- The debug log of sent payloads.

## Tests

New file `tests/test_unit_numbers.py`:

- `number_of`: 1.1, 1.5, 2.16, 2.21a, 5.3c and 6.7 for the codes above.
- `label_of("UA.I.A.K5")` is `1.5 (UA.I.A.K5)`.
- All 77 units in the real `objectives.md` (`ledger.load_units`) get 77 different numbers.
- `mock_gate_context` lists a missed unit as `2.16 (UA.I.B.K16): <objective>`.

Changes to existing tests:

- [tests/test_phase2.py:470](../../tests/test_phase2.py#L470): assert `number` is `2.16` for `UA.I.B.K16` and `1.1` for `UA.I.A.K1` in the state.
- [tests/test_phase2.py:732](../../tests/test_phase2.py#L732) and [tests/test_phase3.py:169](../../tests/test_phase3.py#L169): expect `UNIT: 2.16 (UA.I.B.K16)`.
- [tests/fixtures/course_tree.html](../../tests/fixtures/course_tree.html): add checks that a node label reads `1.1 (UA.I.A.K1)` and the task row reads `1 (Task A) · Regulations`.

## Verification

1. Run `python3 -m unittest discover -s tests -v` from the course folder. All tests pass.
2. Run `python3 tools/check_integrity.py`. The result is the same as before the change.
3. Start the app and check by eye:
   - Tree nodes show `1.1 (UA.I.A.K1)`. Sub-elements show `2.21a (B.K21a)`. Task rows show `2 (Task B) · Operating Rules`.
   - The labels fit the sidebar at its default width of 316 px. Task C's long name was already cut before this change.
   - The map header, picker title, block tag above each lesson, and instructor unit list show the label.
   - In the ask box, ask "what is lesson 2.16 about?". The answer is about prior authorization in controlled airspace.
4. After the change, save a memory note: units are named by chapter.lesson numbers, and `number_of` in orchestrator.py holds the rule.

## As built

Built as planned, with these small additions:

- `tests/test_phase3.py`: the end-of-area test now checks the full label `4.1 (UA.I.D.K1)` in the set-aside list. Before, it checked only the bare code, which still matched after the change.
- The course tree fixture comment and the `tests/test_course_tree.py` docstring now say that the fixture also checks the labels.

Verification on October 17, 2026:

- 196 tests pass, 1 skipped (the PDF tool test, which needs `pdftotext` and `reportlab`). Before the change: 192 pass, the same 1 skipped.
- `tools/check_integrity.py` gives the same result as before the change.
- A copy of the server with the mock provider and a scratch ledger was driven in Chrome with Playwright. The block tag read `1.1 (UA.I.A.K1)`, the map header `1 (Task A) · General`, and the picker title `1.1 (UA.I.A.K1) · Applicability of 14 CFR part 107 ...`. The instructor list had 77 labelled options, from `1.1` to `6.7`. The tree showed `2.4a (B.K4a)` for a sub-element, and all labels fit the 316 px sidebar.
- Not done: the ask-box check ("what is lesson 2.16 about?"). The mock provider cannot answer it, so it needs a run with a real model.
