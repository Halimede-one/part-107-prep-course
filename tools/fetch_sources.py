#!/usr/bin/env python3
"""Fetch the source documents named in knowledge-base/sources.json.

Each manifest entry with a `fetch` block is materialized as the PDF named in
its `pdf` field, which is what tools/build_kb.py reads. Three kinds of fetch:

    {"kind": "pdf",  "url": "..."}              download a published PDF as is
    {"kind": "ecfr", "part": "107"}             print the current eCFR text of a part
    {"kind": "ecfr", "sections": ["91.17", ...]} ... or of selected sections, in order
    {"kind": "html", "url": "..."}              print the main content of a web page

The eCFR and html kinds fetch HTML and print it to PDF with headless Chrome,
a build-time dependency like pdftotext. The page is always printed from a
local file, so Chrome never talks to the site; faa.gov refuses headless
browsers but serves the same page to a plain request. The html kind keeps the
page's main content, drops navigation and scripts, and prepends a
`TITLE: <title>` line so a heading regex can cut the page as one section
(`"title_line": false` leaves it out). The HTML that was printed is kept
next to the PDF for inspection.

Usage, from the course folder:
    python3 tools/fetch_sources.py              # every source whose PDF is missing
    python3 tools/fetch_sources.py --redo       # refresh existing PDFs too
    python3 tools/fetch_sources.py 14cfr107     # one source
    python3 tools/fetch_sources.py --chrome /path/to/chrome

Needs network access, and Chrome or Chromium on the PATH for the ecfr and
html kinds. Each fetch is recorded in knowledge-base/pdfs/fetch-log.json.
"""

import argparse
import datetime
import hashlib
import html as html_module
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ECFR = "https://www.ecfr.gov/api/renderer/v1/content/enhanced/current/title-14"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
CHROME_NAMES = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"]

# Elements that carry no document text: site chrome, scripts, media.
_STRIP = re.compile(
    r"<(script|style|noscript|nav|header|footer|aside|iframe|svg|form|video|audio|button)\b.*?</\1\s*>",
    re.S | re.I,
)
_VOID = re.compile(r"<(img|picture|source|link|meta|input|embed|object)\b[^>]*>", re.I)
_MAIN = re.compile(r"<main\b.*?</main\s*>", re.S | re.I)
_BODY = re.compile(r"<body\b.*?</body\s*>", re.S | re.I)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)

# A wide page keeps most paragraphs on one line, so a cross-reference such as
# "§ 107.29" rarely lands at the start of a line where it could be mistaken
# for a section heading.
_CSS = (
    "@page { size: 420mm 297mm; margin: 12mm } "
    "body { font: 11pt sans-serif; } pre { white-space: pre-wrap; }"
)


class FetchError(Exception):
    pass


def ecfr_url(part=None, section=None):
    """Renderer URL for the current text of a whole part or of one section."""
    if section:
        return "%s?part=%s&section=%s" % (ECFR, section.split(".")[0], section)
    return "%s?part=%s" % (ECFR, part)


def fetch(url, timeout=120):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        raise FetchError("HTTP %d for %s" % (error.code, url))
    except urllib.error.URLError as error:
        raise FetchError("could not reach %s: %s" % (url, error.reason))


def main_content(html):
    """The page's main element (or body), without scripts, chrome, or media."""
    match = _MAIN.search(html) or _BODY.search(html)
    content = match.group(0) if match else html
    return _VOID.sub("", _STRIP.sub("", content))


def page_title(html):
    match = _TITLE.search(html)
    if not match:
        return ""
    title = re.sub(r"\s+", " ", html_module.unescape(match.group(1))).strip()
    return title.split(" | ")[0].strip()


def wrap(body, title=None):
    """A complete printable document around a fragment."""
    lead = "<p>TITLE: %s</p>\n" % html_module.escape(title) if title else ""
    return ('<!doctype html>\n<html><head><meta charset="utf-8"><style>%s</style></head>\n'
            "<body>\n%s%s\n</body></html>\n" % (_CSS, lead, body))


def find_chrome(explicit=None):
    for name in ([explicit] if explicit else []) + CHROME_NAMES:
        path = shutil.which(name)
        if path:
            return path
    return None


