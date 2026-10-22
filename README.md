# FAA Part 107 course

> **Draft. Not vetted.** The lessons, reference facts, and practice exam in this
> repository are drafts. No instructor has checked them against the regulations
> yet. Do not use this course to prepare for the FAA test until this notice is
> removed.

An adaptive, LLM-tutored course for the FAA Part 107 remote pilot knowledge test
(Unmanned Aircraft General). The tutor teaches from the regulations and FAA
guidance only, and every statement links to its source. The model teaches over
this material. It is not the authority on the rules.

**Scope.** The course covers Area of Operation I, Regulations, of the Airman
Certification Standards (FAA-S-ACS-10B): six tasks and 77 knowledge units.
Regulations is 15 to 25 percent of the 60-question test. The other four areas
(Airspace, Weather, Loading and Performance, Operations) are not in the course yet.

**What we ask of instructors.** Run the course on your own computer. Check the
lessons, the reference facts, and the practice exam against the source text. Fix
what is wrong, and send your changes back as a pull request. You do not need to
program. You need a terminal and a few git commands, which this guide gives in full.

This guide is for instructors. Developers start with [DEVELOPING.md](DEVELOPING.md).

## What you need

- Git, and a GitHub account for the pull request.
- Python 3.8 or newer. The course needs no other packages.
- A language model: your own Claude plan or your own Anthropic API key. See
  "Choose a backend".
- Chrome or Edge, if you want to speak your questions. The rest of the course
  works in any current browser.
- macOS or Linux. Windows is not tested yet; see "Start the course".

## Get the course

```bash
git clone https://github.com/Halimede-one/part-107-prep-course.git
cd part-107-prep-course
git switch -c vetting/your-name
```

Put your own name in the branch name. Do all your work on this branch. If you
have no write access to the repository, fork it on GitHub and clone your fork.

## Choose a backend

The tutor needs a language model. Use one of these two backends.

