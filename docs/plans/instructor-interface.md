# Plan: Foundational for every unit, the instructor interface, and the instructor guide

Status: built, October 16, 2026. See "As built" at the end for what differs from the plan.

## Decisions taken

1. Every unit with a Guided lesson offers all three speeds. Where no `<unit>.gear3.md` exists, the tutor builds Foundational from the Guided lesson (option B).
2. The tutor's first Foundational lesson for a unit is saved as that unit's `.gear3.md`, marked as a draft in its header. Later students get that lesson. An instructor's first save removes the draft mark.
3. Instructor mode is off unless the course starts with `./start.sh --instructor` or `"instructor": true` in `config.json`.
4. Fast-track can have an optional `<unit>.gear1.md`, with the same rule as Foundational: a file wins; without one, the tutor shortens the Guided lesson.
5. Each lesson file carries a version number. The save dialog asks whether the content is vetted, and `STATUS.md` records the answer with the version.
6. A diagram the instructor accepts is stored as an SVG file in `curriculum/regulations/images/` and referenced from the lesson. The tutor then shows the same vetted picture every time instead of drawing a new one. This follows the existing image rule in `prompts/orchestrator.md`.

## Part 1. Foundational for every unit, with drafts saved as course material

### Lesson file header

The header of every lesson file can carry two more lines:

```
---
source: 14 CFR 107.41 | https://www.ecfr.gov/current/title-14/section-107.41
version: 1
draft: written by the tutor on 2026-10-16 from the Guided lesson; no instructor has reviewed it
---
```

Only the `source:` lines go into the model's message. The version and the draft mark stay out of it, as principle 20 requires for status notes.

### Which file each gear uses

| Gear | File | When there is no file |
|---|---|---|
| 1, Fast-track | `<unit>.gear1.md` | The tutor shortens `<unit>.md`, as now. |
| 2, Guided | `<unit>.md` | The unit cannot be taught, as now. |
| 3, Foundational | `<unit>.gear3.md` | The tutor builds it from `<unit>.md`, and the server saves a draft `.gear3.md`. |

When the Foundational file is still a draft, the message carries the draft as the form to follow and the Guided lesson and the reference facts as the ground truth. On any conflict, the Guided lesson and the facts win. This stops an unreviewed lesson from becoming the source of facts for later students.

### Saving a draft

- A student who picks Foundational gets a general lesson. The server saves that lesson as the draft.
- A re-teach after a miss starts from one student's mistake, so it is not a good draft. The server writes a separate general lesson with the teach prompt on a background thread and saves that. This costs one extra model call per unit, once.
- The draft's body starts with the objective, then the lesson. Its source lines come from the lesson's citations. It starts at version 1.
- The server writes the file atomically and never replaces an existing `.gear3.md`.
- `STATUS.md` shows the unit's Foundational column as `tutor draft v1`.

### Changes

1. `ledger.py`: `available_gears()` returns 1, 2 and 3. The state gets a `gear_files` field per unit: for each gear, no file, or the file's version and whether it is a draft. The course tree and the picker use it.
2. `orchestrator.py`: `parse_content()` also returns the header's version and draft mark. `content()` picks the file per the table and says which form it is: written, draft, or built from Guided. `_material()` labels the content to match, and adds the Guided lesson when the gear-3 content is a draft or missing.
3. `prompts/orchestrator.md`: one sentence each in the Gear 1 and Gear 3 rules. When the material is the Guided lesson, build the gear's form from it and add nothing it does not say.
4. `server.py`: save the draft, as above.
5. Course tree and picker: all three lanes can be clicked. The picker and the hover text name the source of each gear, for example "Foundational: tutor draft, version 1".
6. Documents: a v3.2 changelog entry and changes to Sections 12.4 and 12.6 of `IMPLEMENTATION_PLAN.md`; the Foundational line in `README.md`; the conventions in `STATUS.md`.

## Part 2.5. The instructor interface

### Turning it on

`./start.sh --instructor` passes the flag to `server.py`, or `"instructor": true` in `config.json` turns it on. Without either, the page has no Instructor button and the instructor endpoints answer 404. The server prints "Instructor mode: on" at start.

### What the instructor sees

- An **Instructor** button in the top bar, on every screen: lesson, question, feedback, exam result, and the done screen.
- The button opens a workspace over the course. It opens on the unit on screen, or the unit picked in the course tree, at the gear on screen.
- The top of the workspace holds a unit picker with all 77 units, the tabs **Fast-track**, **Guided** and **Foundational**, and Close. Each tab shows its file state: "hand-written, version 3, vetted", "tutor draft, version 1", or "no file: the tutor writes it from the Guided lesson".
- Three columns:
  1. **Editor:** the source lines and the body in a plain text box. The server manages the version and draft lines.
  2. **Preview:** the text as a student sees it, with the same Markdown renderer, images and drawings.
  3. **Assistant:** a conversation with the authoring tutor.
- A tab with no file offers "Start from the Guided lesson" or "Ask the tutor for a first version".
- Buttons: **Save**, **Revert** (load the saved file again), and **Try it as a student**, which saves, closes the workspace, and teaches the unit at that gear.

