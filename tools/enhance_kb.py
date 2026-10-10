#!/usr/bin/env python3
"""Add the model-written layer to the knowledge base.

For each source chunk written by build_kb.py, ask the configured model for a
plain-language explanation, a concrete illustration, and the common misreading,
all restated from the chunk and nothing beyond it. The result is written as a
companion chunk tagged `kind: explanation` that carries the same citation as its
source chunk, so a free-form answer drawn from it still links to the regulation.

The two layers stay distinct on purpose: the source layer is ground truth and
the explanation layer is derived from it. Retrieval returns both; the tutor is
told which is which.

Usage, from the course folder:
    python3 tools/enhance_kb.py                 # every source chunk without a companion
    python3 tools/enhance_kb.py --redo          # rewrite existing companions too
    python3 tools/enhance_kb.py 14cfr107-107-41 # one chunk (by file stem)

Uses the provider in config.json. The claude_code backend costs nothing extra
on a Claude plan, which makes it the natural choice for this pass.
"""

import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import retrieval                                   # noqa: E402
from llm_client import LLMClient, LLMError, load_config  # noqa: E402


def companion_name(stem):
    return stem + ".explained.md"


def render(chunk, answer):
    body = []
    if answer.get("explanation"):
        body.append(answer["explanation"].strip())
    if answer.get("illustration"):
        body.append("Illustration: " + answer["illustration"].strip())
    if answer.get("misreading"):
        body.append("Common misreading: " + answer["misreading"].strip())
    return (
        "---\n"
        "source: Explanation of %s\n"
        "section: %s\n"
        "url: %s\n"
        "page: %s\n"
        "kind: explanation\n"
        "derived_from: %s\n"
        "---\n"
        "%s\n" % (chunk["source"], chunk["section"], chunk["url"], chunk.get("page", ""),
                  chunk["id"], "\n\n".join(body))
    )


def parse_answer(raw):
    text = re.sub(r"^```[a-z]*\s*|\s*```$", "", (raw or "").strip())
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


def enhance(chunk, client, system):
    user = (
        "SOURCE: %s\nSECTION: %s\nURL: %s\n\nCHUNK:\n%s"
        % (chunk["source"], chunk["section"], chunk["url"], chunk["text"])
    )
    return parse_answer(client.complete(system, user, stage="enhance"))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("chunks", nargs="*", help="chunk file stems to process (default: all without a companion)")
    parser.add_argument("--redo", action="store_true", help="rewrite companions that already exist")
    parser.add_argument("--config", default=os.path.join(ROOT, "config.json"))
    args = parser.parse_args()

    config = load_config(args.config)
    kb_dir = os.path.join(ROOT, config["paths"]["knowledge_base"])
    with open(os.path.join(ROOT, "prompts", "enhance.md"), "r", encoding="utf-8") as handle:
        system = handle.read()
    client = LLMClient(config)
    print("provider: %s" % client.name)

    wanted = set(args.chunks)
    done = skipped = failed = 0
    for chunk in retrieval.load_chunks(kb_dir):
        stem = chunk["id"][:-3]
        if chunk.get("kind") != "source":
            continue
        if wanted and stem not in wanted:
            continue
        target = os.path.join(kb_dir, companion_name(stem))
        if os.path.exists(target) and not args.redo:
            continue
        try:
            answer = enhance(chunk, client, system)
        except LLMError as error:
            print("  %s: %s" % (stem, error))
            failed += 1
            continue
        if not answer:
            print("  %s: no usable answer" % stem)
            failed += 1
            continue
        if answer.get("skip"):
            print("  %s: skipped (no teachable content)" % stem)
            skipped += 1
            continue
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(render(chunk, answer))
        done += 1
        print("  %s: written" % stem)
    print("written %d, skipped %d, failed %d" % (done, skipped, failed))


if __name__ == "__main__":
    main()
