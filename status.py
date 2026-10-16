"""The vetting record: one table row per unit in curriculum/regulations/STATUS.md.

The server changes one unit's row when a lesson file is saved: the cell for the
gear, and the status and the notes when given. The rest of the file stays as
it is, so the table can still be edited by hand.
"""

import os
import re
import tempfile
import threading
import time

GEAR_COLUMNS = {1: "gear 1", 2: "gear 2", 3: "gear 3"}

_ROW = re.compile(r"^\s*\|(.+)\|\s*$")
_LOCK = threading.Lock()


def _cells(line):
    match = _ROW.match(line)
    return [c.strip() for c in match.group(1).split("|")] if match else None


def _table(lines):
    """The header's index and lowercase column names, or (None, None)."""
    for index, line in enumerate(lines):
        cells = _cells(line)
        if cells and [c.lower() for c in cells][:1] == ["unit"] and "gear 2" in [c.lower() for c in cells]:
            return index, [c.lower() for c in cells]
    return None, None


def row(path, unit):
    """The unit's row as {column: text}, or {} when the file or the row is missing."""
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    header, columns = _table(lines)
    if header is None:
        return {}
    for line in lines[header + 2:]:
        cells = _cells(line)
        if cells is None:
            break
        if cells[0] == unit and len(cells) == len(columns):
            return dict(zip(columns, cells))
    return {}


def record(path, unit, gear, cell, status=None, note=None):
    """Set the unit's cell for a gear, and its status and a dated note when
    given. A unit with no row gets one at the end of the table. Does nothing
    when the file or its table is missing."""
    with _LOCK:
        if not os.path.isfile(path):
            return
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        header, columns = _table(lines)
        if header is None or GEAR_COLUMNS[gear] not in columns:
            return
        end = header + 2
        while end < len(lines) and _cells(lines[end]) is not None:
            end += 1
        at = next((i for i in range(header + 2, end) if _cells(lines[i])[0] == unit), None)
        cells = _cells(lines[at]) if at is not None else [unit] + [""] * (len(columns) - 1)
        cells += [""] * (len(columns) - len(cells))

        def put(column, value):
            if column in columns:
                cells[columns.index(column)] = value.replace("|", "/")

        put(GEAR_COLUMNS[gear], cell)
        if status:
            put("status", status)
        if note and "notes" in columns:
            dated = "%s: %s" % (time.strftime("%Y-%m-%d"), note)
            old = cells[columns.index("notes")]
            put("notes", (old + " " + dated) if old else dated)
        line = "| " + " | ".join(cells) + " |"
        if at is None:
            lines.insert(end, line)
        else:
            lines[at] = line
        _write(path, "\n".join(lines) + "\n")


def _write(path, text):
    """Replace the file in one step, so a reader never sees half of it."""
    folder = os.path.dirname(path) or "."
    handle, temporary = tempfile.mkstemp(dir=folder, prefix=".status-")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            out.write(text)
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise
