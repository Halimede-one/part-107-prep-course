#!/usr/bin/env python3
"""Build the knowledge base from source PDFs.

Runs pdftotext over each PDF named in knowledge-base/sources.json, splits the
text into sections, and writes one chunk file per section with the citation
metadata the course needs: source, section, canonical URL, and page.

This is a mechanical step by design. The text comes from the source document,
not from a model, so the knowledge base stays ground truth. The model's layer
(explanations and illustrations) is added afterwards by tools/enhance_kb.py and
is kept apart by a `kind: explanation` tag.

Usage, from the course folder:
    python3 tools/build_kb.py                 # all sources in the manifest
    python3 tools/build_kb.py 14cfr107        # one source
    python3 tools/build_kb.py --dry-run       # show what would be written

Needs pdftotext (poppler-utils) on the PATH. It is a build-time tool only; the
running course has no such dependency.
"""

import argparse
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# How a section starts, per preset. Each needs a (?P<section>...) group.
HEADINGS = {
    "cfr": re.compile(r"^\s*§\s*(?P<section>\d+\.\d+[a-z]?)\s+(?P<title>\S.*)$"),
    "numbered": re.compile(r"^\s*(?P<section>\d{1,2}\.\d{1,2})\s+(?P<title>[A-Z][^\n]{2,})$"),
    "chapter": re.compile(r"^\s*(?P<section>Chapter\s+\d+)[:.]?\s*(?P<title>.*)$", re.IGNORECASE),
}

# Chunks longer than this are split at paragraph breaks, keeping the section id.
MAX_CHARS = 6000

# Lines that appear on every page and carry no content.
NOISE = re.compile(
    r"^\s*(?:Page\s+\d+(?:\s+of\s+\d+)?|\d{1,3}|"
    r"ECFR\s.*|eCFR\s.*|https?://\S+|AC\s+107-2A?|\d{1,2}/\d{1,2}/\d{2,4})\s*$",
    re.IGNORECASE,
)


def pdf_to_pages(pdf_path, layout=True):
    """Page texts, via pdftotext. Form feeds mark page breaks.

    Layout mode keeps the physical line layout, which suits single-column
    documents and tables. A source with "layout": false in the manifest is
    read in reading order instead, which is what a two-column handbook needs.
    """
    try:
        finished = subprocess.run(
            ["pdftotext"] + (["-layout"] if layout else []) + ["-enc", "UTF-8", pdf_path, "-"],
            capture_output=True, text=True, check=True,
        )
    except FileNotFoundError:
        sys.exit("pdftotext was not found. Install poppler-utils (brew install poppler, "
                 "or apt install poppler-utils) and run again.")
    except subprocess.CalledProcessError as error:
        sys.exit("pdftotext failed on %s: %s" % (pdf_path, error.stderr.strip()[:300]))
    return finished.stdout.split("\f")


def clean(line):
    return line.rstrip()


def split_sections(pages, heading):
    """Walk the pages and cut at section headings.

    Returns a list of {section, title, page, text}. Text before the first
    heading is kept as a 'front' chunk so nothing is silently dropped.
    """
    pattern = HEADINGS.get(heading) or re.compile(heading, re.MULTILINE)
    sections = []
    current = {"section": "front", "title": "Front matter", "page": 1, "lines": []}
    for page_number, page in enumerate(pages, start=1):
        for raw in page.splitlines():
            line = clean(raw)
            if NOISE.match(line):
                continue
            match = pattern.match(line)
            if match:
                sections.append(current)
                current = {
                    "section": match.group("section").strip(),
                    "title": (match.groupdict().get("title") or "").strip().rstrip("."),
                    "page": page_number,
                    "lines": [],
                }
                continue
            current["lines"].append(line)
    sections.append(current)

    out = []
    for section in sections:
        text = re.sub(r"\n{3,}", "\n\n", "\n".join(section["lines"])).strip()
        if not text:
            continue
        out.append({"section": section["section"], "title": section["title"],
                    "page": section["page"], "text": text})
    return out


