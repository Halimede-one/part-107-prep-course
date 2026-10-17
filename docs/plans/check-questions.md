# Plan: check questions you can trust, plus instructor questions

Status: built, October 17, 2026. The suite passes (221 tests). The end-to-end check by hand with a real model is not yet done. See "As built" at the end for what differs from the plan.

## Context

The model writes every check question live, after each unit's lesson. The review found three weak points:

1. **"Already asked" holds IDs only.** The model sees `k16-a1`, not the stem, so it can repeat a question. The model also invents the IDs and reuses them across sessions (the real ledger has `k1-a1` twice). The mastery rule needs 2 correct answers on distinct IDs, so a reused ID blocks mastery.
2. **Only the prompt checks the key.** The server does not validate the question block at all. A missing or bad `answer` makes every student answer score as wrong.
3. **The list lives in memory.** `Session.asked` resets on every intake (each page load) and on each restart.

The user also wants instructor mode to accept two new inputs per unit, both saved to disk:

- **Guidance** for the question writer, for example "make sure the student understands X".
- **Verbatim questions** that the instructor writes and keys.

### Decisions made by the user

| Decision | Choice |
|---|---|
| Key check | Shape check plus fact check. No extra model call. One retry, then an error block. |
| Order | Instructor questions first, in file order. Then the tutor writes new ones. |
| Editor | A form in a fourth "Questions" tab of the instructor workspace. |

### Assumptions (correct me if wrong)

- Guidance is per unit, not per gear. Only the question writer gets it. Lessons and feedback do not.
- A question counts as "asked" when the server shows it, even if the student never answers it.
- An instructor question is vetted when the instructor saves it. No draft state, no `STATUS.md` change.
- Instructor questions never join the practice exam.

## Design

### Part 1. Persisted question log and server-assigned IDs (weak points 1 and 3)

- New file `progress/questions.jsonl`, with a new path key `questions_log` in `config.json`. One line per question shown:
  `{timestamp, unit, gear, question_id, origin: "tutor"|"instructor", review, stem, options, answer, rationale, citations, fact}`.
- The file is in `progress/`, which `research_dirs()` (`server.py:378`) keeps away from the chat tutor. The keys stay hidden.
- New `Course.asked(unit)` reads the log fresh on each call and returns that unit's records in file order. No cache. A fresh read makes the prefetch context and the real context equal.
- New `Course.log_question(block, origin, review)` appends one line. Model it on `log_response` (`server.py:1028`).
- `Course.quiz` gives each tutor question the ID `<unit>-q<n>`, where n is the number of logged questions for the unit plus 1. Example: `UA.I.B.K16-q3`. The model's own `question_id` is ignored.
- `quiz_context` (`orchestrator.py:334`) gets the earlier stems, one per line, with whitespace collapsed:
  ```
  ALREADY ASKED (ask something different):
  - <stem 1>
  - <stem 2>
  ```
- Remove `Session.asked` (used only at `server.py:257`, :460, :627).
- `handle_answer` does not change. It keeps the ID from the browser payload. The page always sends back the server's ID, and many tests send their own IDs.

### Part 2. Shape check and fact check (weak point 2)

- New `items.question_problems(block, facts=())` returns a list of problems in plain words. Rules:
  - the type is `question`; the stem is not empty
  - exactly 3 options with IDs A, B, C; the texts are not empty and differ after lowercasing
  - `answer` is A, B, or C; the rationale is not empty
  - if `fact` is set, it names a known label, and the keyed option contains that fact's answer
- The fact match compares words, not raw text. Both sides are lowercased, and each run of non-letters and non-digits becomes one space. Padding with spaces gives word boundaries, so "3 statute miles" does not match "13 statute miles". A leading "the", "a", or "an" in the fact answer is ignored.
- `_material()` (`orchestrator.py:285`) gets a `labelled=False` keyword. Only `quiz_context` passes `labelled=True`, which prints `- F1: fact -> answer [source | link]`. Teach, remediate, feedback, chat and author contexts stay unchanged.
- In `Course.quiz`, an error block passes through unchecked. That keeps an unreachable provider from doubling the wait. Any other block with problems gets one retry. The retry appends this to the context, in the same pattern as `author_ask` (`server.py:981`):
  `YOUR QUESTION DID NOT PASS THE COURSE'S CHECKS: <problems>. Write the question again.`
