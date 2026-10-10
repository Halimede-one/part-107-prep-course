"""The practice exam and the readiness gate.

Everything here is deterministic. The items are fixed and human-vetted, scoring
is a lookup against the keyed answer, and readiness is computed from the ledger.
The model's only part is the debrief text, written after the numbers are in.
"""

import random

from orchestrator import task_of

PASS_MARK = 0.85
PASSES_NEEDED = 2
MINUTES_PER_ITEM = 2


def mock_items(items):
    """The items that form the practice exam: those with a stem and three options."""
    return {
        item_id: item for item_id, item in items.items()
        if item.get("stem") and all(item.get(k) for k in ("a", "b", "c"))
    }


def new_attempt(items, seed=None):
    """A fresh attempt: the same vetted items, in a shuffled order."""
    order = sorted(mock_items(items))
    random.Random(seed).shuffle(order)
    return {"order": order, "index": 0, "answers": {}}


def question_block(items, attempt, time_limit_seconds):
    """The next item as a question block, without its key."""
    item_id = attempt["order"][attempt["index"]]
    item = items[item_id]
    return {
        "type": "question",
        "mock": True,
        "position": attempt["index"] + 1,
        "total": len(attempt["order"]),
        "time_limit_seconds": time_limit_seconds,
        "unit": item["unit"],
        "question_id": item_id,
        "stem": item["stem"],
        "options": [
            {"id": "A", "text": item["a"]},
            {"id": "B", "text": item["b"]},
            {"id": "C", "text": item["c"]},
        ],
    }


def score_attempt(items, attempt):
    """Score an attempt. Unanswered items count as wrong."""
    total = len(attempt["order"])
    correct = 0
    missed = []
    by_task = {}
    for item_id in attempt["order"]:
        item = items[item_id]
        task = task_of(item["unit"])
        tally = by_task.setdefault(task, {"task": task, "correct": 0, "total": 0})
        tally["total"] += 1
        chosen = attempt["answers"].get(item_id, "")
        if chosen.strip().upper() == item["answer"].strip().upper():
            correct += 1
            tally["correct"] += 1
        else:
            missed.append({"unit": item["unit"], "item": item_id})
    percent = (100.0 * correct / total) if total else 0.0
    return {
        "score": correct,
        "total": total,
        "percent": round(percent, 1),
        "passed": total > 0 and (correct / total) >= PASS_MARK,
        "pass_mark": int(PASS_MARK * 100),
        "by_task": [by_task[k] for k in sorted(by_task)],
        "missed": missed,
    }


def readiness(led, mock_attempts, passes_needed=PASSES_NEEDED):
    """Whether the student meets the bar to schedule the real exam, and why not if not.

    The bar: every tracked unit mastered, none set aside, and enough passing
    practice-exam attempts. This is the only place readiness is decided, and
    it reads the ledger, never the model.
    """
    unmastered = [u for u in led.order if led.mastery(u) != "mastered"]
    parked = led.parked_units()
    passes = sum(1 for a in mock_attempts if a.get("passed"))
    reasons = []
    if parked:
        reasons.append("%d unit%s set aside after repeated misses" % (len(parked), "" if len(parked) == 1 else "s"))
    remaining = [u for u in unmastered if u not in parked]
    if remaining:
        reasons.append("%d unit%s not yet mastered" % (len(remaining), "" if len(remaining) == 1 else "s"))
    if passes < passes_needed:
        reasons.append("%d of %d passing practice exams" % (passes, passes_needed))
    best = max([a.get("percent", 0) for a in mock_attempts] or [0])
    return {
        "ready": not reasons,
        "reasons": reasons,
        "passes": passes,
        "passes_needed": passes_needed,
        "attempts": len(mock_attempts),
        "best_percent": best,
        "pass_mark": int(PASS_MARK * 100),
    }