def print_pdf(html_path, pdf_path, chrome):
    """Print a local HTML file to PDF with headless Chrome."""
    profile = tempfile.mkdtemp(prefix="part107-chrome-")
    argv = [chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
            "--user-data-dir=" + profile, "--print-to-pdf=" + os.path.abspath(pdf_path),
            "file://" + os.path.abspath(html_path)]
    try:
        # Some machines need the sandbox off to run Chrome at all; try without first.
        for extra in ([], ["--no-sandbox"]):
            finished = subprocess.run(argv[:-1] + extra + argv[-1:], capture_output=True, text=True, timeout=300)
            if finished.returncode == 0 and os.path.isfile(pdf_path):
                return
        raise FetchError("Chrome could not print %s: %s" % (html_path, (finished.stderr or "").strip()[-300:]))
    except subprocess.TimeoutExpired:
        raise FetchError("Chrome timed out printing %s" % html_path)
    finally:
        shutil.rmtree(profile, ignore_errors=True)


def materialize(source, chrome):
    """Write the source's PDF from its fetch block. Returns the fetched URL(s)."""
    spec = source["fetch"]
    pdf_path = os.path.join(ROOT, source["pdf"])
    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
    kind = spec.get("kind")

    if kind == "pdf":
        data = fetch(spec["url"])
        if not data.startswith(b"%PDF"):
            raise FetchError("%s did not return a PDF" % spec["url"])
        with open(pdf_path, "wb") as handle:
            handle.write(data)
        return [spec["url"]]

    if kind in ("ecfr", "html"):
        if not chrome:
            raise FetchError("Chrome is needed to print this source and was not found")
        if kind == "ecfr":
            urls = [ecfr_url(section=s) for s in spec.get("sections", [])] or [ecfr_url(part=spec["part"])]
            document = wrap("\n".join(fetch(url).decode("utf-8", "replace") for url in urls))
        else:
            urls = [spec["url"]]
            raw = fetch(spec["url"]).decode("utf-8", "replace")
            # "title_line": false drops the TITLE line, for a page whose own
            # headings carry the section structure (the AIM).
            title = (spec.get("title") or page_title(raw)) if spec.get("title_line", True) else None
            document = wrap(main_content(raw), title)
        html_path = os.path.splitext(pdf_path)[0] + ".html"
        with open(html_path, "w", encoding="utf-8") as handle:
            handle.write(document)
        print_pdf(html_path, pdf_path, chrome)
        return urls

    raise FetchError("unknown fetch kind %r" % kind)


def record(log_path, source, urls):
    """Note what was fetched for the source, and when, in the fetch log."""
    log = {}
    if os.path.isfile(log_path):
        with open(log_path, "r", encoding="utf-8") as handle:
            log = json.load(handle)
    with open(os.path.join(ROOT, source["pdf"]), "rb") as handle:
        data = handle.read()
    log[source["id"]] = {
        "fetched": datetime.date.today().isoformat(),
        "urls": urls,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    with open(log_path, "w", encoding="utf-8") as handle:
        json.dump(log, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sources", nargs="*", help="source ids to fetch (default: all with a fetch block)")
    parser.add_argument("--manifest", default=os.path.join(ROOT, "knowledge-base", "sources.json"))
    parser.add_argument("--redo", action="store_true", help="fetch again even if the PDF is present")
    parser.add_argument("--chrome", help="path to the Chrome or Chromium binary")
    args = parser.parse_args()

    with open(args.manifest, "r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    chrome = find_chrome(args.chrome)
    log_path = os.path.join(ROOT, "knowledge-base", "pdfs", "fetch-log.json")

    wanted = set(args.sources)
    fetched = skipped = failed = 0
    for source in manifest["sources"]:
        if wanted and source["id"] not in wanted:
            continue
        if not source.get("fetch"):
            print("%s: no fetch block, expecting %s to be placed by hand" % (source["id"], source["pdf"]))
            skipped += 1
            continue
        if os.path.isfile(os.path.join(ROOT, source["pdf"])) and not args.redo:
            print("%s: present" % source["id"])
            skipped += 1
            continue
        try:
            urls = materialize(source, chrome)
        except FetchError as error:
            print("%s: FAILED, %s" % (source["id"], error))
            failed += 1
            continue
        record(log_path, source, urls)
        print("%s: fetched %s" % (source["id"], source["pdf"]))
        fetched += 1
    print("fetched %d, skipped %d, failed %d" % (fetched, skipped, failed))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
