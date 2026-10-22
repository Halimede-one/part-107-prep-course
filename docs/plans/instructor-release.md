# Instructor release: implementation plan

Status: all decisions taken October 22, 2026; implementation started the same day.

## Context

The course goes to instructors. Each instructor runs it on their own machine and vets the material against the source text. A review on October 22, 2026 found that the code is ready for this, but the docs are not:

- The README tells the reader to export an API key for the default `anthropic` backend. `config.json` ships `claude_code`.
- The README has no quick start for instructors. Setup starts at line 103, and the instructor guide starts at line 244, between the cost tables and the build steps.
- Nothing tells an instructor how to get the course or how to return their work.
- Several statements are stale: Tasks B to F "not authored", 7 Foundational files (there are 8), the generated vetting guide of October 17, and the status line of `IMPLEMENTATION_PLAN.md`.
- The README never says that the course covers only Area I, Regulations. The readiness banner says "Ready to schedule the real exam".
- `tools/check_links.py` stops with a traceback when a host times out.
- In instructor mode, the server accepts a POST from any web page. A page in the same browser can overwrite a lesson file.

What already works, checked October 22, 2026: 221 tests pass (1 skip) on Python 3.13 and 3.10, the strict integrity check has 0 errors, a fresh clone runs on the mock backend, and the `claude_code` backend teaches and asks a question for unit 5.5.

Decisions taken (October 22, 2026):

1. **Both backends.** An instructor uses `claude_code` on their own Claude plan, or `anthropic` with their own API key.
2. **Git branches.** Each instructor commits on their own branch. The maintainer merges the branch into `main`.
3. **Two documents.** `README.md` becomes the instructor guide. A new developer document holds the rest.
4. **Default provider (O1).** `config.json` ships `anthropic`. The maintainer starts their own runs with `--provider claude_code`.
5. **Clone URL (O2).** `https://github.com/Halimede-one/part-107-prep-course`. The repo becomes public after this round of work.
6. **Pull requests (O3).** Instructors open pull requests. The repo is public, so an instructor without write access forks it and opens the pull request from the fork.
7. **Developer document (O4).** `DEVELOPING.md` in the top folder, next to the README.
8. **Readiness text (O5).** Banner: "Regulations area: ready for the knowledge test" and "Regulations area: not yet ready for the knowledge test". Tree: "Regulations area ready for the knowledge test".
9. **Diagrams (O6).** The student's path and the gears stay in the README. The data flow, the teaching turn, and the ask-the-tutor diagrams move to `DEVELOPING.md`.
10. **License (O7).** No action for now. The repo is public only for the instructor feedback round.
11. **Commit email (O8).** Kept as it is.
12. **Practice exam keys (O9).** Kept in the public repo.

## Part 1. Choose the backend without editing config.json

`config.json` is a tracked file. An instructor who changes `provider` in it puts that change in their commit. Each merge would then change your backend. A command-line flag keeps the choice out of git.

