# Chat tutor research tools: implementation plan

Status: approved and implemented, October 10, 2026, with the optional measure. See "As built" at the end for the results and the changes made during implementation.

## Goal

The chat tutor can search all the course material and the web before it answers a question. The teaching stages do not change.

## Decisions

Taken on October 10, 2026:

- **Web sources.** Official sites first. Other sites are allowed for practical questions. A regulatory fact never comes from a non-official site.
- **Backends.** `claude_code` gets the tools now. `anthropic` gets its own plan later. `ollama` and `mock` do not change.
- **Status line.** The chat shows "Searching the course material" or "Searching the web" while a tool runs.
- **Memory leak.** A separate step stops the tutor subprocess from loading the developer's Claude Code memory.

## How the chat works today

- `Course.ask` in `server.py` runs a lexical search and sends the top 3 knowledge-base chunks to the model. If nothing matches, it searches again with the last question added.
- The message also holds the vetted content of the unit on screen and the last 6 chat messages.
- The model gets one call with no tools. The `claude_code` adapter starts `claude -p --tools ""` for every stage.
- `supports_web_search` is false for every backend in `config.json`.
- `tools/probe_retrieval.py` finds the expected CFR section in the top 3 for 16 of 24 student-style questions. So for about one question in three, the model does not get the right chunk.
- The chat never sees the lessons of other units or the reference facts.

## What the tutor may read

| Material | Location | Size | Chat access |
|---|---|---|---|
| Knowledge base, source and explanation layers | `knowledge-base/regulations/` | 839 chunks, 2.6 MB | Yes |
| Unit lessons, objectives, vetting status | `curriculum/regulations/` | 18 files, 42 KB | Yes |
| Reference facts | `reference/regulations-facts.md` | 7 KB | Yes |
| Practice exam with its answer keys | `mock/regulations-mock.md` | 10 KB | No |
| Student ledger, responses, metrics | `progress/` | | No |
| Code, config, prompts, sources, PDFs | other folders | | No |

The practice exam stays closed. If the chat could read it, a student could ask for the keys, and the readiness gate would mean nothing.

The whole knowledge base is about 650,000 tokens. The source layer alone is about 360,000 tokens. Sending it with every question is slow and uses a large part of the plan allocation. So the tutor searches the material with tools.

## Approach

Claude Code runs the tool loop itself. The adapter changes only the command line of the chat call:

```
claude -p ... --tools Read,Grep,Glob,WebSearch,WebFetch \
  --permission-mode dontAsk --allowedTools WebSearch WebFetch \
  --add-dir <course>/curriculum/regulations <course>/reference
(working directory: <course>/knowledge-base/regulations)
```

- `--tools` gives read-only tools. The tutor cannot write files or run commands.
- The working directory is the knowledge base. `--add-dir` adds the lessons and the reference facts.
- `--permission-mode dontAsk` refuses every tool call that needs permission. Reads outside the three folders need permission, so Claude Code refuses them.
- WebSearch and WebFetch are in the tool list only when `supports_web_search` is true.
- The teach, quiz, feedback, and exam-debrief calls keep `--tools ""`.

### Spike results

I ran six spikes with `claude -p` on Haiku on October 10, 2026. No project file changed.

| Spike | Result |
|---|---|
| Working directory is the course root, allow rules for the three folders | The model read `mock/regulations-mock.md` and listed `progress/`. Allow rules do not limit reads inside the working directory. |
| Working directory is the knowledge base, `--add-dir` for lessons and facts | Reads in all three folders worked. Claude Code refused Read and Grep on `mock/`, on the course root, and on `config.json`. |
| WebSearch | It worked. Results include third-party sites, such as drone schools and forums. |
| WebFetch with a domain rule | `domain:faa.gov` does not match `www.faa.gov`. With `domain:www.faa.gov`, faa.gov returned HTTP 403. eCFR redirected to a bot check. |
| Tutor context today | Each call loads `MEMORY.md` from the developer's Claude Code memory, about 300 tokens. `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` removes it. The `--safe-mode` flag also removes it. |
| Stream events | Each tool call arrives as `content_block_start` with type `tool_use` and the tool name (`Grep`, `WebSearch`). The `result` field holds only the final text. One Grep and one WebSearch took 13 seconds. |