- If the retry also fails, the student gets an error block, and nothing is logged or stored as pending. The metrics line records `error="failed checks"` and the problems, like `server.py:374`.
- The server strips `answer`, `rationale` and `fact` before the block goes to the browser.
- **A fix the new error path needs.** Today `advance()` (`server.py:760`) has no branch for stage `review_quiz`. After a failed review question, Continue skips that review. Add one branch: `if stage == "review_quiz": return self.quiz(unit=self.session.reviewing, review=True)`.
- **Known limit.** Many fact answers are long, for example UA.I.A.K1's list. The model will often leave `fact` out, because quiz.md wants options of similar length. Then only the shape is checked. This is the level you chose. The instructor questions in Part 3 cover the units where this matters most.

### Part 3. Instructor guidance and verbatim questions: storage and serving

**File.** One Markdown file per unit: `questions/regulations/<unit>.md`, with a new path key `questions`. The folder is outside `curriculum/`, so the chat tutor cannot read the keys. The table uses the practice-exam columns, so `items.load_items` reads it.

```
# UA.I.B.K16 check questions

- Last item: 2

## Guidance

Make sure the student understands that LAANC gives authorization only in controlled airspace.

## Questions

| Item | Unit | Stem | A | B | C | Answer | Rationale | Source | Link |
|---|---|---|---|---|---|---|---|---|---|
| UA.I.B.K16-i1 | UA.I.B.K16 | ... | ... | ... | ... | B | ... | 14 CFR 107.41 | https://... |
```

- Instructor IDs are `<unit>-i<n>`. The server gives them on save, as `max(Last item, IDs present) + 1`. A deleted ID is never used again. Without this, a new question could take a deleted one's ID and count as already asked.
- On save, the server refuses `|` in any field, the same rule as the practice-exam file. It collapses whitespace in cells. Stems and options are inline Markdown, so this loses nothing.
- Guidance is free text over many lines. A line that starts with `## ` is refused, because it would end the section.
- Each question needs a source and an `http` link, as practice-exam items do.
- New helpers in `items.py`:
  - `load_questions(path)` returns `{guidance, items (file order), last}`.
  - `questions_text(unit, guidance, items, last)` returns the file text.
  - `item_question(item)` turns a file item into a question block, with the citation from source and link.
- The file is written with `replace_file` (`server.py:61`), which is atomic.

**Serving.** New `Course.instructor_question(unit)` returns the first item in the unit's file that is not yet in `asked(unit)`. It returns None if there is no such item. `Course.quiz` runs in this order:

1. If the unit has no content, return `missing_content`. This check comes first, so no question shows on a unit with no lesson.
2. If an instructor question is due, use it. No model call.
3. Otherwise, call the model, check the reply, retry once, and give the `-q<n>` ID.
4. If the block is a question, stamp the unit and gear, store it as pending, log it with its origin, strip the hidden fields, and set the review flag.

- `quiz_call` returns None when an instructor question is due. All three prefetch sites then make no call. `prefetch(None)` does nothing.
- Scoring does not change. `keyed = pending["answer"]` (`server.py:821`) holds the instructor's key.
- Instructor items never go into `self.items`. `mockexam.mock_items` would take them into the practice exam.

**Guidance.** `quiz_context(..., guidance="")` adds this block after ALREADY ASKED:

```
INSTRUCTOR GUIDANCE (what this unit's questions must make sure the student understands; it never overrides the vetted facts):
<text>
```

The server reads the guidance from the file on each call and passes it in. When an instructor edits the guidance, the context changes, so a stale prefetched question is not used.

### Part 4. Prompt changes (for your review)

`prompts/quiz.md`:

- **Remove:** the `question_id` bullet.
- **Add:** "**Name the fact.** If the key rests on one of the vetted facts, set `fact` to its label, for example `F2`. The keyed option must then contain that fact's answer word for word. The course checks this."
- **Add:** "**Follow the instructor guidance.** If the message has INSTRUCTOR GUIDANCE, the unit's questions must cover each point it names. If no question already asked tests a point, test that point now."

`prompts/orchestrator.md`:

- In the question contract (lines 35-37), remove `question_id` from the required fields and from the example.
- List `fact` as optional.
- Add a note that the server gives each question its ID.

### Part 5. Instructor API

Both endpoints sit behind `Handler.instructor()` and answer 404 without `--instructor`. The unit must be in `objectives`, otherwise the answer is 400. The page never sends a path.

- `GET /api/author/questions?unit=` returns `{unit, guidance, items: [{item, stem, a, b, c, answer, rationale, source, url}], sources: [{source, url}]}`.
  - The item keys match `load_items`, so no mapping is needed.
  - `sources` lists the Guided lesson's sources and the unit's fact sources, without duplicates.
- `POST /api/author/questions` takes `{unit, guidance, items}`. An item with no `item` field is new.
  - It checks everything first. If any check fails, it writes nothing and returns `{error, problems}` with status 200, like `author_save`.
  - On success it returns the GET shape, with the new IDs.