def split_long(section, max_chars=MAX_CHARS):
    """Split an oversized section at paragraph breaks into numbered parts."""
    text = section["text"]
    if len(text) <= max_chars:
        return [section]
    parts, buffer = [], ""
    for paragraph in re.split(r"\n\s*\n", text):
        if buffer and len(buffer) + len(paragraph) + 2 > max_chars:
            parts.append(buffer)
            buffer = paragraph
        else:
            buffer = (buffer + "\n\n" + paragraph) if buffer else paragraph
    if buffer:
        parts.append(buffer)
    return [
        dict(section, text=part, part=index + 1, parts=len(parts))
        for index, part in enumerate(parts)
    ]


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def chunk_filename(source_id, section):
    name = "%s-%s" % (source_id, slug(section["section"]))
    if section.get("part"):
        name += "-p%d" % section["part"]
    return name + ".md"


def section_link(source, section):
    if section["section"] == "front":
        # Text before the first heading has no section to deep-link; cite the document.
        return source["url"]
    template = source.get("section_url") or "{url}#page={page}"
    return template.format(url=source["url"], section=section["section"], page=section["page"])


def render_chunk(source, section):
    label = section["section"]
    if section["section"] != "front" and source.get("heading") == "cfr":
        label = "§ " + section["section"]
    heading = label + (" " + section["title"] if section["title"] else "")
    if section.get("part"):
        heading += " (part %d of %d)" % (section["part"], section["parts"])
    return (
        "---\n"
        "source: %s\n"
        "section: %s\n"
        "url: %s\n"
        "page: %d\n"
        "kind: source\n"
        "---\n"
        "%s\n" % (source["title"], heading, section_link(source, section), section["page"], section["text"])
    )


def build_source(source, output_dir, dry_run=False):
    pdf_path = os.path.join(ROOT, source["pdf"])
    if not os.path.isfile(pdf_path):
        print("  skipped: %s is not present" % source["pdf"])
        return []
    pages = pdf_to_pages(pdf_path, layout=source.get("layout", True))
    sections = []
    for section in split_sections(pages, source.get("heading", "cfr")):
        sections.extend(split_long(section))
    written, names = [], {}
    for section in sections:
        name = chunk_filename(source["id"], section)
        if name in names:
            # A heading that repeats (a running header, a table of contents
            # entry, a task letter reused across areas) would otherwise
            # overwrite the earlier chunk silently.
            names[name] += 1
            name = name[:-3] + "-%d.md" % names[name]
        else:
            names[name] = 1
        path = os.path.join(output_dir, name)
        if not dry_run:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(render_chunk(source, section))
        written.append({"file": name, "source": source["title"], "section": section["section"],
                        "page": section["page"], "chars": len(section["text"])})
    repeats = sum(1 for count in names.values() if count > 1)
    print("  %d sections from %d pages%s" % (len(written), len(pages), (
        "; %d heading%s repeated, kept apart (check the heading regex)"
        % (repeats, "" if repeats == 1 else "s")) if repeats else ""))
    return written


def write_index(output_dir):
    """Regenerate index.md from every chunk on disk, so a one-source build
    does not drop the other sources' rows."""
    rows = []
    for name in sorted(os.listdir(output_dir)):
        if not name.endswith(".md") or name == "index.md":
            continue
        with open(os.path.join(output_dir, name), "r", encoding="utf-8") as handle:
            head = handle.read(2000)
        meta = dict(re.findall(r"^(source|section|page|kind): (.*)$", head.split("---")[1], re.M)) if head.startswith("---") else {}
        rows.append("| %s | %s | %s | %s | %s |" % (
            name, meta.get("source", ""), meta.get("section", ""), meta.get("page", ""), meta.get("kind", "")))
    lines = ["# Knowledge base index", "",
             "Generated by tools/build_kb.py. One row per chunk file.", "",
             "| File | Source | Section | Page | Kind |", "|---|---|---|---|---|"] + rows
    with open(os.path.join(output_dir, "index.md"), "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sources", nargs="*", help="source ids to build (default: all)")
    parser.add_argument("--manifest", default=os.path.join(ROOT, "knowledge-base", "sources.json"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with open(args.manifest, "r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    output_dir = os.path.join(ROOT, manifest.get("output", "knowledge-base/regulations"))
    os.makedirs(output_dir, exist_ok=True)

    wanted = set(args.sources)
    entries = []
    for source in manifest["sources"]:
        if wanted and source["id"] not in wanted:
            continue
        print(source["id"])
        entries.extend(build_source(source, output_dir, dry_run=args.dry_run))
    if entries and not args.dry_run:
        write_index(output_dir)
    print("%s%d chunks" % ("would write " if args.dry_run else "wrote ", len(entries)))


if __name__ == "__main__":
    main()