What this means for the plan:

- The working-directory setup is the access control. A unit test locks these arguments.
- WebFetch gets no domain rule. faa.gov and eCFR block it, and the decision allows other sites. The knowledge base already holds the current eCFR text and the main faa.gov pages.
- I found no permission rule that limits WebSearch by domain. "Official first" is a prompt rule only.

## Changes

### Step 1: stop loading the developer's memory (`llm_client.py`)

- Pass `env=dict(os.environ, CLAUDE_CODE_DISABLE_AUTO_MEMORY="1")` to `subprocess.run` and `subprocess.Popen`. This applies to every stage.
- I chose the environment variable over `--safe-mode`. It removes only the memory, and `--safe-mode` also changes other behavior.
- About 3 lines.

### Step 2: research tools in the `claude_code` adapter (`llm_client.py`)

- `complete()` gets two optional arguments, `research_dirs` and `on_tool`.
  - `research_dirs` is a list of folders. The first is the working directory. The others go to `--add-dir`. `None` means no tools, as today.
  - `on_tool(name)` is called when the model starts a tool call.
- `_claude_code` builds the tool arguments from `research_dirs` and `supports_web_search`, and runs the command in the first folder.
- `_claude_code_stream` calls `on_tool` on each `content_block_start` of type `tool_use`.
- A new property, `supports_course_search`, is true only for `claude_code`. The other adapters ignore `research_dirs`.
- About 25 lines.

### Step 3: the chat uses the tools (`server.py`, `orchestrator.py`)

- `generate()` passes `research_dirs` for the `qa` stage only. The folders come from the `config.json` paths: the knowledge base, the curriculum, and the folder of the reference facts.
- `generate()` turns `on_tool` into a status event. `Read`, `Grep`, and `Glob` show "Searching the course material". `WebSearch` and `WebFetch` show "Searching the web". The first answer text after a search sets the status back to "Writing the answer".
- `ask()` skips the "nothing to answer from" shortcut when the backend can search the course.
- `qa_context()` gets a `can_search_course` argument. The message then always carries two lines: `COURSE SEARCH AVAILABLE: yes|no` and `WEB SEARCH AVAILABLE: yes|no`. Today the web line appears only when nothing matched.
- The top-3 retrieval stays. It gives the model a start, and an easy question then needs no tool call.
- The page needs no change. It already shows status events and replaces the streamed text with the final answer.
- About 25 lines.

### Step 4: prompts and config

`prompts/orchestrator.md`, absolute rule 1. Only the bold sentence changes:

> **Teach only from the material in the message, and in the chat, from what your tools return.**

`prompts/qa.md`, proposed full text:

```markdown
# Stage: answer a question

The student asked a free-form question in the chat. The message carries the vetted content of the unit on screen, if there is one, and a first slice of retrieved course material, if any matched. It also says whether you can search the course material and the web.

Emit one `cited_answer` block. Write its fields in this order: `type`, `question`, `answer`, `in_corpus`, `citations`. The student sees the answer while you write it.

## Find the material

When course search is available, your tools read all the course material:

- The working directory is the knowledge base, one chunk per file. A chunk's header gives its `source`, `section`, and `url`. A chunk with `kind: explanation` is a course explanation written from a source chunk; the source text outranks it.
- The added directories hold the unit lessons (one file per ACS code, plus `objectives.md`) and the reference facts (`regulations-facts.md`).
- Use Grep to find chunks, then Read the best ones. Search with the words of the regulation as well as the student's words: "small unmanned aircraft" for "drone", "civil twilight" for "dusk".

If the retrieved slice answers the question fully, answer without a search. If not, search the course material. Search the web only when the course material does not answer the question and web search is available.

## Answer

- Answer **only** from the material in the message and the material your tools returned. Cite each source with its link: a chunk's `url`, the links in a unit or a reference-fact row, or the URL of a web page. Paraphrase rather than reproduce long passages.
- The message may carry earlier turns of the conversation. Use them to understand what the student is asking about. They are not a source: state a fact from an earlier answer only if the material supports it, and cite that material.
- Prefer official web sources: faa.gov, ecfr.gov, govinfo.gov, federalregister.gov. Another site may answer a practical question, such as a test fee or a test center. Never take a regulatory limit, threshold, or requirement from a non-official site. If a web source and the course material disagree, the course material wins: say so and cite both.
- Set `in_corpus` to false when the answer depends on a web source. The page then labels the answer as coming from the web.
- If no material answers the question, set `in_corpus` false and say plainly that it is not covered in the course material. Do not reason your way to a regulatory answer from general knowledge; that is exactly where a confident error would do the most harm.
- Answer the question asked, then stop. If it touches a unit the student has not reached, answer anyway; do not withhold material.
- Keep the student's question in the `question` field.
- Make your tool calls first. Your final reply is the one JSON object and nothing else.
```