### Working with the assistant

- The instructor writes a request, for example: "This looks good, but can we add a diagram that shows how the altitude is worked out in this scenario?"
- The authoring model gets the request, the text in the editor with unsaved changes, the unit's objective, the Guided lesson when the tab is Fast-track or Foundational, the reference facts, the knowledge-base chunks that match, and the earlier turns of this conversation. On the `claude_code` backend it can also search the course material with the same read-only tools as the chat.
- The model replies with a short note and a full revised file. The note streams into the assistant column, and the revision streams into the preview as a proposal, with a line-by-line diff against the editor.
- **Apply** puts the proposal into the editor; **Discard** drops it. The instructor can edit by hand and ask again. Nothing is saved until Save.
- A new prompt, `prompts/author.md`, sets the rules:
  - Keep the file format and the source lines.
  - Add no fact the material does not support, and add a source line for any new source.
  - Draw diagrams as fenced `svg` blocks, under the tutor's drawing rules: every label from the cited material, and no scripts.
  - Say plainly when a request needs a fact the material does not have.
  - Reply as one JSON object: `{"type": "revision", "note": "...", "text": "..."}`.
- The streaming and the status indicator are the same as in the course, for example "Revising the lesson".

### Saving

The save dialog asks for a short note on the change, and asks: "Is this content vetted against the source text?" (Yes / Not yet). The server then does these steps:

1. Checks the unit against the objectives list and the gear against 1, 2 and 3. The page never sends a path, so nothing outside the lesson files can be written.
2. Moves each new fenced `svg` drawing into `curriculum/regulations/images/<unit>-<n>.svg` and puts `![description](images/<unit>-<n>.svg)` in its place.
3. Increments the version, removes the draft line, and writes the file atomically.
4. Updates the unit's row in `STATUS.md`: the gear's column shows `v4 vetted` or `v4 edited`, plus the unit's status and a dated note with the change note.
5. Runs the integrity check on the file and shows any warning, for example a missing source line.

The next lesson uses the new file at once. A prefetch built from the old text no longer matches, so it is not used. Git keeps the history; the guide tells instructors to commit after a session.

### Endpoints (instructor mode only)

- `GET /api/author?unit=<code>&gear=<1-3>`: the file text, its version and draft mark, the state of each gear, and the unit's `STATUS.md` row.
- `POST /api/author/ask`: streams the revision with the same events as the chat: `start`, `delta` for `note` and `text`, then `done` with the full text and the diff.
- `POST /api/author/save`: saves as above and returns the new state.

### `STATUS.md`

The table gets a Gear 1 column: Unit, Gear 1, Gear 2, Gear 3, Reference facts, Status, Notes. A gear cell is empty (no file), `tutor draft v1`, `v3 edited`, or `v3 vetted`. The server changes only the row of the unit it saves.

## Part 2. README section: "Improving the tutor"

This section is for instructors who know the subject, such as remote pilots and flight instructors, and who are not programmers. It starts with the instructor interface as the main way in, and then covers editing the files directly for those who use an editor and git.

1. What the tutor teaches from, and what it cannot know.
2. How to find what needs work: units reached at Foundational, set aside, or marked "needs attention" in the course tree; misses per unit in `progress/student-ledger.md`; the questions students ask in the chat; tutor drafts waiting for review.
3. Where each fix goes, as a table: a wrong fact, a lesson that does not land, a unit students keep missing, a weak quiz question, a practice-exam item, a wrong chat answer.
4. How to use the instructor interface, step by step, with the diagram request as the worked example.
5. How to write a lesson file by hand, for each gear.
6. How to vet: against the source text, where the CFR wins, and how the save dialog and `STATUS.md` record it.
7. How to check a change, and how to hand it over: commit, or send the files.

## Order of work

1. Part 1, with its tests.
2. Part 2.5 on the server: endpoints, `prompts/author.md`, saving, with tests.
3. Part 2.5 in the page, with browser tests.
4. Part 2, then the plan, README and `STATUS.md` updates.

Each step leaves the test suite passing.

## Tests

Part 1:
1. File choice per gear: a `.gear1.md` wins at gear 1; a `.gear3.md` wins at gear 3; a draft gear 3 also carries the Guided lesson and the facts; no file gives the "built from Guided" label.
2. The version and the draft line never reach the model's message.
3. Teaching at Foundational with no file saves a draft `.gear3.md`: version 1, the draft line, and source lines from the citations. A re-teach at Foundational starts a background general lesson and saves that. An existing file is never replaced.
4. A miss at Guided leads to Foundational in every unit. Two misses at Foundational set the unit aside.
5. The state reports each gear's file.

Part 2.5:

6. Without the flag, the instructor endpoints answer 404 and the page has no button. With it, both are there.
7. An unknown unit, gear 4, or a unit written as a path is refused. No file outside the lesson files is written.
8. A save increments the version, removes the draft line, moves a drawing into `images/` with a reference, updates the `STATUS.md` row with the vetting answer, and the next lesson's message contains the new text.
9. The assistant's message carries the editor text, the request, the facts, the Guided lesson for gears 1 and 3, and the earlier turns. The note and the text stream, and `done` carries the diff.
10. Browser, with the mock backend:
    - the Instructor button on each screen
    - the workspace opens on the current unit and gear
    - an edit updates the preview
    - a request returns a proposal and a diff; Apply, then Save with "Not yet"
    - the `STATUS.md` row and the version are updated
    - Try it as a student works
