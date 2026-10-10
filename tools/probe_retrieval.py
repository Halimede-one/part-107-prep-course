#!/usr/bin/env python3
"""Probe retrieval over the built knowledge base with student-style questions.

For each question, report whether the expected CFR section (by file-name
prefix) reaches the top three chunks, and whether any regulation chunk or
regulation explanation does. The numbers are a coarse health check for the
corpus and the lexical retriever, not a test: a miss can still be a useful
guidance chunk, and a hit can be a poor one. Compare runs before and after a
change to the corpus or to retrieval.

Usage, from the course folder:
    python3 tools/probe_retrieval.py
    python3 tools/probe_retrieval.py --top 5
"""

import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import retrieval  # noqa: E402

# (question in student vocabulary, expected CFR or statute section)
QUESTIONS = [
    ("How high can I fly my drone?", "107.51"),
    ("What is the maximum speed under part 107?", "107.51"),
    ("Do I need permission to fly in Class D airspace?", "107.41"),
    ("Can I fly at night?", "107.29"),
    ("What are the rules for flying over people with a Category 2 drone?", "107.115"),
    ("What happens if I alter my remote pilot certificate?", "3.403"),
    ("When do I have to report an accident to the FAA?", "107.9"),
    ("How long after drinking alcohol can I fly?", "107.27"),
    ("Does my 0.4 pound drone need to be registered?", "48.15"),
    ("Can I fly from a moving car?", "107.25"),
    ("What is a visual observer responsible for?", "107.33"),
    ("What is remote identification and when is it required?", "89.1"),
    ("What is a FAA-recognized identification area?", "89.2"),
    ("How often do I need recurrent training?", "107.65"),
    ("Which rules can be waived?", "107.205"),
    ("What is the minimum visibility for a part 107 flight?", "107.51"),
    ("How far from clouds must I stay?", "107.51"),
    ("Can I fly over a crowd at a concert with a Category 3 aircraft?", "107.125"),
    ("What does night mean in the regulations?", "1.1"),
    ("What is a temporary flight restriction and must I obey it?", "91.137"),
    ("Can I drop something from the drone?", "107.23"),
    ("Can I fly more than one drone at a time?", "107.35"),
    ("What is the recreational exception?", "44809"),
    ("Can I carry hazardous materials?", "107.36"),
]

REGULATION_PREFIXES = ("14cfr", "49usc")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--top", type=int, default=3)
    parser.add_argument("--kb", default=os.path.join(ROOT, "knowledge-base", "regulations"))
    args = parser.parse_args()

    chunks = retrieval.load_chunks(args.kb)
    print("%d chunks" % len(chunks))
    expected_hits = regulation_hits = 0
    started = time.time()
    for question, expected in QUESTIONS:
        found = retrieval.search(chunks, question, top_k=args.top)
        ids = [c["id"][:-3] for c in found]
        hit = any(("-" + expected.replace(".", "-")) in i for i in ids)
        regulation = any(i.startswith(REGULATION_PREFIXES) for i in ids)
        expected_hits += hit
        regulation_hits += regulation
        print("%s %-66s %s" % ("ok  " if hit else "MISS", question[:66], ", ".join(ids)))
    print("expected section in top %d: %d of %d; a regulation chunk or its explanation in top %d: %d of %d; %.3f s per query"
          % (args.top, expected_hits, len(QUESTIONS), args.top, regulation_hits, len(QUESTIONS),
             (time.time() - started) / len(QUESTIONS)))


if __name__ == "__main__":
    main()
