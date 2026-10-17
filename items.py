"""Vetted items and deterministic lookup scoring.

Vetted items (the mock exam, and any vetted practice items) are scored by exact
lookup against their keyed answer, so scoring stays correct whichever model is
driving and can be unit tested. Items the model generates on the fly are not in
this table; `score` reports that, and the caller falls back to model scoring.
"""

import os
import re

_ROW = re.compile(r"^\s*\|(?!\s*-)(.+)\|\s*$")


def _cells(inner):
    """Split the inside of a table row. `inner` is the regex group between the
    outer pipes, so no pipe stripping here: that would eat an empty last cell."""
    return [cell.strip() for cell in inner.split("|")]


def read_table(path, required):
    """Parse Markdown tables in a file into row dicts keyed by lowercase headers.

    `required` names the columns that identify the header row, which is how the
    table is found among surrounding prose. A missing file yields no rows, which
    is the normal state before the vetted content lands.
    """
    if not os.path.isfile(path):
        return []

    rows, headers = [], None
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            match = _ROW.match(line)
            if not match:
                continue
            cells = _cells(match.group(1))
            lowered = [c.lower() for c in cells]
            if all(column in lowered for column in required):
                headers = lowered
                continue
            if not headers or len(cells) != len(headers):
                continue
            rows.append(dict(zip(headers, cells)))
    return rows


def load_items(path):
    """Parse a Markdown items table into {item_id: item}."""
    items = {}
    for row in read_table(path, required=("item", "answer")):
        item_id = row.get("item", "")
        if item_id:
            items[item_id] = {
                "item": item_id,
                "unit": row.get("unit", ""),
                "answer": row.get("answer", ""),
                "source": row.get("source", ""),
                "url": row.get("link", row.get("url", "")),
                # Present for practice-exam items; absent for a bare answer key.
                "stem": row.get("stem", ""),
                "a": row.get("a", ""),
                "b": row.get("b", ""),
                "c": row.get("c", ""),
                "rationale": row.get("rationale", ""),
            }
    return items


# An instructor's questions file holds one unit's guidance for the tutor who
# writes its questions, and the instructor's own questions in the columns of
# the practice exam. Item numbers only grow, so a deleted id is never reused.
QUESTION_COLUMNS = ("item", "unit", "stem", "a", "b", "c", "answer", "rationale", "source", "url")
_LAST_ITEM = re.compile(r"^- Last item:\s*(\d+)\s*$")


def load_questions(path):
    """{guidance, items (file order), last item number} from an instructor's
    questions file. A missing file is the normal state and reads as empty."""
    if not os.path.isfile(path):
        return {"guidance": "", "items": [], "last": 0}
    section, guidance, last = None, [], 0
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle.read().splitlines():
            if line.startswith("## "):
                section = line[3:].strip().lower()
            elif section == "guidance":
                guidance.append(line)
            elif section is None and _LAST_ITEM.match(line):
                last = int(_LAST_ITEM.match(line).group(1))
    return {"guidance": "\n".join(guidance).strip(), "items": list(load_items(path).values()), "last": last}


def questions_text(unit, guidance, items, last):
    """The text of an instructor's questions file. A table cell holds one line."""
    lines = ["# %s check questions" % unit, "",
             "Saved from the instructor workspace. The course asks these questions before the tutor writes its own.",
             "", "- Last item: %d" % last, "", "## Guidance", ""]
    if guidance.strip():
        lines += [guidance.strip(), ""]
    lines += ["## Questions", "", "| Item | Unit | Stem | A | B | C | Answer | Rationale | Source | Link |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    lines += ["| %s |" % " | ".join(" ".join(str(item.get(key, "")).split()) for key in QUESTION_COLUMNS)
              for item in items]
    return "\n".join(lines) + "\n"


def item_question(item):
    """An instructor's question as a question block, with its key."""
    return {
        "type": "question",
        "question_id": item["item"],
        "unit": item["unit"],
        "stem": item["stem"],
        "options": [{"id": key.upper(), "text": item[key]} for key in ("a", "b", "c")],
        "answer": item["answer"].strip().upper(),
        "rationale": item["rationale"],
        "citations": [{"source": item["source"], "url": item["url"]}],
    }


def _words(text):
    """Lowercase words with one space between them and one at each end, so
    one phrase is found in another only at word boundaries."""
    return " %s " % " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def question_problems(block, facts=()):
    """What is wrong with a question block, in plain words; empty when nothing is.

    `facts` are the unit's vetted facts in the order the quiz message numbers
    them, F1 first. A question that names one in `fact` must key an option
    that states that fact's answer.
    """
    if block.get("type") != "question":
        return ["the reply is not a question block"]
    problems = []
    if not str(block.get("stem") or "").strip():
        problems.append("the stem is empty")
    options = block.get("options")
    if not isinstance(options, list) or [o.get("id") if isinstance(o, dict) else None for o in options] != list("ABC"):
        problems.append("there must be exactly three options, with the ids A, B and C in that order")
        options = []
    texts = {o["id"]: str(o.get("text") or "").strip() for o in options}
    if options and not all(texts.values()):
        problems.append("an option has no text")
    elif options and len({_words(t) for t in texts.values()}) != 3:
        problems.append("two options say the same thing")
    answer = str(block.get("answer") or "").strip().upper()
    if answer not in ("A", "B", "C"):
        problems.append("the answer must be A, B or C")
    if not str(block.get("rationale") or "").strip():
        problems.append("the rationale is empty")

    label = str(block.get("fact") or "").strip()
    if label:
        number = re.fullmatch(r"F(\d+)", label)
        if not number or not 1 <= int(number.group(1)) <= len(facts):
            problems.append("%s is not one of the vetted facts" % label)
        elif answer in texts:
            stated = facts[int(number.group(1)) - 1]["answer"]
            if re.sub(r"^ (the|a|an) ", " ", _words(stated)) not in _words(texts[answer]):
                problems.append("the keyed option does not state the answer of %s, which is: %s" % (label, stated))
    return problems


def score(items, item_id, selected_option):
    """Score a submitted option.

    Returns (method, correct):
      ("lookup", True/False) when the item has a vetted keyed answer,
      ("model", None) when it does not, so the caller scores it with the model.
    """
    item = items.get(item_id)
    if not item or not item.get("answer"):
        return "model", None
    return "lookup", item["answer"].strip().upper() == (selected_option or "").strip().upper()