11. Browser, with the real model: the diagram request on a Foundational lesson, one more round of changes, Save, and the lesson then shows the image.

## Risks

- **An unreviewed tutor draft becomes material for later students.** The draft mark, the Guided lesson and the facts sent with it as ground truth, and the drafts listed in the workspace and in `STATUS.md` limit this.
- **A web page that writes files.** The instructor flag, the 127.0.0.1-only server, the unit and gear checks, no paths from the page, and atomic writes limit this.
- **A diagram with a label the material does not support.** The prompt forbids it, the instructor reviews it before saving, and the vetting question makes the check explicit.
- **Two copies of the course edit the same file.** Git merges the changes. This is out of scope.
- **Cost:** each assistant call sends the file, the Guided lesson, the facts and the chunks, about 4,000 to 8,000 tokens.

## As built

Built October 16, 2026, in the order above. The test suite had 181 tests (1 skipped), and 189 after the follow-up below; new are `tests/test_foundational.py`, `tests/test_instructor.py`, and `tests/test_instructor_page.py` with `tests/fixtures/instructor.html`. Differences from the plan, and what the build found:

1. **MCP servers in every `claude -p` call.** The real-model check showed 25,000 tokens of context on a lesson call that needs about 3,700. The user's claude.ai connectors and plugins loaded into every tutor call, because `--setting-sources ""` does not turn them off. They also put tools that reach the user's Google account in front of the tutor. The `claude_code` adapter now passes `--strict-mcp-config`, which loads no MCP servers; a trivial call fell from 21,563 to 264 tokens. `tests/test_phase2.py` checks the flag.
2. **The save dialog acts on its buttons, not on its `close` event.** Headless Chrome under `--dump-dom` closes a dialog but never fires the event, so the browser test could not see a save. A click on "Not yet" or "Yes, vetted" saves; Enter in the note field clicks "Not yet", the first button; Escape and Cancel save nothing.
3. **Test helpers copy the fixture curriculum** into each test's temporary folder (`stub_paths` in `tests/test_phase3.py`, `mock_config` in `tests/test_phase2.py`), because teaching at Foundational now writes a draft file into the curriculum. Two tests that hide a fixture file now hide it in the copy.
4. **Existing tests changed:** `test_gear_three_uses_its_own_file_or_else_the_guided_lesson` and `test_foundational_without_a_file_is_built_from_the_guided_lesson` replace the two tests of the old rule that a unit offers gear 3 only with a file. The browser fixtures `panels.html` and `chat_drawing.html` load or stub `instructor.js`, which `app.js` now sets up.
5. **`STATUS.md`** got its Gear 1 column by hand, and the server edits rows through `status.py`.
6. **Real-model run** (claude_code, Opus 5): two assistant rounds on the UA.I.B.K16 Foundational file took 44 s and 76 s and wrote 3,600 and 6,000 tokens, because each revision is the whole file. The save stored the diagram as `images/UA.I.B.K16-1.svg`, and "Try it as a student" taught the unit at Foundational with the diagram in the lesson.

Open points, resolved October 16, 2026 (approved follow-up plan):

1. **The unit and gear on a block are the course's.** `teach()`, `quiz()`, and `handle_answer()` now stamp the unit and gear they decided on the lesson, question, and feedback, whatever the model wrote. With the mock, the gear tag after "Try it as a student" now shows the gear tried.
2. **A draft written during a session is used from the next session.** `Session.drafted` records the units this session wrote a Foundational draft for, and `Course.content()` gives the teaching calls the Guided lesson for them until the next pace choice or server start. So the question prefetched with the first Foundational lesson still matches; tests show it is used on both paths (a picked lesson, and a re-teach with its background draft), and they fail without the change.
3. **The assistant sends only its changes.** `prompts/author.md` asks for `edits`: a `from`/`to` span or an `after` place, each copied exactly from the file, with the new `text`. `apply_edits()` in `server.py` applies them and refuses a change that does not fit (missing, repeated, out of order, overlapping); then the server asks once for the whole file. A first version or a full rewrite still comes as `file`, which streams into the preview. The whole-file key was renamed from `text` to `file`, because the streaming parser takes the first `"text"` key, and in a reply with changes that belongs to a change.

Measured with the real model on the UA.I.B.K16 Foundational diagram request: the second round (larger labels) fell from 76 s and 6,000 output tokens to 31 s and 2,700. The first round (add a diagram) did not get faster: 40 to 59 s. Its reply is about 1,000 tokens; the rest is thinking. At the default effort, 2,219 of 3,262 output tokens were thinking (45 s). With `--effort low` the same request took 13 s, with 64 thinking tokens and a valid reply. The effort is unchanged: less thinking may make worse diagrams, and that is the user's call.
