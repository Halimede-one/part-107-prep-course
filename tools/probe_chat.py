#!/usr/bin/env python3
"""Ask the chat tutor the retrieval probe's questions and check its citations.

Each question goes through the chat (Course.ask) with an empty history and no
unit on screen, on the backend set in config.json, so a run makes one chat
call per question and spends model time. For each, report whether a citation
names the expected CFR or statute section, whether the answer is labeled as
from the web, how many searches the tutor started, and the time. Compare a run
before and after a change to the chat.

Usage, from the course folder:
    python3 tools/probe_chat.py
    python3 tools/probe_chat.py --limit 3
"""

import argparse
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import server  # noqa: E402
from probe_retrieval import QUESTIONS  # noqa: E402


def cites(block, expected):
    """True when a citation's name or link names the expected section.
    The section must stand alone, so 1.1 does not match 91.137."""
    pattern = re.compile(r"(?<![\d.])%s(?!\d)" % re.escape(expected))
    return any(pattern.search("%s %s" % (c.get("source", ""), c.get("url", "")))
               for c in block.get("citations") or [])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=len(QUESTIONS))
    args = parser.parse_args()

    course = server.Course()
    course.ledger.current_unit = None  # no unit on screen: only the corpus can answer
    print("backend %s" % course.client.name)
    hits = web = errors = 0
    seconds = []
    for question, expected in QUESTIONS[:args.limit]:
        course.chat = []
        statuses = []
        started = time.time()
        block = course.ask(question, emit=lambda event: statuses.append(event.get("status", "")))
        seconds.append(time.time() - started)
        searches = sum(1 for s in statuses if s.startswith("Searching"))
        if block.get("type") != "cited_answer":
            errors += 1
            print("ERR  %-60s %s" % (question[:60], block.get("message", "")[:100]))
            continue
        hit = cites(block, expected)
        from_web = block.get("in_corpus") is False and bool(block.get("citations"))
        hits += hit
        web += from_web
        print("%s %-60s %-7s %s searches=%d %4.0f s  %s" % (
            "ok  " if hit else "MISS", question[:60], expected, "web" if from_web else "   ",
            searches, seconds[-1], "; ".join(c.get("source", "") for c in block.get("citations") or [])[:120]))
    count = min(args.limit, len(QUESTIONS))
    print("expected section cited: %d of %d; web answers: %d; errors: %d; %.0f s per question, %.0f s at most"
          % (hits, count, web, errors, sum(seconds) / len(seconds), max(seconds)))


if __name__ == "__main__":
    main()
