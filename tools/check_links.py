#!/usr/bin/env python3
"""Check that every link the course cites still resolves.

Collects the links from the curriculum headers, the reference facts, the
practice exam, and the knowledge base, requests each one once, and reports
any that fail. Cite-and-link everywhere is only honest while the links work,
and FAA moves documents.

Usage, from the course folder:
    python3 tools/check_links.py
    python3 tools/check_links.py --timeout 20

Needs network access. Exit status is 1 when any link fails.
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import items as items_module      # noqa: E402
import orchestrator               # noqa: E402
import retrieval                  # noqa: E402

URL = re.compile(r"https?://[^\s|)>\]]+")


def collect(paths):
    """url -> list of places it is cited."""
    found = {}

    def add(url, where):
        url = url.split("#")[0]
        found.setdefault(url, []).append(where)

    curriculum = paths["curriculum"]
    for name in sorted(os.listdir(curriculum)):
        if name.startswith("UA.") and name.endswith(".md"):
            with open(os.path.join(curriculum, name), "r", encoding="utf-8") as handle:
                for source in orchestrator.parse_content(handle.read())["sources"]:
                    if source["url"]:
                        add(source["url"], "curriculum/" + name)
    for row in items_module.read_table(paths["reference"], required=("unit", "fact")):
        if row.get("link"):
            add(row["link"], "facts %s" % row.get("unit"))
    for item_id, item in items_module.load_items(paths["items"]).items():
        if item["url"]:
            add(item["url"], "mock %s" % item_id)
    for chunk in retrieval.load_chunks(paths["knowledge_base"]):
        if chunk["url"]:
            add(chunk["url"], "kb %s" % chunk["id"])
    return found


def probe(url, timeout):
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "part107-course-linkcheck"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, ""
    except urllib.error.HTTPError as error:
        if error.code in (403, 405):
            # Some hosts refuse HEAD; try a GET before calling it broken.
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "part107-course-linkcheck"})
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    return response.status, ""
            except urllib.error.HTTPError as again:
                return again.code, str(again.reason)
            except urllib.error.URLError as again:
                return 0, str(again.reason)
        return error.code, str(error.reason)
    except urllib.error.URLError as error:
        return 0, str(error.reason)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=os.path.join(ROOT, "config.json"))
    parser.add_argument("--timeout", type=int, default=15)
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as handle:
        config = json.load(handle)
    paths = {k: os.path.join(ROOT, v) for k, v in config["paths"].items()}

    links = collect(paths)
    print("checking %d distinct links" % len(links))
    failed = 0
    for url in sorted(links):
        status, reason = probe(url, args.timeout)
        ok = 200 <= status < 400
        if not ok:
            failed += 1
        print("%s %s %s" % ("ok  " if ok else "FAIL", status or "---", url))
        if not ok:
            print("      %s; cited by %s" % (reason, ", ".join(links[url][:3]) + (" ..." if len(links[url]) > 3 else "")))
    print("%d failed of %d" % (failed, len(links)))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