| | Your Claude plan | Your Anthropic API key |
|---|---|---|
| Backend name | `claude_code` | `anthropic` (the default) |
| You need | [Claude Code](https://code.claude.com/docs/en/quickstart), installed and signed in to your plan. Tested with version 2.1.235. | An API key from the Anthropic Console, set as `ANTHROPIC_API_KEY` in your shell. |
| Cost | Comes from your plan. | Billed to your key per token, a few cents for each lesson, answer, or edit request. |
| Start command | `./start.sh --instructor --provider claude_code` | `./start.sh --instructor` |
| The chat tutor | Searches the course material, and the web when the material does not cover a question. | Answers from the knowledge-base passages that match the question best. |

- Choose the backend with `--provider`. Do not change `provider` in
  `config.json`, because that change would go into your pull request.
- Do not keep `ANTHROPIC_API_KEY` in your shell profile if you use your Claude
  plan. Claude Code then bills the API key, not your plan.

On the Claude plan, the course runs Claude Code without access to your files.
Lessons and questions get no tools. The chat and the authoring assistant can read
only the course material. Your Claude Code settings, memory, and connectors do
not load.

## Start the course

```bash
./start.sh --instructor                          # with your API key
./start.sh --instructor --provider claude_code   # with your Claude plan
```

The course opens http://localhost:8107 in your browser. If no browser opens, open
that address yourself. Press Ctrl+C in the terminal to stop the course.

- If `./start.sh` reports a permission error, run `chmod +x start.sh` once.
- On Windows, start the course from its folder with `python server.py --instructor`,
  and add `--provider claude_code` for your Claude plan.
- `--instructor` adds the **Instructor** button. Without it, nobody can change
  the course material from the browser.

Expect these waits:

| Action | Usual wait |
|---|---|
| A lesson or a check question | 15 to 30 seconds |
| A diagram from the authoring assistant | 30 to 60 seconds |
| A chat answer | Up to 2 minutes when the tutor searches the course and the web |

The course keeps your progress as a student in the `progress/` folder. Git
ignores that folder. To start over, stop the course, delete `progress/`, and
start it again.

**Speaking a question.** With the microphone button beside Send, a student can
speak a question. The browser's own speech recognition turns it into text.
Chrome sends the audio to Google, Edge to Microsoft, and Safari to Apple. Safari
needs Siri or Dictation turned on in macOS settings. Firefox has no speech
recognition, so it shows no button. Brave shows the button but has no speech
service. The words go into the question box. Nothing goes to the tutor until the
student presses Send. The speech service needs the internet, also with the
offline `ollama` backend.

## How the course teaches

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
memory handle. Every unit with a Guided lesson offers all three. A unit's own
Fast-track or Foundational file comes first; without one, the tutor builds that
gear from the Guided lesson. The tutor's first Foundational lesson for a unit is
saved as that unit's file, marked as a draft for an instructor to review.

A student who knows the material answers two checks at Fast-track and moves on.
A miss moves only that unit one gear deeper. There the tutor teaches it a
different way, never the same explanation slower. At the deepest gear the unit
offers, the first miss brings a re-teach from a new angle. The second miss in a
row sets the unit aside. The course moves on and brings the unit back at the next
task boundary. Readiness stays closed until that unit is mastered.

## What the tutor teaches from

The tutor knows only what is in the course files. It never teaches from memory.
Five kinds of file decide what it says:

| File | What it holds | Where |
|---|---|---|
| Lesson files | One Guided lesson per unit, and optional Fast-track and Foundational lessons | `curriculum/regulations/` |
| Reference facts | The exact facts that the tutor's questions are keyed to, each with its source | `reference/regulations-facts.md` |
| Questions files | Per unit: your guidance for the tutor who writes the questions, and your own questions with their keys | `questions/regulations/` (edit them in the Questions tab) |
| Knowledge base | The regulations and FAA guidance in chunks, for the "Ask the tutor" panel | `knowledge-base/regulations/` (built by a script; do not edit by hand) |
| Practice exam | 20 fixed questions with their keys | `mock/regulations-mock.md` |

The prompts in `prompts/` set how the tutor teaches, not what is true. Change them
only together with the course maintainer.

## Vet a unit

`docs/vetting-guide.html` is your working aid. Open it in your browser. It has the
full procedure and a checklist with links to every unit's files, its source
chunks, its facts, and its open question. Its checkboxes stay in your browser
only. `STATUS.md` is the record.

1. Take the units the maintainer gave you. Read each unit's Notes in
   `curriculum/regulations/STATUS.md` first. A note names an open question.
2. Open the lesson in the workspace (see "Edit in the instructor workspace"), or
   in a text editor.
3. Check every fact in the lesson against the source text in the knowledge base:
   who the rule binds, what it requires, and every number, date, section
   citation, defined term, and diagram label. Check the worked example and the
   common misreading.
4. Check the unit's rows in `reference/regulations-facts.md` the same way. The
   tutor's questions are keyed to these rows.
5. Check the unit's Foundational file, if it has one. A tutor draft is a real
   lesson file that later students get.
6. Fix what is wrong, in the lesson and in the facts. A fix in the lesson alone
   is not enough.
7. Record the result, as the next section describes.

The CFR outranks the Advisory Circular and the study guide. If two sources
disagree, follow the CFR and write the conflict in the Notes column of
`STATUS.md`. Do not smooth it over in the lesson.

### Record the result

- **A lesson file, in the workspace.** Save it, and answer the question "Is this
  content vetted against the source text?" The save raises the file's version to
  N and writes `vN vetted` or `vN edited` into the unit's row in `STATUS.md`.
- **A lesson file, by hand.** Edit the file. Then set the unit's Gear cell in
  `STATUS.md` to `vN vetted`, where N is the `version:` line in the file.
- **The facts and the status, by hand.** The workspace does not change these
  cells. Write `vetted` in the Reference facts cell when you have checked every
  row for the unit. Set the Status cell to `vetted` when all the unit's lesson
  files and its facts are vetted. Add a dated note.
- **A problem you do not fix.** Write it in the unit's Notes cell, in this form:
  `<date>: <what is wrong>, per <section>. Not fixed.` Git records who wrote it.

A unit is vetted when all its lesson files and its reference facts are vetted.

### Find what needs work

- **The course tree.** A unit that students reach at Foundational, set aside, or
  mark "needs attention" is not getting through. Hover a unit to see which lesson
  file each speed uses.
- **The student record,** `progress/student-ledger.md`. Its Attempts table lists
  each miss by unit and speed.
- **The chat questions,** in `progress/responses.jsonl` (the lines with
  `"type": "question"`). A question that students ask often shows a gap in the lesson.
- **The check questions asked,** in `progress/questions.jsonl`, each with its key
  and rationale. Look here for a weak question or a wrong key.
- **Tutor drafts.** A Foundational lesson that the tutor wrote waits for your
  review. The course tree calls it "a draft the tutor wrote", and `STATUS.md`
  shows `tutor draft v1` in its Gear 3 column.
- **Open questions** in the Notes column of `STATUS.md`.

### Where each fix goes

| Problem | Fix it in | How |
|---|---|---|
| A fact is wrong or out of date | The lesson file and the reference facts | Correct both against the CFR. Questions are keyed to the reference facts, so a fix in the lesson alone is not enough. |
| A lesson does not get through | The lesson file for that speed | Rewrite the explanation or the worked example, or add a diagram. |
| Students keep missing a unit | Its Foundational file | Review the tutor draft, or write the file. |
| A quiz question is weak or wrong | The lesson file and the reference facts | The tutor writes a new question each time, from the lesson and the facts. Make the fact exact, and name the common misreading in the lesson. |
| The questions miss a point that matters | The unit's questions file | In the Questions tab, write guidance such as "make sure the student understands X", or write the question yourself. |
| A practice-exam item is wrong | `mock/regulations-mock.md` | Correct the row. Keep one keyed answer, distinct wrong options, a rationale, and a link. |
| A chat answer is wrong | Your pull request | Describe the question and the wrong answer. Chat answers come from the knowledge base, which the maintainer corrects or rebuilds. |

## Edit in the instructor workspace

1. Start the course with `--instructor` (see "Start the course"). The top bar
   then shows an **Instructor** button.
2. Click **Instructor** on any screen. The workspace opens on the unit and the
   speed on screen. To edit another file, pick a unit from the list and a tab:
   **Fast-track**, **Guided**, or **Foundational**. The line next to the tabs
   says what that file is: a lesson file with its version, a tutor draft, or no
   file yet.
3. Edit the file in the left column. The middle column shows it as a student
   sees it, with its images and its sources.
4. Or ask the assistant in the right column. Write what you want as you would to
   a colleague, for example: "This looks good, but can we add a diagram that
   shows how the authorized altitude applies in the worked example?" The
   assistant replies with a note on what it changed and a proposal for the whole
   file. The proposal shows in the middle column. Under the note, **Changes**
   lists each line that it adds or removes. You can also speak the request with
   the microphone button beside Send (see "Speaking a question").
5. Read the proposal. **Apply** puts it into the editor, and **Discard** drops
   it. Ask again to adjust it, for example "make the labels larger". You can also
   edit by hand at any time. Nothing is saved until you click Save.
6. Click **Save**. Write a short note on what changed, then answer the question
   "Is this content vetted against the source text?" Choose **Yes, vetted** only
   after you have checked every fact, number, and diagram label in the file
   against the source text. The save raises the file's version, records your
   answer in `STATUS.md`, and stores each new diagram as an image file in
   `curriculum/regulations/images/`.
7. Click **Try it as a student** to see the tutor teach the unit at that speed
   from your file.

The **Questions** tab, next to the speeds, edits the unit's check questions:

- **Guidance** goes to the tutor each time it writes a question on the unit, for
  example "make sure the student understands that LAANC covers controlled
  airspace only". The tutor makes its questions cover each point you name.
- **Add a question** writes your own question: the stem, three options with the
  answer marked, why the answer is right, and a source with its link. The tutor
  uses the "why" in its feedback. The course asks your questions first, in
  order, before the tutor writes its own. Each student sees each one once.
- **Save** checks every question and saves nothing while one has a problem. The
  problems show above the questions. A new question gets its id on save, and a
  deleted question's id is never used again. Do not use the `|` character.

Your own progress counts the questions you see as asked, so the Questions tab
has no **Try it as a student** button.

For a speed with no file, the workspace offers **Start from the Guided lesson**
and **Ask the tutor for a first version**. A unit with no Guided lesson cannot be
taught at all, so write that file first.

The assistant follows the tutor's rules: facts come only from the course material,
and every source is cited. When the material does not support a request, it says
so in its note. Check its work all the same: a diagram can carry a wrong label as
easily as a sentence can carry a wrong fact. The assistant sends only its changes,
so a small change is quick. A request for a new diagram takes about 30 to 60
seconds, most of it the model thinking before it writes.

### The speeds and their files

| Speed | File | Without the file |
|---|---|---|
| Fast-track | `<unit>.gear1.md` | The tutor shortens the Guided lesson. |
| Guided | `<unit>.md` | The unit cannot be taught. |
| Foundational | `<unit>.gear3.md` | The tutor builds it from the Guided lesson and saves its first version as a tutor draft. |

A tutor draft is a real lesson file that later students get. While it is a draft,
the tutor also receives the Guided lesson and the reference facts, and those win
on any conflict. Your first save of the file removes the draft mark.

Write a Foundational file when students keep missing a unit, or when the tutor
draft does not teach it well. Write a Fast-track file only when the tutor's short
version misses the point.

### Write a lesson file by hand

A lesson file is plain text in Markdown:

```
---
source: 14 CFR 107.51 | https://www.ecfr.gov/current/title-14/section-107.51
source: AC 107-2A | https://www.faa.gov/documentLibrary/media/Advisory_Circular/AC_107-2A.pdf
version: 3
---
Objective: know the altitude limit and its exception for structures.

The plain-language explanation, then the worked example, then the common misreading.
```

- Write one `source:` line for each source the lesson uses, with its link. For a
  CFR section, use its eCFR section link.
- The course writes the `version:` line and the `draft:` line. Leave them as they are.
- **Guided:** the objective, a plain-language explanation, a worked example, and
  the common misreading.
- **Fast-track:** the point in one or two sentences.
- **Foundational:** the point in numbered steps, each taught a different way (a
  picture, an analogy, or step-by-step reasoning), a memory handle, then the
  worked example step by step.
- Keep every number exactly as the source states it.
- Do not put review notes or status words in the file. The tutor reads the file
  as it is, so a note there reaches a student. Notes go in `STATUS.md`.
- Put an image in `curriculum/regulations/images/`, and show it in the lesson as
  `![What it shows](images/name.svg)`.

## Hand your work back

1. Run the integrity check:

   ```bash
   python3 tools/check_integrity.py
   ```

   It must report 0 errors. It finds a lesson without a source line, a fact
   without a link, and a broken exam item. It cannot check whether a fact is
   true; that part is yours. Open each link that you added or changed once in
   your browser. The maintainer checks all links before a release.

2. Start the course and try each unit you changed, at the speed you changed.

3. Commit the course material and push your branch:

   ```bash
   git add curriculum reference questions mock
   git commit -m "Vet 2.1 to 2.5"
   git push -u origin vetting/your-name
   ```

   The `git add` line takes only the course material: lessons, images,
   `STATUS.md`, facts, questions, and the practice exam. It leaves out
   `config.json` and `docs/vetting-guide.html`. Do not commit those two files.
   The maintainer regenerates the vetting guide after each merge.

4. Open a pull request on GitHub from your branch into `main`. List the units you
   vetted, and each problem that you found but did not fix.

## For developers

[DEVELOPING.md](DEVELOPING.md) covers the four backends in detail, the system
diagrams, the cost estimates, the tests, the content build, packaging, and the
file layout.
