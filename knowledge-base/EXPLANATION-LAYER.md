# The explanation layer

A guide to the second layer of the knowledge base: what it is, how it is made, how the tutor uses it, how to vet it, and how to keep it current.

## What it is

The knowledge base in `regulations/` has two kinds of chunk, told apart by the `kind` field in each file's header.

- **Source chunks** (`kind: source`) hold text cut mechanically from the documents by `tools/build_kb.py`. No model wrote any of it. They are the ground truth.
- **Explanation chunks** (`kind: explanation`), also called companions, are written by the configured model from one source chunk at a time. Each one restates its chunk in plain language, adds one worked scenario, and names the misreading that trips people up. It carries the same citation as its source chunk and names that chunk in `derived_from`.

The layer exists for two reasons. Students ask in everyday words ("how high can I fly") while the regulation speaks in its own ("altitude above ground level"), and the lexical retriever matches words. A companion bridges the vocabulary, so a question in plain words can reach the regulation it belongs to. And a companion gives the tutor a ready, grounded explanation to teach from, instead of inventing one from recall.

The design rule behind it is principle 1 of the courseware principles: the model tutors, the sources hold the truth. A companion may restate, illustrate, and warn. It may not add a fact.

## What a companion looks like

A companion sits next to its source chunk with the suffix `.explained.md`:

```
14cfr107-107-41.md             source chunk
14cfr107-107-41.explained.md   its companion
```

Its header mirrors the source chunk's header, with two differences: `kind: explanation`, and `derived_from` naming the source file.

```
---
source: Explanation of 14 CFR Part 107, Small Unmanned Aircraft Systems (eCFR, current text)
section: § 107.41 Operation in certain airspace
url: https://www.ecfr.gov/current/title-14/section-107.41
page: 5
kind: explanation
derived_from: 14cfr107-107-41.md
---
```

The body has up to three parts, in this order: the plain-language explanation; a paragraph that starts with `Illustration:`; and a paragraph that starts with `Common misreading:`. The last two are left out when the chunk does not invite them.

## The rules the writer follows

The writer's instructions are in `prompts/enhance.md`. They are short, and a reviewer should know them:

1. Restate only what the chunk says. No regulatory fact, number, date, or requirement that is not in the chunk. A reference to a section the writer cannot see becomes "see that section".
2. Every number exact, as the chunk states it.
3. Explain, then illustrate, then name the misreading.
4. Plain language; acronyms expanded at first use.
5. A fragment, a broken table, or front matter is marked as such and kept short, or skipped.

The scenario in the illustration may invent its own details: a tower height, a repair bill, a date, a client. Those are not facts about the rule. The line a reviewer polices is between a scenario detail and a rule.

## How it is made

```bash
python3 tools/enhance_kb.py                 # every source chunk that has no companion
python3 tools/enhance_kb.py 14cfr107-107-41 # named chunks, by file stem
python3 tools/enhance_kb.py --redo <stem>   # rewrite a companion that exists
```

The tool uses the provider in `config.json`. The `claude_code` provider draws on the signed-in Claude plan, which is why it is the natural choice for this pass. Each chunk is one model call of about 10 to 30 seconds. The tool processes chunks one after another; to run several at once, start several copies with disjoint lists of stems. The October 2026 build ran four, and wrote 305 companions in about 40 minutes.

The tool reports three outcomes per chunk:

- `written`: the companion exists.
- `skipped (no teachable content)`: the writer judged the chunk to be front matter or a fragment. Eight chunks were skipped in the October 2026 build, all front matter.
- `no usable answer` or a Claude Code error: the model's answer was not parseable JSON, or the call timed out (120 seconds by default, in `config.json`). Run the tool again for that stem; a second attempt usually succeeds.

## Which sources have companions

The October 2026 build wrote companions for the CFR parts (107, 89, 48, 47, 3, and the referenced sections of parts 61, 91, and 99), the statute (49 U.S.C. 44809), AC 107-2A, and the FAA-G-8082-22 study guide. These are the sources the tutor should quote for a rule, and the regulation is the layer that most needs a plain-language bridge.

