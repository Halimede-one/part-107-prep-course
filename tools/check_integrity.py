#!/usr/bin/env python3
"""Check the course content for coverage and well-formedness.

What it verifies:
  coverage    every tracked unit has gear-2 content and a reference fact, or is a
              grouping parent whose sub-elements all have them
  content     each content file has a source line with a link and a non-empty body
  facts       each reference fact names a known unit, an answer, a source, a link
  mock        each item is well-formed, keyed to one of A/B/C, mapped to a known
              unit, with a rationale and a link; every task with units has items
  kb          each chunk carries source, section, link, and a known kind; each
              explanation chunk points at a source chunk that exists
  prompts     every stage prompt the server loads is present

It cannot check that a fact is true. That is the human vetting step, done
against the source text in the knowledge base.

Exit status is 1 when any error is found. Missing coverage is an error unless
--allow-incomplete is given, which reports it as a warning while content is
still being written.

Usage, from the course folder:
    python3 tools/check_integrity.py
    python3 tools/check_integrity.py --allow-incomplete
"""

import argparse
import json
import os
import re
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import items as items_module      # noqa: E402
import ledger as ledger_module    # noqa: E402
import orchestrator               # noqa: E402
import retrieval                  # noqa: E402

STAGE_PROMPTS = ["orchestrator", "teach", "quiz", "score_diagnose", "remediate", "qa", "mock_gate", "enhance"]
HTTP = re.compile(r"^https?://\S+$")


class Report:
    def __init__(self):
        self.errors, self.warnings, self.notes = [], [], []

    def error(self, text):
        self.errors.append(text)

    def warn(self, text):
        self.warnings.append(text)

    def note(self, text):
        self.notes.append(text)


def children_of(units):
    """unit -> its lettered sub-elements."""
    out = {}
    for unit in units:
        match = re.match(r"^(UA\.I\.[A-F]\.K\d+)([a-d])$", unit)
        if match:
            out.setdefault(match.group(1), []).append(unit)
    return out


def check_prompts(paths, report):
    for name in STAGE_PROMPTS:
        if not os.path.isfile(os.path.join(paths["prompts"], name + ".md")):
            report.error("prompts: missing %s.md" % name)


def check_content_file(path, label, report):
    with open(path, "r", encoding="utf-8") as handle:
        parsed = orchestrator.parse_content(handle.read())
    if not parsed["sources"]:
        report.error("%s: no source line in the header" % label)
    for source in parsed["sources"]:
        if not source["source"]:
            report.error("%s: a source line has no name" % label)
        if not HTTP.match(source["url"]):
            report.error("%s: source %r has no http link" % (label, source["source"]))
    if len(parsed["body"].split()) < 20:
        report.error("%s: body is empty or too short to teach from" % label)


def check_coverage(paths, units, report, allow_incomplete):
    curriculum = paths["curriculum"]
    facts = orchestrator.load_facts(paths["reference"])
    kids = children_of(units)
    has_content = {u: os.path.isfile(os.path.join(curriculum, u + ".md")) for u in units}
    has_fact = {u: bool(facts.get(u)) for u in units}

    def covered(unit, table):
        if table[unit]:
            return True
        children = kids.get(unit, [])
        return bool(children) and all(table[c] for c in children)

    missing_content = [u for u in units if not covered(u, has_content)]
    missing_fact = [u for u in units if not covered(u, has_fact)]
    via_children = [u for u in units if not has_content[u] and covered(u, has_content)]

    report.note("coverage: %d of %d units have gear-2 content (%d covered by sub-elements)"
                % (len(units) - len(missing_content), len(units), len(via_children)))
    report.note("coverage: %d of %d units have a reference fact" % (len(units) - len(missing_fact), len(units)))
    gear3 = sorted(f[:-len(".gear3.md")] for f in os.listdir(curriculum) if f.endswith(".gear3.md"))
    report.note("coverage: gear-3 content for %d unit%s%s" % (
        len(gear3), "" if len(gear3) == 1 else "s", (": " + ", ".join(gear3)) if gear3 else ""))

    sink = report.warn if allow_incomplete else report.error
    if missing_content:
        sink("coverage: no gear-2 content for %d unit%s: %s" % (
            len(missing_content), "" if len(missing_content) == 1 else "s", ", ".join(missing_content)))
    if missing_fact:
        sink("coverage: no reference fact for %d unit%s: %s" % (
            len(missing_fact), "" if len(missing_fact) == 1 else "s", ", ".join(missing_fact)))

    for name in sorted(os.listdir(curriculum)):
        # Only unit-named files are content; objectives.md and STATUS.md live here too.
        if not name.endswith(".md") or not name.startswith("UA."):
            continue
        unit = name.replace(".gear3.md", "").replace(".md", "")
        if unit not in units:
            report.error("content: %s does not match a tracked unit" % name)
            continue
        check_content_file(os.path.join(curriculum, name), "content " + name, report)


