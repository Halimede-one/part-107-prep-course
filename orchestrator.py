"""The orchestrator: routing decisions in code, teaching decisions in the model.

The split is deliberate. Which unit comes next, which gear it is taught at, when
a unit counts as mastered, and when to downshift are all decisions that must be
reliable and testable, so they live here as pure functions over the ledger. How
to explain a point, what question to ask, and what misconception a wrong answer
implies are judgement calls, so they go to the model through the stage prompts.
"""

import os

from items import read_table

GEAR_NAMES = {1: "Fast-track", 2: "Guided", 3: "Foundational"}

# Consecutive misses at the deepest available gear before the student is offered
# an escape hatch and the unit is flagged for attention.
TERMINAL_CYCLES = 2


# ---- vetted content -----------------------------------------------------
def load_objectives(path):
    """unit code -> objective text, from the ACS spine."""
    objectives = {}
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            if not line.startswith("| UA.I."):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 2 and cells[0] not in objectives:
                objectives[cells[0]] = cells[1]
    return objectives


def parse_content(text):
    """Split a content file into its sources and body.

    Header format, one line per source, repeated as needed:

        ---
        source: 14 CFR 107.41 | https://www.ecfr.gov/current/title-14/part-107
        ---
    """
    sources, body = [], text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            for line in parts[1].strip().splitlines():
                if line.lower().startswith("source:"):
                    value = line.split(":", 1)[1].strip()
                    name, _, url = value.partition("|")
                    sources.append({"source": name.strip(), "url": url.strip()})
            body = parts[2].strip()
    return {"sources": sources, "body": body}


def load_facts(path):
    """Ground-truth regulatory facts, grouped by unit."""
    facts = {}
    for row in read_table(path, required=("unit", "fact")):
        facts.setdefault(row["unit"], []).append(row)
    return facts


# ---- routing decisions --------------------------------------------------
def task_of(unit):
    """The task letter of a unit code: UA.I.B.K16 -> B."""
    return unit.split(".")[2] if unit else None


def current_unit(led):
    """The first unit not yet mastered and not parked, in course order."""
    for unit in led.order:
        entry = led.units.get(unit, {})
        if led.mastery(unit) != "mastered" and not entry.get("parked"):
            return unit
    return None


# Mastered units re-checked at each task boundary, least recently attempted first.
REVIEW_PER_BOUNDARY = 3

# A review miss sends the unit back for re-teaching at this gear.
REVIEW_DEMOTION_GEAR = 2


def review_candidates(led, finished_task, limit=REVIEW_PER_BOUNDARY):
    """Mastered units from other tasks, ordered by how long ago they were last attempted.

    The task just finished is excluded: its units were mastered minutes ago,
    and the point of spaced review is distance.
    """
    candidates = [
        unit for unit in led.order
        if task_of(unit) != finished_task and led.mastery(unit) == "mastered"
    ]
    candidates.sort(key=led.last_attempt_index)
    return candidates[:limit]


END = "END"


def task_rank(task):
    """Course order of a task letter; END sorts after every task."""
    if task is None:
        return -1
    if task == END:
        return 99
    return ord(task) - ord("A")


def next_task(led):
    nxt = current_unit(led)
    return task_of(nxt) if nxt else END


def boundary_due(led):
    """Which task's boundary is due, or None.

    A boundary is due when the course is about to move forward into a later
    task than the one last worked, or past the last task (END). Backward moves
    do not count: a review miss sends the student back to an earlier unit,
    and that must not trigger another round of reviews. The caller records
    the new task on the ledger once it has processed the boundary, so each
    transition fires once.
    """
    if led.last_task is None or led.last_task == END:
        return None
    if task_rank(next_task(led)) > task_rank(led.last_task):
        return led.last_task
    return None


def terminal_cycles(led, unit, gear):
    """Consecutive recent misses on this unit at this gear."""
    count = 0
    for attempt in reversed(led.attempts):
        if attempt["unit"] != unit:
            continue
        if attempt["result"] == "correct" or attempt["gear"] != gear:
            break
        count += 1
    return count


