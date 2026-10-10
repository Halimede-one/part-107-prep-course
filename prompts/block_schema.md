# Block schema

The content blocks the tutor model emits. The shell renders these; the model never writes markup. Each block is a JSON object with a `type`.

Shell-owned elements (the intake step, the chat panel, and the course map) are not blocks. They are part of the fixed shell and are specified in the implementation plan, not here.

## Common fields

- `unit`: the ACS code the block concerns, for example `"UA.I.B.K16"`. Present on lesson, question, and feedback; optional on cited_answer.
- `gear`: `1`, `2`, or `3`, the current gear. Rendered as a tag. Present on lesson, question, and feedback; optional on cited_answer.
- `citations`: an array of `{ "source": string, "url": string }`. Required on any block that states a fact (lesson, feedback, cited_answer). The shell renders each entry as a link.
- `actions`: optional array of `{ "id": string, "label": string }`. If omitted, the shell supplies a default Continue on lesson and feedback.

## Block types

### lesson

```json
{
  "type": "lesson",
  "unit": "UA.I.B.K16",
  "gear": 2,
  "title": "Prior authorization in controlled airspace",
  "body": "Operating in controlled airspace under Part 107 requires prior authorization from ATC.\n\nBelow controlled airspace you may fly without it, but entering Class B, C, D, or surface Class E needs authorization first. The common automated method is LAANC.",
  "citations": [
    { "source": "14 CFR 107.41", "url": "https://www.ecfr.gov/current/title-14/part-107" }
  ]
}
```

### question

The tutor emits `answer` and `rationale`; the server records them, strips them, and sends the rest to the shell. So the key exists for scoring but never reaches the browser, and the client only ever reports the option the student selected.

A vetted key from the items table wins over the tutor's declared `answer` when one exists. Either way scoring is a comparison on the server, never a judgement call at feedback time.

```json
{
  "type": "question",
  "unit": "UA.I.B.K16",
  "gear": 2,
  "question_id": "q-k16-1",
  "stem": "Before operating in Class C airspace, what is required?",
  "options": [
    { "id": "A", "text": "Nothing, as long as you stay below 400 feet" },
    { "id": "B", "text": "Prior authorization, for example through LAANC" },
    { "id": "C", "text": "A verbal call to the control tower" }
  ],
  "answer": "B",
  "rationale": "Server-only. Why B is right and why the distractors tempt."
}
```

### feedback

```json
{
  "type": "feedback",
  "unit": "UA.I.B.K16",
  "gear": 2,
  "question_id": "q-k16-1",
  "correct": true,
  "correct_option": "B",
  "message": "Correct. Operating in controlled airspace (Class B, C, D, or surface Class E) requires prior authorization. LAANC is the common automated method.",
  "citations": [
    { "source": "14 CFR 107.41", "url": "https://www.ecfr.gov/current/title-14/part-107" }
  ]
}
```

### cited_answer

The answer to a free-form question from the chat panel. The server streams the `answer` text to the chat while the model writes it, so the fields come in the order shown. `in_corpus` is `false` when the answer was not found in the course material; a web fallback carries citations, and the shell labels it as web sources.

```json
{
  "type": "cited_answer",
  "question": "Can I fly at night under Part 107?",
  "answer": "Yes. Since the 2021 rule update, night operations are allowed under Part 107 if the aircraft has anti-collision lighting visible for at least 3 statute miles and the remote pilot has completed the updated training.",
  "in_corpus": true,
  "citations": [
    { "source": "14 CFR 107.29", "url": "https://www.ecfr.gov/current/title-14/part-107" }
  ]
}
```

### question, practice-exam form

The same question block with `mock: true`, a `position` and `total`, and `time_limit_seconds` for the whole attempt. No feedback follows an exam question; the shell posts a `mock_answer` and the next question arrives. A `review: true` flag on an ordinary question marks a spaced-review check at a task boundary.

### mock_result

Built by the server after an attempt, with the numbers decided by lookup scoring and `debrief` written by the tutor from the `mock_gate` stage. `readiness` is computed from the ledger and is the only place the course says whether the student is ready.

```json
{
  "type": "mock_result",
  "score": 17, "total": 20, "percent": 85.0, "passed": true, "pass_mark": 85,
  "by_task": [{ "task": "A", "correct": 2, "total": 2 }],
  "missed_units": ["UA.I.B.K21c"],
  "debrief": "What the score means, what to revisit, and the readiness status as given.",
  "citations": [],
  "readiness": { "ready": false, "reasons": ["3 units not yet mastered", "1 of 2 passing practice exams"], "passes": 1, "passes_needed": 2, "attempts": 1, "best_percent": 85.0, "pass_mark": 85 }
}
```

### debrief

Emitted by the tutor for the `mock_gate` stage only; the server folds its `body` into `mock_result`.

### error

Emitted by the server, not the model, when the tutor cannot be reached (for example no API key, or the local model is not running). The shell renders the message and offers to retry.

```json
{
  "type": "error",
  "message": "No API key found. Set ANTHROPIC_API_KEY in your environment, or set \"provider\" to \"ollama\" in config.json to run locally."
}
```

## Notes

- The mock provider's canned blocks are test scaffolding, not authoritative course content. Verified content and links arrive in Phase 4.
- The shell renders block text as plain paragraphs (split on blank lines). It does not execute markup from a block.