def check_facts(paths, units, report):
    rows = items_module.read_table(paths["reference"], required=("unit", "fact"))
    if not rows and os.path.isfile(paths["reference"]):
        report.error("facts: %s has no table with Unit and Fact columns" % os.path.basename(paths["reference"]))
    for index, row in enumerate(rows, start=1):
        label = "facts row %d (%s)" % (index, row.get("unit", "?"))
        if row.get("unit") not in units:
            report.error("%s: unknown unit" % label)
        for column in ("fact", "answer", "source"):
            if not row.get(column):
                report.error("%s: empty %s" % (label, column))
        if not HTTP.match(row.get("link", "")):
            report.error("%s: link is not an http link" % label)


def check_mock(paths, units, report, allow_incomplete):
    all_items = items_module.load_items(paths["items"])
    import mockexam
    exam = mockexam.mock_items(all_items)
    if not exam:
        (report.warn if allow_incomplete else report.error)("mock: no practice-exam items found in %s"
                                                             % os.path.basename(paths["items"]))
        return
    ids = Counter(all_items)
    for item_id, item in exam.items():
        label = "mock %s" % item_id
        if item["unit"] not in units:
            report.error("%s: unknown unit %r" % (label, item["unit"]))
        if item["answer"].upper() not in ("A", "B", "C"):
            report.error("%s: answer must be A, B, or C" % label)
        options = [item["a"], item["b"], item["c"]]
        if len(set(o.strip().lower() for o in options)) != 3:
            report.error("%s: options are not three distinct texts" % label)
        if not item["rationale"]:
            report.error("%s: no rationale" % label)
        if not item["source"]:
            report.error("%s: no source" % label)
        if not HTTP.match(item["url"]):
            report.error("%s: link is not an http link" % label)

    by_task_units = Counter(orchestrator.task_of(u) for u in units)
    by_task_items = Counter(orchestrator.task_of(i["unit"]) for i in exam.values() if i["unit"] in units)
    shares = []
    for task in sorted(by_task_units):
        unit_share = by_task_units[task] / len(units)
        item_share = by_task_items[task] / len(exam)
        shares.append("%s %d%% of units, %d%% of items" % (task, round(100 * unit_share), round(100 * item_share)))
        if by_task_items[task] == 0:
            report.error("mock: task %s has units but no items" % task)
    report.note("mock: %d items; weighting by task: %s" % (len(exam), "; ".join(shares)))


def check_kb(paths, report):
    kb = paths["knowledge_base"]
    chunks = retrieval.load_chunks(kb)
    if not chunks:
        report.warn("kb: no chunks in %s (run tools/build_kb.py)" % os.path.relpath(kb, ROOT))
        return
    ids = {c["id"] for c in chunks}
    kinds = Counter(c["kind"] for c in chunks)
    for chunk in chunks:
        label = "kb %s" % chunk["id"]
        if not chunk["source"] or chunk["source"] == chunk["id"]:
            report.error("%s: no source" % label)
        if not chunk["section"]:
            report.error("%s: no section" % label)
        if not HTTP.match(chunk["url"]):
            report.error("%s: link is not an http link" % label)
        if chunk["kind"] not in ("source", "explanation"):
            report.error("%s: unknown kind %r" % (label, chunk["kind"]))
        if chunk["kind"] == "explanation" and chunk["derived_from"] not in ids:
            report.error("%s: derived_from %r is not a chunk" % (label, chunk["derived_from"]))
    report.note("kb: %d chunks (%d source, %d explanation)" % (len(chunks), kinds["source"], kinds["explanation"]))


def run(config_path, allow_incomplete):
    with open(config_path, "r", encoding="utf-8") as handle:
        config = json.load(handle)
    paths = {k: os.path.join(ROOT, v) for k, v in config["paths"].items()}
    report = Report()

    units = ledger_module.load_units(paths["objectives"])
    if not units:
        report.error("objectives: no tracked units found in %s" % paths["objectives"])
        return report
    report.note("objectives: %d tracked units" % len(units))

    check_prompts(paths, report)
    check_coverage(paths, units, report, allow_incomplete)
    check_facts(paths, units, report)
    check_mock(paths, units, report, allow_incomplete)
    check_kb(paths, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=os.path.join(ROOT, "config.json"))
    parser.add_argument("--allow-incomplete", action="store_true",
                        help="report missing coverage as warnings while content is in progress")
    args = parser.parse_args()
    report = run(args.config, args.allow_incomplete)
    for line in report.notes:
        print("  " + line)
    for line in report.warnings:
        print("WARN  " + line)
    for line in report.errors:
        print("ERROR " + line)
    print("%d error%s, %d warning%s" % (len(report.errors), "" if len(report.errors) == 1 else "s",
                                         len(report.warnings), "" if len(report.warnings) == 1 else "s"))
    sys.exit(1 if report.errors else 0)


if __name__ == "__main__":
    main()
