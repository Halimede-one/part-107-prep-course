# Stage: quiz

Write one multiple-choice check question on the unit named in the message.

Emit one `question` block.

- Test the objective for this unit, not neighbouring material and not trivia.
- Three options, exactly one correct. Set `answer` to that option's id.
- **Anchor the key.** Where the question turns on a precise regulatory fact, the keyed answer must match the vetted facts supplied in the message exactly. If the facts do not settle it, ask about something they do settle.
- Distractors are the plausible wrong beliefs a real student holds, not obvious filler. Keep all three options similar in length and specificity.
- Vary the form across a unit: sometimes a direct question, sometimes a short operational scenario. If the message lists questions already asked, ask something different.
- `question_id` is short, lowercase, and unique within the unit, for example `k16-a2`.
- `rationale` explains why the key is right and why each distractor tempts. It is read by the tutor at the feedback stage, not by the student.
