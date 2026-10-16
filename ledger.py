"""The student ledger: plain Markdown, human readable and auditable.

The unit list is seeded from objectives.md, so the 77 tracked units stay in sync
with the ACS spine automatically rather than being duplicated by hand.

Mastery is derived from attempt history rather than stored, so the ledger cannot
drift out of sync with itself. The threshold is the agreed one: two consecutive
correct answers on distinct items.

Gear transition decisions are not made here. This module records the gear the
orchestrator reports; the transition and terminal logic arrives in Phase 3.
"""

import os
import re

from orchestrator import lesson_files

MASTERY_STREAK = 2

_UNIT = re.compile(r"^\|\s*(UA\.I\.[A-F]\.K\d+[a-d]?)\s*\|")
_ROW = re.compile(r"^\s*\|(?!\s*-)(.+)\|\s*$")
_FIELD = re.compile(r"^-\s*([^:]+):\s*(.*)$")


def _cells(inner):
    """Split the inside of a table row. `inner` is the regex group between the
    outer pipes, so no pipe stripping here: that would eat an empty last cell."""
    return [cell.strip() for cell in inner.split("|")]


def load_units(objectives_path):
    """Read the tracked unit codes, in order, from objectives.md."""
    units = []
    with open(objectives_path, "r", encoding="utf-8") as handle:
        for line in handle:
            match = _UNIT.match(line)
            if match and match.group(1) not in units:
                units.append(match.group(1))
    return units


def available_gears(unit, curriculum_dir):
    """All three gears, for every unit. Fast-track and Foundational use their own
    lesson file where one is written; otherwise the tutor builds them from the
    Guided lesson (see orchestrator.content)."""
    return [1, 2, 3]


def _entry(gear):
    return {"current_gear": gear, "gears_taken": [], "needs_attention": False, "parked": False}