No companions were written for 14 CFR part 1 (a long list of definitions, mostly for manned aviation), the ACS (a map, not an answer source), the sample questions (questions without an answer key), the handbook chapters, the AIM, or the faa.gov pages (already plain language). Running the tool with no arguments covers them; expect about 230 model calls.

## How the tutor uses it

Retrieval returns both kinds of chunk. For a free-form question, the server passes the matching chunks to the tutor sorted with source chunks first, each labeled `SOURCE TEXT` or `COURSE EXPLANATION, derived from the source and not the regulation text`, under a line that says source text outranks course explanations on any conflict. A companion cites the same link as its source chunk, so an answer drawn from a companion still links to the regulation.

A companion never reaches the student verbatim. The tutor writes its own lesson, answer, or feedback from the material in the message, under the orchestrator's rule that every factual statement is cited.

## How to vet the layer

Vetting is the human step that principle 20 requires before the layer is trusted. The question for each companion is single: does it state anything about the rule that the source chunk does not? Three things to look for:

1. An added number, date, or threshold. The most common and the most harmful.
2. A filled-in cross-reference. The chunk says "in accordance with § 107.120(a)"; the companion explains what 107.120(a) requires. The writer should have said "see that section".
3. A wrong scope. A long section is split into parts (`-p1`, `-p2`); a companion written from part 2 can describe the section as if part 2 were all of it.

`tools/check_companions.py` makes the first check fast. It lists every number in a companion that its source chunk does not contain, with the sentence it sits in:

```bash
python3 tools/check_companions.py             # every companion
python3 tools/check_companions.py 14cfr107    # one source
python3 tools/check_companions.py --quiet     # the count only
```

Most flags are scenario details in the illustration. Read the sentence; if the number is part of the scenario, move on. If it is stated as a rule, the companion has added a fact.

The remedy for any added fact is the same: delete the companion and write it again.

```bash
python3 tools/enhance_kb.py --redo 14cfr107-107-41
```

Read the new one before accepting it. The October 2026 build checked 62 flagged companions out of 305 this way and found scenario details in the 29 that were read; the other 33 are listed by the tool and were not read.

Record what was vetted in `BUILD.md`, not in the chunk files. Anything in a chunk file reaches the model.

## Keeping it current

A companion is tied to the text of its source chunk on the day it was written. Three events can make it stale.

- **The source changes.** After `tools/fetch_sources.py --redo` and a rebuild, a chunk whose text changed keeps its file name, so its companion survives and is now out of date. Rewrite the companions of every source that changed: `python3 tools/enhance_kb.py --redo <stems>`. The eCFR version history (`https://www.ecfr.gov/api/versioner/v1/versions/title-14.json?part=107`) says which sections changed and when.
- **The chunking changes.** A new heading regex produces new file names. The old companions become orphans, which `tools/check_integrity.py` reports as `derived_from ... is not a chunk`. Delete them along with the old source chunks before rebuilding (`rm regulations/<id>-*.md`, minding that `14cfr1-` is a prefix of `14cfr107-`).
- **A source's link changes.** The companion carries a copy of the source chunk's `url`. After a rebuild that changes links, either rewrite the companions or set each companion's `url` line to its source chunk's; the integrity check does not compare the two.

`tools/check_integrity.py` verifies the structure of the layer on every run: each companion has a source, a section, a link, a known kind, and a `derived_from` that names an existing chunk. It cannot verify that a companion is true. That is the vetting step above.

## Known limits

- The illustration may invent scenario numbers. This is by design and is the main source of noise in the number check.
- A companion's `section` heading is copied from its source chunk. For AC 107-2A that heading includes the body text that followed the heading on the same line, so it reads long.
- A companion written from one part of a split section sees only that part.
- A companion for front matter is usually skipped; where one was written, it describes the authority citation and is harmless.
- The retriever does not prefer a companion over any other chunk. A plain-words question still often lands on a faa.gov page or a sample question before the companion of the regulation; `tools/probe_retrieval.py` measures this.
