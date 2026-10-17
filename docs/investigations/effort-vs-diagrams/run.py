#!/usr/bin/env python3
"""Effort versus diagram quality for the authoring assistant.

Sends three fixed diagram requests to the authoring stage (prompts/author.md)
at several Claude Code effort levels, twice each, and keeps every reply, the
diagrams it drew, and the time and tokens it took, in this folder:

    results.json      one record per run
    svg/<run>.svg     each diagram, as the instructor would save it

The messages are built by the course's own orchestrator.author_context(), with
course search off, so the effort level is the only thing that changes. The
lesson files are read from git HEAD, so uncommitted edits do not change the
experiment. check.py then renders and measures the diagrams.

Run from the course folder:  python3 docs/investigations/effort-vs-diagrams/run.py
Needs Claude Code signed in; each run is one call on the plan (24 in all).
"""

import concurrent.futures
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, ROOT)

import orchestrator  # noqa: E402
import server        # noqa: E402

TASKS = [
    ("k16-altitude", "UA.I.B.K16", 3,
     "This looks good, but can we add a diagram that shows how the authorized altitude applies in the worked example?"),
    ("e-k3-categories", "UA.I.E.K3", 2,
     "Add a diagram that compares the four categories of operation over people: what each one requires of the "
     "aircraft, and where each one may fly over people."),
    ("a-k4-reporting", "UA.I.A.K4", 2,
     "Add a decision diagram that a student can follow to decide whether an accident must be reported to the FAA, "
     "and by when."),
]
EFFORTS = ["low", "medium", "default", "max"]
SAMPLES = 2
TIMEOUT = 900


def head(path):
    """A lesson file as committed, as the instructor's editor would show it."""
    relative = os.path.relpath(path, ROOT)
    text = subprocess.run(["git", "show", "HEAD:" + relative], cwd=ROOT, capture_output=True, text=True).stdout
    lines, rest = server._header(text)
    if lines is None:
        return text
    return "---\n" + "".join(l + "\n" for l in lines if not server._course_line(l)) + rest.lstrip("\n")


def run(task, effort, sample, tutor, paths):
    name, unit, gear, request = task
    run_id = "%s.%s.%d" % (name, effort, sample)
    text = head(orchestrator.lesson_path(paths["curriculum"], unit, gear))
    context = tutor.author_context(unit, gear, text, request, chunks=[], can_search=False)
    argv = ["claude", "-p", "--output-format", "json", "--system-prompt", tutor.system("author"), "--tools", "",
            "--setting-sources", "", "--strict-mcp-config", "--no-session-persistence"]
    if effort != "default":
        argv += ["--effort", effort]
    record = {"run": run_id, "task": name, "unit": unit, "gear": gear, "effort": effort, "sample": sample}
    started = time.monotonic()
    try:
        done = subprocess.run(argv, input=context, capture_output=True, text=True, timeout=TIMEOUT,
                              env=dict(os.environ, CLAUDE_CODE_DISABLE_AUTO_MEMORY="1"))
        data = json.loads(done.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        record.update(seconds=round(time.monotonic() - started), error=type(error).__name__)
        return record
    usage = data.get("usage") or {}
    record.update(seconds=round(time.monotonic() - started),
                  output_tokens=usage.get("output_tokens"),
                  thinking_tokens=(usage.get("output_tokens_details") or {}).get("thinking_tokens"))
    raw = data.get("result") or ""
    block = server._parse_json_block(raw)
    if not block or block.get("type") != "revision":
        record.update(error="no revision block", reply=raw[:500])
        return record
    record["note"] = block.get("note", "")
    try:
        if isinstance(block.get("edits"), list):
            record["mode"] = "edits"
            revised = server.apply_edits(text, block["edits"])
        else:
            record["mode"] = "file"
            revised = block.get("file") or ""
    except ValueError as problem:
        record.update(error="edits did not fit: %s" % problem)
        return record
    removed = [l for l in text.splitlines() if l not in revised.splitlines()]
    record["lines_removed"] = len(removed)
    drawings = [m.group("svg") for m in server._DRAWING.finditer(revised)]
    record["drawings"] = len(drawings)
    record["descriptions"] = [m.group("description").strip() for m in server._DRAWING.finditer(revised)]
    record["unsafe"] = any(server._UNSAFE_SVG.search(svg) for svg in drawings)
    # Every number in a label must be in the message the model received.
    labels = " ".join(re.sub(r"<[^>]+>", " ", t) for svg in drawings
                      for t in re.findall(r"<text\b[^>]*>(.*?)</text>", svg, re.S))
    numbers = sorted(set(re.findall(r"\d+(?:[.,]\d+)*", labels)))
    record["label_numbers"] = numbers
    record["unsupported_numbers"] = [n for n in numbers if n not in context]
    os.makedirs(os.path.join(HERE, "svg"), exist_ok=True)
    for index, svg in enumerate(drawings):
        if "xmlns=" not in svg.split(">", 1)[0]:
            svg = svg.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"', 1)
        suffix = "" if index == 0 else "-%d" % (index + 1)
        with open(os.path.join(HERE, "svg", run_id + suffix + ".svg"), "w", encoding="utf-8") as handle:
            handle.write(svg + "\n")
    return record


def main():
    paths = {k: os.path.join(ROOT, v) for k, v in json.load(open(os.path.join(ROOT, "config.json")))["paths"].items()}
    tutor = orchestrator.Orchestrator(paths)
    jobs = [(t, e, s) for s in range(1, SAMPLES + 1) for t in TASKS for e in EFFORTS]
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(run, t, e, s, tutor, paths) for t, e, s in jobs]
        for future in concurrent.futures.as_completed(futures):
            record = future.result()
            results.append(record)
            print("%-28s %4ss  out %-5s think %-5s %s" % (
                record["run"], record.get("seconds"), record.get("output_tokens"), record.get("thinking_tokens"),
                record.get("error") or "drawings %s, unsupported numbers %s" % (record.get("drawings"), record.get("unsupported_numbers"))),
                flush=True)
    results.sort(key=lambda r: (r["task"], EFFORTS.index(r["effort"]), r["sample"]))
    with open(os.path.join(HERE, "results.json"), "w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=1)


if __name__ == "__main__":
    main()