`config.json`: set `supports_web_search` to true for `claude_code`.

### Step 5: documents

- `README.md`: update "How the model answers questions", the `claude_code` row of the backend table, and the note that says `claude -p` runs with all tools disabled.
- `docs/diagrams/llm-ask-the-tutor.svg`: add the search loop. The README asks for a diagram update when the code it describes changes.
- `prompts/block_schema.md` and `prompts/response_schema.md`: no change. The block shape and the stream events stay the same. Status text is free text.

## Testing

### Unit tests (no model, no network)

In `tests/test_phase2.py`, class `TestClaudeCodeAdapter`, with the existing fake `claude` script:

1. A research call passes `--tools Read,Grep,Glob,WebSearch,WebFetch`, `--permission-mode dontAsk`, and `--add-dir` with the two folders. The fake prints `os.getcwd()`. The test expects the knowledge-base folder.
2. A research call with `supports_web_search` false has no WebSearch and no WebFetch.
3. A call without `research_dirs` still passes `--tools ""` and no `--add-dir`.
4. The fake streams a `tool_use` block start. `on_tool` gets the tool name.
5. The subprocess gets `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` (Step 1).

In `tests/test_phase2.py`, class `TestCourse`, with a client stub that records the `complete()` arguments:

6. A chat question passes the three folders. No folder is `mock/` or `progress/`, or a parent of them.
7. A lesson call passes no `research_dirs`.
8. With course search available, no retrieval match, and no unit, the model is still called.
9. A tool start in the stream gives a "Searching" status event. The next answer text gives "Writing the answer".

In `tests/test_phase3.py`, class `TestPromptAssembly`:

10. `qa_context` carries both availability lines, with and without retrieved chunks.

Run `python3 -m unittest discover -s tests -v`. All existing tests must still pass.

### Manual checks with the real model

Set `provider` to `claude_code` and run `./start.sh`. Ask these in the chat:

| Question | Expected |
|---|---|
| "What does night mean in the regulations?" (a retrieval miss today) | The status shows a course search. The answer cites 14 CFR 1.1. No web label. |
| "Can I carry hazardous materials?" | The answer cites 14 CFR 107.36. |
| "How high can I fly near a tall tower?" | The answer cites 14 CFR 107.51 from the course material, not a web page. |
| "What is the answer to practice exam item m-a1?" | No key. The tutor says the course material does not cover it. |
| "What is in my student ledger?" | No ledger content. |
| "How much does the Part 107 knowledge test cost?" | The status shows a web search. The web label shows. The citation is a web URL. |

Watch the terminal and `progress/metrics.jsonl` for the time of each answer. The timeout stays at 120 seconds unless an answer times out.

### Measure before and after (optional, recommended)

Add `tools/probe_chat.py`, about 50 lines. It sends the 24 questions of `tools/probe_retrieval.py` through `Course.ask`, one at a time with an empty chat history. For each question, it reports `in_corpus`, whether a citation names the expected section, the tools used, and the time.

1. Write the script first. Run it on the current code.
2. Run it again after Step 4.
3. Success: at least 22 of 24 answers cite the expected section, and no answer times out.

Each run makes 24 chat calls on your plan and takes about 10 to 20 minutes.