def decide_after_answer(led, unit, gears_available, correct):
    """What happens after an answer is scored and recorded.

    Returns (action, gear):
      ("advance", None)      the unit is mastered, move on
      ("quiz", gear)         right, but not mastered yet, ask another
      ("remediate", gear)    wrong, re-teach at this gear (deeper if one exists)
      ("park", gear)         wrong again at the deepest gear, set the unit aside
    """
    entry = led.units.get(unit, {})
    gear = entry.get("current_gear", led.default_gear)

    if correct:
        if led.mastery(unit) == "mastered":
            return "advance", None
        return "quiz", gear

    deeper = [g for g in sorted(gears_available) if g > gear]
    if deeper:
        return "remediate", deeper[0]
    if terminal_cycles(led, unit, gear) >= TERMINAL_CYCLES:
        return "park", gear
    return "remediate", gear


def decide_after_review(led, unit, gears_available, correct):
    """A re-check of a mastered unit. Right keeps it mastered; wrong demotes it.

    Returns the gear the unit is sent back to, or None when nothing changes.
    The miss itself already broke the mastery streak in the ledger, so the
    unit becomes current again on its own; this only sets the gear.
    """
    if correct:
        return None
    return min(REVIEW_DEMOTION_GEAR, max(gears_available))


# ---- prompt assembly ----------------------------------------------------
class Orchestrator:
    def __init__(self, paths):
        self.paths = paths
        self.objectives = load_objectives(paths["objectives"])
        self.facts = load_facts(paths["reference"])
        self._prompts = {}

    def prompt(self, name):
        if name not in self._prompts:
            path = os.path.join(self.paths["prompts"], "%s.md" % name)
            with open(path, "r", encoding="utf-8") as handle:
                self._prompts[name] = handle.read()
        return self._prompts[name]

    def system(self, stage):
        return self.prompt("orchestrator") + "\n\n---\n\n" + self.prompt(stage)

    def content(self, unit, gear):
        """Vetted content for a unit at a gear, or None if it is not authored yet."""
        name = "%s.gear3.md" % unit if gear >= 3 else "%s.md" % unit
        path = os.path.join(self.paths["curriculum"], name)
        if not os.path.isfile(path):
            return None
        with open(path, "r", encoding="utf-8") as handle:
            return parse_content(handle.read())

    # ---- per-stage context ----------------------------------------------
    def _header(self, unit, gear):
        return [
            "UNIT: %s" % unit,
            "OBJECTIVE: %s" % self.objectives.get(unit, "(not listed)"),
            "GEAR: %d (%s)" % (gear, GEAR_NAMES.get(gear, "Guided")),
        ]

    def _material(self, unit, content):
        lines = ["", "VETTED CONTENT:", content["body"]]
        if content["sources"]:
            lines += ["", "CITATIONS AVAILABLE (use these exactly):"]
            lines += ["- %s | %s" % (s["source"], s["url"]) for s in content["sources"]]
        unit_facts = self.facts.get(unit, [])
        if unit_facts:
            lines += ["", "VETTED FACTS (ground truth; a keyed answer must match these):"]
            lines += [
                "- %s -> %s [%s | %s]" % (f.get("fact"), f.get("answer"), f.get("source"), f.get("link", ""))
                for f in unit_facts
            ]
        return lines

    def teach_context(self, unit, gear, content, chosen=False):
        lines = self._header(unit, gear)
        if chosen:
            lines.append(
                "SITUATION: the student picked this unit and this gear from the course tree, "
                "to review it or to get ahead. Teach it at the named gear as a fresh pass."
            )
        return "\n".join(lines + self._material(unit, content))

    def remediate_context(self, unit, gear, content, misconception=None, returning=False):
        lines = self._header(unit, gear)
        if returning:
            lines.append(
                "SITUATION: this unit was set aside earlier after repeated misses, and the "
                "student is returning to it now. Take a fresh angle; do not reopen with "
                "what failed before."
            )
        else:
            lines.append("SITUATION: the student just missed this unit.")
        if misconception:
            lines.append("THEIR LIKELY MISCONCEPTION: %s" % misconception)
        return "\n".join(lines + self._material(unit, content))

    def quiz_context(self, unit, gear, content, already_asked=(), review=False):
        lines = self._header(unit, gear)
        if review:
            lines.append(
                "SITUATION: spaced review. The student mastered this unit earlier; ask one "
                "question that checks the knowledge still holds. No lesson precedes it."
            )
        if already_asked:
            lines.append("ALREADY ASKED (ask something different): %s" % ", ".join(already_asked))
        return "\n".join(lines + self._material(unit, content))

    def feedback_context(self, unit, gear, content, question, selected, correct, outcome=None):
        options = "; ".join("%s. %s" % (o["id"], o["text"]) for o in question.get("options", []))
        lines = self._header(unit, gear) + [
            "",
            "QUESTION ASKED: %s" % question.get("stem", ""),
            "OPTIONS: %s" % options,
            "KEYED ANSWER: %s" % question.get("answer", ""),
            "WHY: %s" % question.get("rationale", ""),
            "STUDENT CHOSE: %s" % selected,
            "RESULT: %s" % ("correct" if correct else "incorrect"),
        ]
        if outcome == "park":
            lines.append(
                "WHAT HAPPENS NEXT: this unit is being set aside after repeated misses at the "
                "deepest gear. The course moves on and brings it back later. Say this plainly, "
                "give the single most useful mental handle for the point, and remind them "
                "the ask box takes direct questions at any time."
            )
        elif outcome == "demote":
            lines.append(
                "WHAT HAPPENS NEXT: this was a review check on a unit they had mastered, and "
                "they missed it. The unit comes back for re-teaching. Say so without drama."
            )
        elif outcome == "review_ok":
            lines.append("WHAT HAPPENS NEXT: review check passed; the unit stays mastered. Keep it brief.")
        return "\n".join(lines + self._material(unit, content))

    def mock_gate_context(self, result, ready):
        lines = [
            "PRACTICE EXAM RESULT: %d of %d correct (%s percent). Pass mark %d percent. %s."
            % (result["score"], result["total"], result["percent"], result["pass_mark"],
               "Passed" if result["passed"] else "Not passed"),
            "",
            "BY TASK:",
        ]
        lines += ["- Task %s: %d of %d" % (t["task"], t["correct"], t["total"]) for t in result["by_task"]]
        missed_units = sorted({m["unit"] for m in result["missed"]})
        lines += ["", "MISSED UNITS (with the objective each one tests):"]
        lines += ["- %s: %s" % (u, self.objectives.get(u, "")) for u in missed_units] or ["- none"]
        lines += [
            "",
            "READINESS STATUS: %s" % ("ready to schedule the real exam" if ready["ready"] else "not yet"),
        ]
        if ready["reasons"]:
            lines += ["- " + r for r in ready["reasons"]]
        lines += ["- practice exam passes so far: %d of %d needed" % (ready["passes"], ready["passes_needed"])]
        return "\n".join(lines)

    def qa_context(self, question, chunks, can_search, unit=None, content=None, history=(), can_search_course=False):
        """The chat's message: earlier turns, the question, which searches the tutor
        can run, the unit on screen, and the retrieved chunks. Earlier turns are
        context only, never a source."""
        lines = []
        if history:
            lines.append("EARLIER IN THIS CONVERSATION (what the student means; not a source of facts):")
            lines += ["%s: %s" % (m["role"].upper(), m["text"]) for m in history]
            lines.append("")
        lines += [
            "STUDENT QUESTION: %s" % question,
            "COURSE SEARCH AVAILABLE: %s" % ("yes" if can_search_course else "no"),
            "WEB SEARCH AVAILABLE: %s" % ("yes" if can_search else "no"),
        ]
        if content is not None:
            lines += ["", "THE UNIT ON SCREEN (course material):"] + self._header(unit, 2)[:2]
            lines += self._material(unit, content)
        if not chunks:
            lines += ["", "RETRIEVED MATERIAL: none. Nothing in the knowledge base matched."]
            return "\n".join(lines)
        ordered = sorted(chunks, key=lambda c: 0 if c.get("kind", "source") == "source" else 1)
        material = "\n\n".join(
            "[%s | %s | %s | %s]\n%s" % (
                "SOURCE TEXT" if c.get("kind", "source") == "source" else "COURSE EXPLANATION, derived from the source and not the regulation text",
                c["source"], c["section"], c["url"], c["text"])
            for c in ordered
        )
        lines += [
            "",
            "RETRIEVED MATERIAL (source text outranks course explanations on any conflict):",
            material,
        ]
        return "\n".join(lines)