class Ledger:
    def __init__(self, area="Regulations", default_gear=1, current_unit=None):
        self.area = area
        self.default_gear = default_gear
        self.current_unit = current_unit
        self.last_task = None  # task letter last worked; a change marks a task boundary
        self.units = {}      # unit -> {current_gear, gears_taken, needs_attention, parked}
        self.order = []      # unit codes, in course order
        self.attempts = []   # {timestamp, unit, item, gear, result}
        self.mock_attempts = []  # {timestamp, score, total, percent, passed, missed}

    # ---- construction ---------------------------------------------------
    @classmethod
    def bootstrap(cls, objectives_path, area="Regulations", default_gear=1):
        ledger = cls(area=area, default_gear=default_gear)
        ledger.order = load_units(objectives_path)
        for unit in ledger.order:
            ledger.units[unit] = _entry(default_gear)
        ledger.current_unit = ledger.order[0] if ledger.order else None
        return ledger

    @classmethod
    def load(cls, path):
        ledger = cls()
        section = None
        headers = None
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if stripped.startswith("## "):
                    section, headers = stripped[3:].strip().lower(), None
                    continue

                field = _FIELD.match(stripped)
                if field and section is None:
                    key, value = field.group(1).strip().lower(), field.group(2).strip()
                    if key == "area":
                        ledger.area = value
                    elif key == "default gear":
                        ledger.default_gear = int(value)
                    elif key == "current unit":
                        ledger.current_unit = value or None
                    elif key == "last task":
                        ledger.last_task = value or None
                    continue

                row = _ROW.match(line)
                if not row:
                    continue
                cells = _cells(row.group(1))
                lowered = [c.lower() for c in cells]
                if "unit" in lowered or "timestamp" in lowered:
                    headers = lowered
                    continue
                if not headers or len(cells) != len(headers):
                    continue
                record = dict(zip(headers, cells))

                if section == "units":
                    unit = record.get("unit", "")
                    if not unit:
                        continue
                    taken = [int(g) for g in re.findall(r"\d", record.get("gears taken", ""))]
                    ledger.order.append(unit)
                    ledger.units[unit] = {
                        "current_gear": int(record.get("current gear") or ledger.default_gear),
                        "gears_taken": taken,
                        "needs_attention": record.get("needs attention", "no").lower() == "yes",
                        "parked": record.get("parked", "no").lower() == "yes",
                    }
                elif section == "attempts":
                    ledger.attempts.append({
                        "timestamp": record.get("timestamp", ""),
                        "unit": record.get("unit", ""),
                        "item": record.get("item", ""),
                        "gear": int(record.get("gear") or ledger.default_gear),
                        "result": record.get("result", ""),
                    })
                elif section == "mock attempts":
                    ledger.mock_attempts.append({
                        "timestamp": record.get("timestamp", ""),
                        "score": int(record.get("score") or 0),
                        "total": int(record.get("total") or 0),
                        "percent": float(record.get("percent") or 0),
                        "passed": record.get("passed", "no").lower() == "yes",
                        "missed": [u for u in record.get("missed units", "").split(",") if u.strip()],
                    })
        return ledger

    @classmethod
    def open_or_bootstrap(cls, path, objectives_path, area="Regulations"):
        if os.path.isfile(path):
            return cls.load(path)
        return cls.bootstrap(objectives_path, area=area)

    # ---- updates --------------------------------------------------------
    def record_attempt(self, unit, item, gear, correct, timestamp):
        self.attempts.append({
            "timestamp": timestamp,
            "unit": unit,
            "item": item,
            "gear": gear,
            "result": "correct" if correct else "incorrect",
        })
        entry = self.units.setdefault(unit, _entry(gear))
        if gear not in entry["gears_taken"]:
            entry["gears_taken"].append(gear)
        entry["current_gear"] = gear
        self.current_unit = unit

    def set_gear(self, unit, gear):
        """Record that the student is now working this unit at this gear.

        The gear is appended to the traversed path, which is what the course map
        draws. Setting a gear also makes the unit current, since we only set it
        when about to teach or test that unit.
        """
        entry = self.units.setdefault(unit, _entry(gear))
        entry["current_gear"] = gear
        if gear not in entry["gears_taken"]:
            entry["gears_taken"].append(gear)
        self.current_unit = unit

    def flag_attention(self, unit, value=True):
        self.units.setdefault(unit, _entry(self.default_gear))["needs_attention"] = value

    def park(self, unit):
        """Set the unit aside after repeated misses at its deepest gear.

        A parked unit is skipped by the course until the next task boundary,
        when it is unparked and retried. It keeps its needs-attention flag so
        the course map still shows where the student struggled.
        """
        entry = self.units.setdefault(unit, _entry(self.default_gear))
        entry["parked"] = True
        entry["needs_attention"] = True

    def unpark_all(self):
        """Return every parked unit to the course. Returns the units unparked."""
        unparked = []
        for unit in self.order:
            if self.units.get(unit, {}).get("parked"):
                self.units[unit]["parked"] = False
                unparked.append(unit)
        return unparked

    def parked_units(self):
        return [u for u in self.order if self.units.get(u, {}).get("parked")]

    def record_mock_attempt(self, result, timestamp):
        self.mock_attempts.append({
            "timestamp": timestamp,
            "score": result["score"],
            "total": result["total"],
            "percent": result["percent"],
            "passed": bool(result["passed"]),
            "missed": sorted({m["unit"] for m in result["missed"]}),
        })

    def last_attempt_index(self, unit):
        """Position of the unit's most recent attempt, or -1. Used for review order."""
        for index in range(len(self.attempts) - 1, -1, -1):
            if self.attempts[index]["unit"] == unit:
                return index
        return -1

    def set_default_gear(self, gear):
        self.default_gear = gear
        for entry in self.units.values():
            if not entry["gears_taken"]:
                entry["current_gear"] = gear

    # ---- derived state --------------------------------------------------
    def mastery(self, unit):
        """unseen, learning, or mastered, derived from attempt history."""
        attempts = [a for a in self.attempts if a["unit"] == unit]
        if not attempts:
            return "unseen"
        streak, seen_items = 0, set()
        for attempt in reversed(attempts):
            if attempt["result"] != "correct" or attempt["item"] in seen_items:
                break
            seen_items.add(attempt["item"])
            streak += 1
            if streak >= MASTERY_STREAK:
                return "mastered"
        return "learning"

    def state(self, curriculum_dir, objectives=None):
        """The /state payload the course map consumes. `objectives` maps a unit
        to its title; attempts per gear come from the attempt history."""
        attempts = {}
        for attempt in self.attempts:
            per_gear = attempts.setdefault(attempt["unit"], {})
            per_gear[str(attempt["gear"])] = per_gear.get(str(attempt["gear"]), 0) + 1
        units = []
        for unit in self.order:
            entry = self.units.get(unit, _entry(self.default_gear))
            units.append({
                "id": unit,
                "task": unit.split(".")[2],
                "title": (objectives or {}).get(unit, ""),
                "mastery": self.mastery(unit),
                "current": unit == self.current_unit,
                "available_gears": available_gears(unit, curriculum_dir),
                "written": os.path.isfile(os.path.join(curriculum_dir, "%s.md" % unit)),
                "gear_files": {str(g): f for g, f in lesson_files(curriculum_dir, unit).items()},
                "gears_taken": entry["gears_taken"],
                "attempts": attempts.get(unit, {}),
                "current_gear": entry["current_gear"],
                "needs_attention": entry["needs_attention"],
                "parked": entry.get("parked", False),
            })
        return {
            "area": self.area,
            "default_gear": self.default_gear,
            "last_task": self.last_task,
            "units": units,
            "summary": {
                "mastered": sum(1 for u in units if u["mastery"] == "mastered"),
                "total": len(units),
            },
        }

    # ---- persistence ----------------------------------------------------
    def to_markdown(self):
        lines = [
            "# Student ledger",
            "",
            "Generated and maintained by the course. Safe to read; edit with care.",
            "",
            "- Area: %s" % self.area,
            "- Default gear: %d" % self.default_gear,
            "- Current unit: %s" % (self.current_unit or ""),
            "- Last task: %s" % (self.last_task or ""),
            "",
            "## Units",
            "",
            "| Unit | Current gear | Gears taken | Needs attention | Parked |",
            "|---|---|---|---|---|",
        ]
        for unit in self.order:
            entry = self.units[unit]
            lines.append("| %s | %d | %s | %s | %s |" % (
                unit,
                entry["current_gear"],
                ", ".join(str(g) for g in entry["gears_taken"]),
                "yes" if entry["needs_attention"] else "no",
                "yes" if entry.get("parked") else "no",
            ))
        lines += [
            "",
            "## Attempts",
            "",
            "| Timestamp | Unit | Item | Gear | Result |",
            "|---|---|---|---|---|",
        ]
        for attempt in self.attempts:
            lines.append("| %s | %s | %s | %d | %s |" % (
                attempt["timestamp"], attempt["unit"], attempt["item"], attempt["gear"], attempt["result"]
            ))
        lines += [
            "",
            "## Mock attempts",
            "",
            "| Timestamp | Score | Total | Percent | Passed | Missed units |",
            "|---|---|---|---|---|---|",
        ]
        for attempt in self.mock_attempts:
            lines.append("| %s | %d | %d | %s | %s | %s |" % (
                attempt["timestamp"], attempt["score"], attempt["total"], attempt["percent"],
                "yes" if attempt["passed"] else "no", ", ".join(attempt["missed"]),
            ))
        return "\n".join(lines) + "\n"

    def save(self, path):
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(self.to_markdown())