- Add the GET branch before the `/api/author?` branch (`server.py:1285`). Add the POST path to the gate at :1310.

### Part 6. Questions tab (UI)

- `ui/index.html`:
  - A fourth tab `#author-questions-tab` in `.author-gears`, with no `data-gear`.
  - A new panel `#author-questions`, a sibling of `.author-body`, between it and `.author-foot`. It holds a guidance textarea, `#questions-list` for the cards, `#questions-add`, and `#questions-dirty`.
- `ui/instructor.js`:
  - New state `qs = {on, saved, sources}`.
  - New functions: `loadQuestions`, `card`, `collect`, `questionsChanged`, `saveQuestions`, `showQuestions`.
  - Each card has the stem, A, B, C, a key radio, the rationale, a source select that fills an editable link field, and Delete.
- Changes to existing code:
  - Change both `.author-gears button` selectors (:89, :246) to `.author-gears button[data-gear]`. Otherwise the new tab sends `gear=NaN`.
  - The gear-tab guard at :249 becomes `(gear !== my.gear || qs.on)`, so the instructor can go back to the same gear.
  - `keepOrDiscard` (:77) checks `questionsChanged()` in questions mode.
- In questions mode:
  - Save and Ctrl+S post at once, with no vetted/edited dialog.
  - Revert reloads the questions. The unit select loads that unit's questions.
  - "Try it as a student" is hidden. The instructor's own log would mark the questions as asked.
  - Call `Dictation.cancel()` when the tab opens, because the request box goes out of reach.
- `ui/styles.css`: add `.author-body[hidden], .author-questions[hidden] { display: none; }`. `.author-col` sets `display: flex`, which overrides `hidden`. Add simple card styles in the existing look.

## Files to change

| File | Change |
|---|---|
| `items.py` | `question_problems`, `item_question`, `load_questions`, `questions_text` |
| `orchestrator.py` | `_material(labelled=)`, `quiz_context(already-asked stems, guidance=)` |
| `server.py` | remove `Session.asked`; add `asked`, `log_question`, `questions_path`, `instructor_question`, `author_questions`, `author_questions_save`; change `quiz_call`, `quiz`, `advance`; two Handler branches |
| `prompts/quiz.md`, `prompts/orchestrator.md` | Part 4 |
| `config.json` | path keys `questions`, `questions_log` |
| `ui/index.html`, `ui/instructor.js`, `ui/styles.css` | Part 6 |
| `tests/test_phase3.py` (`stub_paths`), `tests/test_phase2.py` (`mock_config`) | add the two path keys, pointing into the temp folder |
| `README.md` | add rows for `questions/` and `progress/questions.jsonl` to the file layout and "where each fix goes" |
| `docs/plans/check-questions.md` | a copy of this plan, after approval |

## Steps

Each step ends with the full suite green: `python3 -m unittest discover -s tests -v`.

1. Part 1: log, IDs, stems in the context. Verify with the TestQuestionsAsked tests.
2. Part 2 and the quiz.md/orchestrator.md changes for `fact` and IDs. Verify with TestQuestionChecks and the retry tests.
3. Part 3 and the guidance prompt rule. Verify with TestInstructorQuestions (serving, guidance).
4. Part 5. Verify with the HTTP tests.
5. Part 6. Verify with the headless page test, then by hand (see Verification).
6. README rows and the plan copy in `docs/plans/`.

## Tests

**New `tests/test_questions.py`**

`TestQuestionChecks`
- `test_a_sound_question_has_no_problems` (the mock block passes)
- `test_three_distinct_options_a_key_among_them_a_stem_and_a_rationale_are_required`
- `test_the_keyed_option_must_state_the_named_fact` (pass; "13 statute miles" fails; unknown `F9` fails)
- `test_without_a_named_fact_only_the_form_is_checked`

`TestQuestionsAsked` (uses `make_course`)
- `test_each_question_served_gets_its_own_id_from_the_course` (`UA.I.B.K16-q1`, then `-q2`, though the mock always says `mock-q1`)
- `test_questions_asked_survive_a_new_session_and_a_restart` (intake, then a fresh course on the same temp folder: the stem is in the context and the ID continues)
- `test_two_right_answers_master_a_unit_though_the_model_repeats_its_id`
- `test_a_question_that_fails_the_checks_is_written_once_more_with_the_problems`
- `test_a_question_that_fails_twice_is_an_error_and_is_not_logged`
- `test_a_failed_review_question_is_asked_again_on_continue`

`TestInstructorQuestions`
- `test_instructor_questions_come_first_in_file_order_then_the_tutor_writes` (no model call for the first two)
- `test_an_instructor_question_is_scored_on_its_key_and_recorded_under_its_id`
- `test_nothing_is_prefetched_while_an_instructor_question_is_due`
- `test_the_guidance_goes_into_the_quiz_message`
- `test_a_save_assigns_new_ids_and_never_reuses_one`
- `test_a_save_with_a_problem_writes_nothing_and_names_the_question` (a pipe, duplicate options, answer D, a link that is not http)
- `test_saved_questions_read_back_with_multi_line_guidance`
- `test_instructor_questions_never_join_the_practice_exam`

**Changes to existing tests**
- `test_phase3.py:174` `test_quiz_context_supplies_the_ground_truth_and_avoids_repeats`: pass stems; assert `F1:` is in the quiz context and not in `teach_context`.
- `test_phase2.py:770`: add `questions` and `questions_log` to the folders the chat must not read.
- `test_instructor.py`:
  - add 404 checks for both new endpoints without the flag
  - `test_only_real_units_are_accepted_for_questions` (400 for `../../config`)
  - `test_read_and_save_the_questions_over_http`

**Page test**
- Turn `tests/test_instructor_page.py` into a `page(query)` helper, as `test_layout.py` does.
- Add `test_write_and_save_the_questions_on_a_unit`, which loads `instructor.html?questions`. The fixture picks its steps from `location.search` and stubs the GET, a POST success and a POST refusal.
- The test checks that:
  - the tab hides the lesson columns and the Try button
  - the guidance and the cards load
  - choosing a source fills the link
  - Add and Delete work
  - an edit marks unsaved changes
  - with `confirm` false, a tab switch keeps the edits
  - the save payload has the IDs and the key, and new cards have no ID
  - a refusal shows its problems and keeps the edits
  - after a save, the cards show the new IDs
  - the gear tab brings the lesson editor back
- No dialog or rAF is used. The steps set values and dispatch `input` events.

## Verification (end to end)

1. Run the full suite. Expect all tests to pass, with the Chrome tests skipped only if Chrome is missing.
2. Start the course with `./start.sh --instructor`. Open the instructor workspace and choose a unit, for example UA.I.B.K16. Open the Questions tab, write guidance and two questions, and save.
3. Check that `questions/regulations/UA.I.B.K16.md` has the guidance, two rows with `-i1` and `-i2`, and `- Last item: 2`.
4. Close the workspace and pick the unit in the course tree. Check that the two instructor questions come first and arrive with no "Writing a question" delay.
5. Answer them. Check that `progress/questions.jsonl` has two `instructor` lines, and that the ledger shows two attempts under the `-i` IDs.
6. Get a wrong answer so the course asks a third question. Check that it has a `-q` ID, does not repeat the two stems, and serves the guidance. Judge this by eye.
7. Reload the page, pick a gear, and return to the unit. Check that the next question still avoids the earlier stems.
8. Save a question with a `|` in the stem. Check that the page names the problem and the file does not change.

## Found during review, not in this plan

- A server restart with a question on screen loses `pending`. The answer then scores as wrong. The new log could restore it by ID, in about 5 lines.
- A restart during spaced review drops the remaining reviews for good, because `last_task` is saved before the reviews run (`server.py:794`).
- The "already asked" list has no length limit. A unit the student keeps missing sends more stems each time. This stays small in practice, because a unit is set aside after 2 misses at the deepest gear.
- `tools/check_integrity.py:148-167` could use `question_problems` and also check the `questions/` files. Not done here.

## As built

The build follows the plan. These points differ or add detail:

- `Course.quiz` keeps the order of Part 3. The tutor's question moved to a new `Course.tutor_question`, which holds the check and the one retry. `Course.question_problems` runs `items.question_problems` with the unit's facts and flags a failure in the metrics.
- A tutor question that fails twice becomes this error block: "The tutor wrote a question that did not pass the course's checks: <problems>. Try again for a new question." The page shows it with its "Try again" button.
- On save, an ID that the file does not hold gets a new number. The page cannot set an ID such as `m-a1`, which would collide with a practice-exam item. A second card with the same ID also gets a new number.
- The GET reply also carries the unit's `title`. The POST reply is the GET reply plus `saved: true`. The handler trims the guidance.
- The questions file starts with one line of prose that says what the file is.
- A card's source list holds the Guided lesson's sources and the unit's fact sources. A question saved with another source keeps that source in its own list.
- `load` in `instructor.js` now calls `showQuestions(false)`, which also marks the gear tab. That replaced the loop that marked the tab.
- The page fixture runs the Questions steps when it loads with `?questions`. Its `confirm` stub can now answer no.
- One extra test: `test_a_missing_questions_file_reads_as_empty`.