1. **Flag.** In `main()` ([server.py:1574](../../server.py#L1574)), add `--provider NAME`, next to `--instructor`. Pass it to `Course`.
2. **Override.** `Course.__init__` ([server.py:274](../../server.py#L274)) gets `provider=None`. When it is set, write it into `self.config["provider"]` before `LLMClient(self.config)`.
3. **Unknown name.** `LLMClient` already raises `LLMError` with the list of names. In `main()`, catch it around `Course(...)` and exit with that one line, not a traceback.
4. **Missing key note.** Move the note in [start.sh:12-18](../../start.sh#L12-L18) into `main()`, after the course is built. Print it when `course.client.name` is `anthropic` and the variable named by `api_key_env` is not set. Two reasons for the move: the note must follow the flag, and Windows users run `server.py` without `start.sh`. Remove lines 12 to 18 from `start.sh`. It already passes `"$@"` to the server, so `./start.sh --instructor --provider claude_code` works.
5. **Default.** Set `"provider"` in [config.json:2](../../config.json#L2) as decided in O1.

## Part 2. README.md, the instructor guide

The reader is an instructor who knows Part 107 and need not know programming. They can use a terminal and follow git commands that are written out in full. Most of the text comes from the current README. New text is marked "new".

1. **Title and purpose.** What the course is. The scope: Area I, Regulations, 6 tasks, 77 units. The other four areas are not in the course. What we ask instructors to do. A warning at the top: the content is a draft and is not vetted, so do not use it yet to prepare for the test. The repo is public, so students can find it. (New, scope text from the intake page.)
2. **What you need.** Git, and access to the repo. Python 3.8 or newer. One backend from section 4. Chrome or Edge, for the microphone. macOS or Linux; on Windows, run `python server.py --instructor` (untested). (New.)
3. **Get the course.** `git clone <URL>`, then `git switch -c vetting/<your-name>`. (New, URL from O2.)
4. **Choose a backend.** A table with two rows: Claude plan (`claude_code`) and API key (`anthropic`). For each row: what to install, how you are billed, the start command, and what the chat can do. Claude Code was tested at version 2.1.235; older versions can lack flags that the course uses. Keep the current warning: a set `ANTHROPIC_API_KEY` makes Claude Code bill the API. (From "Choosing a backend", rewritten for two choices.)
5. **Start the course.**
   - The start command: `./start.sh --instructor`, with `--provider claude_code` when you use your Claude plan.
   - Open `http://localhost:8107`. Ctrl+C stops the server.
   - Usual waits: 15 to 30 s for a lesson, 30 to 60 s for a diagram request, and up to two minutes for a chat answer.
   - To start over: stop the server, delete the `progress/` folder, and start again.
   (From "Run it", plus new lines.)
6. **Speaking a question.** As now.
7. **How the course teaches.** The student's path and the gears, with their two diagrams, shortened. (From the top of the README.)
8. **Vet the material.** The current "Improving the tutor" section, with three changes:
   - "Vet" gives the order of work: open `docs/vetting-guide.html`, take your units, and check each one.
   - "Record the result" says that the workspace records lesson saves. You edit the Reference facts and Status cells in `STATUS.md` by hand.
   - "Report a problem you do not fix" says to write it in the unit's Notes cell, with the date. Git records who wrote it. (New.)
9. **Hand your work back.** (New.)
   - Run `python3 tools/check_integrity.py` and `python3 tools/check_links.py`.
   - `git add curriculum reference questions mock`. This takes only course material. It leaves out `config.json`, `progress/` and `docs/`.
   - `git commit -m "Vet 2.1 to 2.5: ..."`, with the unit numbers in the message.
   - `git push -u origin vetting/<your-name>`, then the pull request from O3.
   - Do not commit `docs/vetting-guide.html`. The maintainer regenerates it after each merge, so two branches do not collide on it.
10. **For developers.** One line that points to `DEVELOPING.md`.

## Part 3. DEVELOPING.md, the developer document

The reader is the maintainer or a developer who changes the code or rebuilds the content. Most of the text moves from the current README.

1. **Run it.** All four backends, including `ollama` and `mock`, the `--provider` flag, and the `claude_code` sandbox notes. (From "Run it" and "Choosing a backend".)
2. **How the course works.** The data flow, the teaching turn, and the ask-the-tutor diagrams, with their text. (From the top of the README.)
3. **Estimated AI costs.** As now. One change: the Tasks B to F assumption ([README.md:191](../../README.md#L191)) says that the estimate came before those units were written and was not measured again.
4. **Running the tests.** As now. Add: the browser tests need Chrome or Chromium and skip without it. One test needs `reportlab` and skips without it.
5. **Where this is up to.** As now, with these updates: 8 Foundational files, not 7, and all 77 units written but not vetted. Add the open items: the hand check of check questions with a real model, course tools and web search on `anthropic`, restoring pending questions after a restart, and `questions/` files in the integrity check.
6. **Merging an instructor branch.** (New.)
   - Rows of `STATUS.md` and the facts table merge without conflict when instructors vet different units, so assign whole chapters.
   - Two branches can each hold a tutor draft for the same Foundational file. Keep one of them.
   - After each merge, run the strict integrity check and `python3 tools/vetting_guide.py`, then commit the guide.
7. **Building the content.** Steps 1 to 9 as now. Step 1 no longer says to set `provider` in `config.json`. It says to use `--provider claude_code`.
8. **How it fits together.** The file map as now, plus `vetting_guide.py` in `tools/`, `questions/`, `DEVELOPING.md`, and a full `docs/` line (diagrams, plans, mockups, investigations, the vetting guide).
9. **Design records.** Pointers to `LLM_COURSEWARE_DESIGN_AND_PRINCIPLES.md`, `IMPLEMENTATION_PLAN.md`, and `docs/plans/`.

## Part 4. The vetting guide

The page is generated, so its text changes go into [tools/vetting_guide.py](../../tools/vetting_guide.py).

1. Line 307: point to the README section "Vet the material" instead of "Improving the tutor, section Vet".
2. "After vetting" (lines 374 to 381) becomes two lists:
   - "When you finish your units": run the two checks, then commit and push as in README section 9.
   - "For the maintainer, after a merge": regenerate this page, run the course with a real model, and package.
3. Regenerate `docs/vetting-guide.html`. That also puts the count of Foundational files (8) and the 2.1 note up to date.

## Part 5. Small fixes

1. **Readiness text.** Change [ui/app.js:436](../../ui/app.js#L436), [ui/app.js:439](../../ui/app.js#L439), and [ui/course-tree.js:231](../../ui/course-tree.js#L231) to the O5 text. Do not change the mockup copy in `docs/mockups/`, because it is a design record.
2. **Link checker.** In `probe()` ([tools/check_links.py:60](../../tools/check_links.py#L60)), catch `OSError` after `URLError`, in the first request and in the GET retry. Return status 0 with the error text. A timeout then shows as one `FAIL` line, and the run goes on. `TimeoutError` and the connection errors are subclasses of `OSError`.
3. **Origin check.** At the start of `do_POST` ([server.py:1434](../../server.py#L1434)), read the `Origin` header.
   - If the header is present and is not `http://localhost:<port>` or `http://127.0.0.1:<port>`, answer 403 and change nothing.
   - `<port>` is the port that the server is bound to (`self.server.server_address[1]`), so tests on a free port pass.
   - A request with no `Origin` header (curl, the tests, the tools) is accepted as now.
   - Browsers send `Origin` on every cross-site POST. A page on another site can then no longer write lesson files, the ledger, or `STATUS.md`.
4. **STATUS.md residue.** The note for 1.4 at [STATUS.md:10](../../curriculum/regulations/STATUS.md#L10) contains the save note "test changes in grammar". New note: "2026-10-17: the body is the v1 text, restored from commit 51606b7 after commit bce7ce6 emptied the file; the version line stays at 2. Not yet vetted." The notes on 1.6 and 1.7 are real edits and stay.
5. **IMPLEMENTATION_PLAN.md.**
   - Line 3: content is written for all 77 units and none is vetted. The instructor release is in this plan.
   - Section 13, item 3 (line 309): mark it done on October 17, 2026, with a pointer to `docs/plans/content-tasks-b-to-f.md`.
   - Leave the rest. It is the record of the build.

## Files changed

| File | Part |
|---|---|
| `server.py` | 1 (flag, override, startup note), 5.3 (origin check) |
| `start.sh` | 1 (note removed) |
| `config.json` | 1 (default provider, O1) |
| `README.md` | 2 (rewritten as the instructor guide) |
| `DEVELOPING.md` | 3 (new) |
| `tools/vetting_guide.py`, `docs/vetting-guide.html` | 4 |
| `ui/app.js`, `ui/course-tree.js` | 5.1 |
| `tools/check_links.py` | 5.2 |
| `curriculum/regulations/STATUS.md` | 5.4 |
| `IMPLEMENTATION_PLAN.md` | 5.5 |
| `tests/test_phase2.py`, `tests/test_instructor.py`, `tests/test_tools.py` | the tests below |

## Testing approach

Before any change: the full suite passes (221 tests, 1 skip, October 22, 2026). Run it again after each part.

New unit tests:

- **T1, the provider flag** (`tests/test_phase2.py`). Write a temporary `config.json` with `"provider": "claude_code"`, the `mock` and `claude_code` providers, and the stub paths from `tests/test_phase3.py`.
  - Without a flag, `Course(config_path)` uses `claude_code`.
  - With `provider="mock"`, it uses `mock`.
  - With `provider="nosuch"`, it raises `LLMError` with the list of names.
- **T2, the origin check** (`tests/test_instructor.py`, with its `serving()` helper).
  - A POST to `/api/author/save` with `Origin: http://evil.example` gets 403, and the lesson file and `STATUS.md` do not change.
  - The same POST with `Origin: http://127.0.0.1:<port>` saves.
  - A POST with no `Origin` header saves.
- **T3, the link checker** (`tests/test_tools.py`). Patch `urllib.request.urlopen` to raise `TimeoutError`. `probe()` returns status 0 and a reason, and does not raise.

Manual checks, done by me:

- **M1, a new instructor's path.** In a throwaway clone in my scratchpad, follow the new README word for word.
  - Steps: clone, branch, start on `claude_code` with the flag, vet one unit in the workspace, edit a fact row and the Status cell by hand, run both checks, then `git add` and `git commit` as the README says.
  - Then `git diff main --stat` must list only course material.
  - The commit is in the throwaway clone only. Nothing reaches your repo or the remote. I will not push.
- **M2, links.** A one-off script in my scratchpad checks that every relative link in `README.md`, `DEVELOPING.md`, and `docs/vetting-guide.html` points to a file that exists.
- **M3, stale text.** Search for "not authored", "7 units", and `--allow-incomplete` in the instructor steps.
- **M4, startup.**
  - `env -u ANTHROPIC_API_KEY python3 server.py --provider anthropic` prints the key note.
  - `--provider nosuch` prints one line and exits.
- **M5, the browser.** The readiness text in the shell and in the tree.

Checks I cannot do: I have no Anthropic API key in this environment. You, or an instructor with a key, run the `anthropic` path of M1 once, including one request to the authoring assistant.

## After the work: suggested next tests

1. **Pilot.** One instructor vets one chapter on the backend they have. Note each place where they stop or ask.
2. **Merge test.** Two branches each vet a different unit, then merge both into a scratch `main`. `STATUS.md` and the facts table must merge with no conflict.
3. **Windows.** If an instructor uses Windows, a first run of `python server.py --instructor` on both backends.

## Out of scope

- Why one chat answer took 91 s and 265k input tokens, against about 25 s on October 10.
- Leaving `.pytest_cache/` and the 13 MB of `docs/` out of the zip.
- Course tools on the `anthropic` backend, and a check of its web search.
- Restoring pending questions after a restart, and `questions/` files in the integrity check.
- A `Host` header check against DNS rebinding for the GET endpoints. These endpoints only read files. The origin check covers the writes.

## As built

Built October 22, 2026, Parts 1 to 5 as planned. Nothing is committed. Differences from the plan, and what the build found:

1. **The link check is not an instructor step.** A full run of `tools/check_links.py` reported 145 of 207 links as `FAIL`. Every failure was eCFR answering `429 Too Many Requests` after about 30 requests. The 62 links that were checked all worked, including all 31 faa.gov links. The README and the vetting guide now ask instructors to open each link they add or change once, in a browser. `DEVELOPING.md` and the vetting guide's maintainer steps keep the link check, with this caveat. The tool still has no back-off for 429.
2. **`questions/README.md` is new.** In M1, `git add curriculum reference questions mock` failed with "pathspec 'questions' did not match any files" and staged nothing. The folder exists only after a save in the Questions tab. The README in the folder makes the folder exist in every clone. No code reads it: the course reads only `questions/regulations/<unit>.md`.
3. **The vetting guide had "7 units" in its template.** Regenerating would not have fixed the count, so the template now uses the Foundational count it already computes.
4. **The build tools still read `provider` from `config.json`.** `tools/enhance_kb.py` and `tools/probe_chat.py` have no `--provider` flag. `DEVELOPING.md` says to set `claude_code` in a local copy for a build pass and not to commit it.
5. **The startup note** names `--provider claude_code` as the way to use a Claude plan. The page's own missing-key message in `llm_client.py` is unchanged and still names `config.json`.

Checks:

- Tests: 225 (1 skipped), up from 221. The four new tests (T1, T2, two for T3) fail on the old `server.py` and `tools/check_links.py`.
- Strict integrity check: 0 errors, 0 warnings. The regenerated vetting guide counts 8 Foundational files.
- M1: a throwaway clone with these changes, on the branch `vetting/test-instructor`. `server.py --instructor --provider claude_code` started on the Claude plan. A workspace save of 2.2 with "Yes, vetted" wrote `v2 vetted`. A hand edit set the facts and the status to `vetted`. The integrity check passed. The README's `git add` line then committed only the lesson and `STATUS.md`, and left a local `config.json` change out. The lesson for 2.2 came back in 15 s.
- M2: every relative link in `README.md`, `DEVELOPING.md`, and `docs/vetting-guide.html` resolves. The one exception is the placeholder `images/name.svg` inside a code example.
- M3: no "not authored", "7 units", or "Improving the tutor" remains in the docs.
- M4: `--provider nosuch` prints one usage error and exits with status 2. `--provider anthropic` without a key prints the note.
- M5: the page shows "Regulations area: not yet ready for the knowledge test". The "ready" text is checked in the code only, because it needs a fully mastered course.
- Not done: the `anthropic` path of M1, because there is no API key in the build environment.
