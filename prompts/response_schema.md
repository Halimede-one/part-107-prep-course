# Response schema

The payloads the shell posts back. In Phase 1 they are logged in the page (the "sent" panel) so their shape can be verified without a server. In Phase 2 the server receives them, writes them to files, and scores answers by lookup against the question bank.

## Common field

- `timestamp`: an ISO 8601 string.

## Payload types

### answer

Posted when the student submits a question block. The server scores `selected_option` against the keyed answer.

```json
{
  "type": "answer",
  "question_id": "q-k16-1",
  "unit": "UA.I.B.K16",
  "selected_option": "B",
  "timestamp": "2026-07-16T18:30:00.000Z"
}
```

### question

Posted to `/api/ask` when the student sends a message in the chat panel. `context_unit` is the unit on screen; its vetted content is part of the material the tutor answers from.

```json
{
  "type": "question",
  "text": "Can I fly at night under Part 107?",
  "context_unit": "UA.I.B.K16",
  "timestamp": "2026-07-16T18:31:00.000Z"
}
```

The reply streams as one JSON object per line (see Streaming below), ending with `{"done": true, "message": {...}, "meta": {...}}` with the final chat message and the model's name and context use, or `{"error": "..."}`. `GET /api/chat` returns the conversation so far, so a reload shows it again. The chat is paused while a practice exam is in progress.

### intake

Posted once at session start when the student picks a starting level. Sets the session default gear.

```json
{
  "type": "intake",
  "default_gear": 1,
  "timestamp": "2026-07-16T18:29:00.000Z"
}
```

### advance

Posted when the student continues past a lesson or feedback block.

```json
{
  "type": "advance",
  "unit": "UA.I.B.K16",
  "timestamp": "2026-07-16T18:30:30.000Z"
}
```

### mock_start, mock_answer, mock_submit

`mock_start` begins a practice-exam attempt. `mock_answer` carries one answer in the same shape as `answer` (plus `unit`); the server records it silently and returns the next question or the result. `mock_submit` ends the attempt early, for example when the timer runs out; unanswered items score as wrong.

```json
{ "type": "mock_start", "timestamp": "2026-10-09T22:00:00.000Z" }
{ "type": "mock_answer", "question_id": "m-7", "unit": "UA.I.B.K21c", "selected_option": "A", "timestamp": "..." }
{ "type": "mock_submit", "timestamp": "..." }
```

## Streaming

`/api/ask` always streams, and `/api/respond` streams when the request carries `Accept: application/x-ndjson`; without it, `/api/respond` returns the block as plain JSON. A stream is one JSON object per line:

- `{"start": {"stage", "status", "model", "block"}}` when a model call begins. `status` is what the indicator says, and `block` holds the parts already decided: the unit and gear, a feedback result and its correct option, or an exam score.
- `{"status": "..."}` when the indicator text changes, for example once a question's stem is written.
- `{"delta": "...", "field": "..."}` for each piece of a text field as the model writes it. Only the fields the student sees stream; a question's key and rationale never do.
- `{"done": true, "block": {...}}` with the finished block, or `{"error": "..."}`.

A response with no model call, such as a practice-exam question, sends only the final line.

## Instructor mode

Only when the course starts with `--instructor`; otherwise these paths answer 404. The page names a unit and a gear, never a file path, and the server refuses a unit that is not in `objectives.md` or a gear other than 1, 2, or 3.

- `GET /api/author?unit=UA.I.B.K16&gear=3`: the lesson file as the editor shows it (the source lines and the body), the Guided lesson, each gear's file version and draft mark, and the unit's `STATUS.md` row.
- `POST /api/author/ask` with `{"unit", "gear", "text", "request", "history"}`: `text` is the editor's content with unsaved changes, and `history` holds the earlier `{"role", "text"}` turns. The reply streams like the chat; the stage is `author`, its fields `note` and `text`, and the final line is `{"done": true, "note", "text", "diff"}`.
- `POST /api/author/save` with `{"unit", "gear", "text", "note", "vetted"}`: saves the file and returns `{"saved": true, "version", "images", "warnings", "file"}`, or `{"error"}` for a drawing that could run code.

## Notes

- Scoring is deterministic and server-side. The client never decides correctness; it only reports the selected option.
- In Phase 1 the four posting paths are stubbed in `ui/app.js` behind a single `api.post` function, which is the only seam the Phase 2 server replaces.
