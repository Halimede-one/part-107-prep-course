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
