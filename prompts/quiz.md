# Stage: quiz

Write one multiple-choice check question on the unit named in the message.

Emit one `question` block.

- Test the objective for this unit, not neighbouring material and not trivia.
- Three options, exactly one correct. Set `answer` to that option's id.
- **Anchor the key.** Where the question turns on a precise regulatory fact, the keyed answer must match the vetted facts supplied in the message exactly. If the facts do not settle it, ask about something they do settle.
- **Name the fact.** If the key rests on one of the vetted facts, set `fact` to its label, for example `F2`. The keyed option must then contain that fact's answer word for word. The course checks this.
- Distractors are the plausible wrong beliefs a real student holds, not obvious filler. Keep all three options similar in length and specificity.
- **Follow the instructor guidance.** If the message has INSTRUCTOR GUIDANCE, the unit's questions must cover each point it names. If no question already asked tests a point, test that point now.
- Vary the form across a unit: sometimes a direct question, sometimes a short operational scenario. If the message lists questions already asked, ask something different.
- `rationale` explains why the key is right and why each distractor tempts. It is read by the tutor at the feedback stage, not by the student.
