#!/usr/bin/env python3
"""List the numbers in each explanation chunk that its source chunk lacks.

A companion may invent scenario details for its illustration (a 600-foot
tower, a repair bill, a date), but it may not add a regulatory number. This
check cannot tell the two apart. It prints every number in a companion that
the source chunk does not contain, with the sentence it sits in, so a
reviewer can judge each one in a few seconds. Single digits (list numbering)
and section references such as "§ 107.41" are left out as noise. A number
that passes this check can still be wrong in context; the check narrows the
reading, it does not replace it.

Usage, from the course folder:
    python3 tools/check_companions.py             # every companion
    python3 tools/check_companions.py 14cfr107    # companions whose file name starts with this
    python3 tools/check_companions.py --quiet     # the summary line only
"""

import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import retrieval  # noqa: E402

NUMBER = re.compile(r"(?<![\w.])\d(?:[\d,]*\d)?(?:\.\d+)?(?![\w])")
SECTION_REFERENCE = re.compile(r"(?:§|section|sections|part|parts)\s*$", re.I)


def extra_numbers(source_text, companion_text):
    """Numbers in the companion that do not occur in the source, in order."""
    haystack = source_text.replace(",", "")
    found = []
    for match in NUMBER.finditer(companion_text):
        number = match.group(0)
        plain = number.replace(",", "")
        if len(plain) == 1 or plain in haystack or number in found:
            continue
        if SECTION_REFERENCE.search(companion_text[max(0, match.start() - 10):match.start()]):
            continue
        found.append(number)
    return found


def sentence_with(text, number):
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if re.search(r"(?<![\w.])" + re.escape(number) + r"(?![\w])", sentence):
            return sentence.strip()
    return ""


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("prefixes", nargs="*", help="only companions whose file name starts with one of these")
    parser.add_argument("--config", default=os.path.join(ROOT, "config.json"))
    parser.add_argument("--quiet", action="store_true", help="print the summary line only")
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as handle:
        kb_dir = os.path.join(ROOT, json.load(handle)["paths"]["knowledge_base"])
    chunks = {c["id"]: c for c in retrieval.load_chunks(kb_dir)}

    flagged = total = 0
    for chunk_id in sorted(chunks):
        chunk = chunks[chunk_id]
        if chunk["kind"] != "explanation":
            continue
        if args.prefixes and not chunk_id.startswith(tuple(args.prefixes)):
            continue
        total += 1
        source = chunks.get(chunk["derived_from"])
        if source is None:
            print("%s: source chunk %s is missing" % (chunk_id, chunk["derived_from"]))
            continue
        extra = extra_numbers(source["section"] + " " + source["text"], chunk["text"])
        if not extra:
            continue
        flagged += 1
        if not args.quiet:
            print(chunk_id)
            for number in extra:
                print("   %-8s | %s" % (number, sentence_with(chunk["text"], number)[:160]))
    print("%d of %d companions carry a number their source chunk does not; judge each in context"
          % (flagged, total))


if __name__ == "__main__":
    main()