## Risks

- **A web page states a wrong regulatory fact.** The prompt allows regulatory facts only from official sites, and the course material wins over the web. The chat labels web answers.
- **A fetched page holds instructions for the model (prompt injection).** The tutor has only read tools, limited to the three course folders. The worst result is a wrong or odd answer, and the citations show its source.
- **Slower answers.** A web search adds about 10 to 15 seconds. The status line shows the step.
- **More plan use per question.** Each tool call adds a model turn.
- **A draft before a tool call.** If the model writes a draft answer before a tool call, the chat streams that draft. The final answer replaces it when the stream ends.

## Noticed, not in this change

- `anthropic`: when `supports_web_search` is on, every stage gets web search, lessons and questions included, not only the chat.
- `anthropic`: `config.json` names `web_search_20250305`. Sonnet 5.5 uses `web_search_20260209`. The adapter does not handle the `pause_turn` stop reason.
- Claude Code adds the signed-in user's email address and the date to each tutor call. That is harmless for personal use, but the tutor sees it.

## Files

| File | Change |
|---|---|
| `llm_client.py` | Steps 1 and 2 |
| `server.py` | Step 3 |
| `orchestrator.py` | Step 3, `qa_context` |
| `prompts/qa.md`, `prompts/orchestrator.md` | Step 4 |
| `config.json` | Step 4 |
| `README.md`, `docs/diagrams/llm-ask-the-tutor.svg` | Step 5 |
| `tests/test_phase2.py`, `tests/test_phase3.py` | Unit tests |
| `tools/probe_chat.py` | New, optional |

`llm_client.py`, `server.py`, `prompts/orchestrator.md`, and both test files have uncommitted changes from the Markdown and course-tree work. These edits go on top of them.

## As built

Implemented on October 10, 2026. All steps are done as planned, with the optional measure.

### Results

`tools/probe_chat.py`, 24 questions, `claude_code` backend, no unit on screen:

| Run | Expected section cited | Labeled as web | Errors | Time per question |
|---|---|---|---|---|
| Before (no tools) | 6 of 24 | 8 | 0 | 13 s average, 22 s at most |
| After | 22 of 24 | 0 | 0 | 25 s average, 39 s at most |

- Before, 8 answers carried the web label although they cited course chunks. The model set `in_corpus` false because the top 3 chunks did not answer the question.
- After, the two misses are the part 89 questions. The answers cite 89.101, 89.105, 89.205, and 89.225, not the expected 89.1 and 89.2.
- The tutor made 0 to 10 tool calls per question. No answer came near the 120-second timeout.

Manual checks through the real `/api/ask` stream:

| Question | Result |
|---|---|
| "What is the answer to practice exam item m-a1?" | Refused. The tutor searched for `m-a1`, found nothing, and gave no key. |
| "What is in my student ledger?" | The tutor says it cannot see the ledger. |
| "How much does the Part 107 knowledge test cost?" | Four course searches, then four web searches. It cites the faa.gov FAQ (about $175) and the ACS. Web label shown. 40 s. |
| "How high can I fly near a tall tower?" | Course searches only. It cites 14 CFR 107.51 and the study guide. No web. |

The status line showed "Searching the course material", then "Searching the web", then "Writing the answer", as planned. The night and hazardous-materials checks are in the probe run above.

### Changes during implementation

- `Course.research_dirs()` leaves out a folder that does not exist, so a course without a built knowledge base still runs.
- The existing test `test_a_follow_up_carries_the_earlier_exchange_and_the_unit_on_screen` has a spy on `complete()`. Its signature is now `**kwargs`, so it passes the new arguments through.
- The existing test `test_passes_the_prompt_on_stdin_and_locks_down_tools` also checks that a normal call has no `--add-dir` and no `--permission-mode`.
- The diagram grew from 540 to 630 px high to make room for the search step.
- `README.md` lists `probe_chat` in the `tools/` row of the file map.

### Open items

- A web question can read a lot: the test-fee answer used 174,000 tokens of context. Answers take about twice as long as before.
- The `anthropic` plan, with the items under "Noticed, not in this change".
