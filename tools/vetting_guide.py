"""Render docs/vetting-guide.html: the vetting guide and the per-unit checklist.

Reads objectives.md, STATUS.md, the reference facts, the practice exam, and the
lesson files, and writes one self-contained page with links into the repository.
Re-run it whenever STATUS.md changes:

    python3 tools/vetting_guide.py

The page is a working aid. STATUS.md stays the record of what is vetted.
"""

import datetime
import glob
import html
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import orchestrator  # noqa: E402

CURRICULUM = os.path.join(ROOT, "curriculum", "regulations")
KB = os.path.join(ROOT, "knowledge-base", "regulations")
OUT = os.path.join(ROOT, "docs", "vetting-guide.html")

# Links are relative to docs/, where the page lives.
REL = {
    "readme": "../README.md",
    "status": "../curriculum/regulations/STATUS.md",
    "objectives": "../curriculum/regulations/objectives.md",
    "curriculum": "../curriculum/regulations/",
    "facts": "../reference/regulations-facts.md",
    "mock": "../mock/regulations-mock.md",
    "kb": "../knowledge-base/regulations/",
    "kb_index": "../knowledge-base/regulations/index.md",
    "build": "../knowledge-base/BUILD.md",
    "explanation": "../knowledge-base/EXPLANATION-LAYER.md",
    "sources": "../sources/SOURCES.md",
    "plan": "plans/content-tasks-b-to-f.md",
    "instructor_plan": "plans/instructor-interface.md",
    "check_integrity": "../tools/check_integrity.py",
    "check_links": "../tools/check_links.py",
    "check_companions": "../tools/check_companions.py",
}


def esc(text):
    return html.escape(str(text), quote=True)


def table_rows(path):
    """Rows of the first markdown table in a file, as dicts keyed by the lowercase header."""
    rows, columns = [], None
    for line in open(path, encoding="utf-8").read().splitlines():
        match = re.match(r"^\s*\|(.+)\|\s*$", line)
        if not match:
            if columns:
                break
            continue
        cells = [c.strip() for c in match.group(1).split("|")]
        if columns is None:
            columns = [c.lower() for c in cells]
        elif set(cells[0]) <= set("-: "):
            continue
        else:
            rows.append(dict(zip(columns, cells + [""] * (len(columns) - len(cells)))))
    return rows


def tasks():
    """[(letter, title, [codes])] in the order of objectives.md."""
    out, current = [], None
    for line in open(os.path.join(CURRICULUM, "objectives.md"), encoding="utf-8").read().splitlines():
        heading = re.match(r"^## Task ([A-F])\. (.+)$", line)
        if heading:
            current = (heading.group(1), heading.group(2).strip(), [])
            out.append(current)
            continue
        code = re.match(r"^\| (UA\.I\.[A-F]\.K\d+[a-d]?) \|", line)
        if code and current:
            current[2].append(code.group(1))
    return out


def chunk_for(name):
    """The knowledge-base chunk file for a source name such as '14 CFR 107.41', or None."""
    match = re.match(r"^14 CFR (\d+)\.(\d+)$", name)
    if match:
        part, section = match.groups()
        candidates = ["14cfr%s-%s-%s.md" % (part, part, section), "14cfr-referenced-%s-%s.md" % (part, section)]
        candidates += sorted(os.path.basename(p) for p in glob.glob(os.path.join(KB, "14cfr%s-%s-%s-p*.md" % (part, part, section)))
                             if not p.endswith(".explained.md"))
        for candidate in candidates:
            if os.path.isfile(os.path.join(KB, candidate)):
                return candidate
    if name.startswith("49 U.S.C. 44809"):
        return "49usc44809-44809-p1.md"
    return None


def source_links(sources):
    parts = []
    for source in sources:
        name, url = source["source"], source["url"]
        chunk = chunk_for(name)
        if chunk:
            parts.append('<a href="%s%s">%s</a> <a class="ext" href="%s">official</a>'
                         % (REL["kb"], esc(chunk), esc(name), esc(url)))
        elif url:
            parts.append('<a class="ext" href="%s">%s</a>' % (esc(url), esc(name)))
        else:
            parts.append(esc(name))
    return "<br>".join(parts)


def badge(cell):
    text = cell.strip() or "no file"
    if not cell.strip():
        kind = "none"
    elif "vetted" in cell:
        kind = "ok"
    elif "tutor draft" in cell:
        kind = "tutor"
    else:
        kind = "draft"
    return '<span class="badge %s">%s</span>' % (kind, esc(text))


def note_text(note):
    """The note without the dated boilerplate that every new row carries."""
    note = re.sub(r"2026-10-17: Guided lesson and facts written against the knowledge base; not vetted\.?\s*", "", note)
    return note.strip()


def checkbox(key):
    return '<input type="checkbox" data-key="%s">' % esc(key)


def build():
    objectives = orchestrator.load_objectives(os.path.join(CURRICULUM, "objectives.md"))
    status = {row["unit"]: row for row in table_rows(os.path.join(CURRICULUM, "STATUS.md"))}
    facts = orchestrator.load_facts(os.path.join(ROOT, "reference", "regulations-facts.md"))
    exam = table_rows(os.path.join(ROOT, "mock", "regulations-mock.md"))
    today = datetime.date.today().isoformat()

    units = [code for _, _, codes in tasks() for code in codes]
    vetted_units = sum(1 for u in units if status.get(u, {}).get("status", "").strip().lower() == "vetted")
    fact_rows = sum(len(v) for v in facts.values())
    gear3 = [u for u in units if orchestrator.lesson_files(CURRICULUM, u)[3]]

    # ---- per-unit checklist ----
    unit_sections = []
    for letter, title, codes in tasks():
        rows = []
        for code in codes:
            row = status.get(code, {})
            files = orchestrator.lesson_files(CURRICULUM, code)
            number = orchestrator.number_of(code)
            lesson_path = os.path.join(CURRICULUM, "%s.md" % code)
            sources = []
            if os.path.isfile(lesson_path):
                sources = orchestrator.parse_content(open(lesson_path, encoding="utf-8").read())["sources"]
            file_links = ['<a href="%s%s.md">Guided</a>' % (REL["curriculum"], code)]
            if files[1]:
                file_links.append('<a href="%s%s.gear1.md">Fast-track</a>' % (REL["curriculum"], code))
            if files[3]:
                mark = " (tutor draft)" if files[3]["draft"] else ""
                file_links.append('<a href="%s%s.gear3.md">Foundational%s</a>' % (REL["curriculum"], code, esc(mark)))
            note = note_text(row.get("notes", ""))
            rows.append(
                "<tr>"
                "<td class='num'>%s</td>"
                "<td><code>%s</code><br>%s</td>"
                "<td>%s</td>"
                "<td class='src'>%s</td>"
                "<td><a href='%s'>%d</a></td>"
                "<td>%s %s<br>%s</td>"
                "<td class='note'>%s</td>"
                "<td class='check'>%s</td><td class='check'>%s</td><td class='check'>%s</td>"
                "</tr>" % (
                    esc(number), esc(code), esc(objectives.get(code, "")),
                    " · ".join(file_links),
                    source_links(sources),
                    REL["facts"], len(facts.get(code, [])),
                    badge(row.get("gear 2", "")), badge(row.get("gear 3", "")), badge(row.get("status", "")),
                    esc(note) if note else "",
                    checkbox("%s:lesson" % code), checkbox("%s:facts" % code), checkbox("%s:recorded" % code)))
        unit_sections.append(
            "<h3 id='task-%s'>Chapter %d. Task %s. %s <span class='count'>%d units</span></h3>"
            "<div class='scroll'><table class='checklist'><thead><tr>"
            "<th>No.</th><th>Unit</th><th>Lesson files</th><th>Sources (chunk, official)</th><th>Facts</th>"
            "<th>STATUS cells: Gear 2, Gear 3, Status</th><th>Open question</th>"
            "<th>Lesson checked</th><th>Facts checked</th><th>Recorded in STATUS</th>"
            "</tr></thead><tbody>%s</tbody></table></div>"
            % (letter, "ABCDEF".index(letter) + 1, letter, esc(title), len(codes), "".join(rows)))

    # ---- open questions ----
    open_items = []
    for code in units:
        note = note_text(status.get(code, {}).get("notes", ""))
        if note:
            open_items.append("<li><strong>%s</strong> <code>%s</code>: %s</li>" % (
                esc(orchestrator.number_of(code)), esc(code), esc(note)))

    # ---- exam items ----
    exam_rows = []
    for item in exam:
        exam_rows.append(
            "<tr><td class='id'><code>%s</code></td><td>%s <code>%s</code></td><td>%s</td>"
            "<td><a class='ext' href='%s'>%s</a></td><td class='check'>%s</td></tr>" % (
                esc(item["item"]), esc(orchestrator.number_of(item["unit"])), esc(item["unit"]),
                esc(item["stem"]), esc(item["link"]), esc(item["source"]), checkbox("exam:%s" % item["item"])))

    # ---- Foundational files ----
    gear3_rows = []
    for code in gear3:
        info = orchestrator.lesson_files(CURRICULUM, code)[3]
        row = status.get(code, {})
        gear3_rows.append(
            "<tr><td>%s <code>%s</code></td><td><a href='%s%s.gear3.md'>%s.gear3.md</a></td>"
            "<td>%s</td><td>%s</td><td class='check'>%s</td></tr>" % (
                esc(orchestrator.number_of(code)), esc(code), REL["curriculum"], code, esc(code),
                ("tutor draft, version %s" % info["version"]) if info["draft"] else ("version %s" % info["version"] if info["version"] else "no version line"),
                badge(row.get("gear 3", "")), checkbox("%s:gear3" % code)))

    page = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Part 107 course: vetting guide and checklist</title>
<style>
  :root { --ink: #1f2933; --muted: #52606d; --line: #d9e2ec; --soft: #f5f7fa; --accent: #1f5f8b; --ok: #1e7f4f; --warn: #a15c00; }
  body { margin: 0; padding: 24px 16px 64px; font: 15px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; color: var(--ink); background: #fff; }
  main { max-width: 1180px; margin: 0 auto; }
  h1 { font-size: 1.7em; margin: 0 0 4px; }
  h2 { font-size: 1.3em; margin: 40px 0 8px; border-bottom: 1px solid var(--line); padding-bottom: 4px; }
  h3 { font-size: 1.1em; margin: 28px 0 8px; }
  p, li { max-width: 78ch; }
  a { color: var(--accent); }
  a.ext::after { content: " \\2197"; font-size: 0.8em; }
  code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.92em; background: var(--soft); padding: 0 3px; border-radius: 3px; }
  pre { background: var(--soft); padding: 10px 12px; border-radius: 6px; overflow-x: auto; }
  .meta { color: var(--muted); margin: 0 0 16px; }
  .summary { display: flex; flex-wrap: wrap; gap: 12px; margin: 16px 0; }
  .summary div { background: var(--soft); border: 1px solid var(--line); border-radius: 8px; padding: 10px 14px; min-width: 150px; }
  .summary b { display: block; font-size: 1.4em; }
  nav ul { columns: 2; padding-left: 20px; }
  table { border-collapse: collapse; width: 100%; font-size: 0.93em; }
  th, td { border: 1px solid var(--line); padding: 6px 8px; vertical-align: top; text-align: left; }
  thead th { background: var(--soft); position: sticky; top: 0; }
  tbody tr:nth-child(even) { background: #fbfcfd; }
  td.num { white-space: nowrap; font-weight: 600; }
  td.check { text-align: center; }
  td.note { color: var(--warn); max-width: 32ch; }
  td.src { min-width: 19ch; }
  td.src a { white-space: nowrap; }
  td.id { white-space: nowrap; }
  .scroll { overflow-x: auto; }
  .badge { display: inline-block; padding: 0 6px; border-radius: 10px; font-size: 0.85em; white-space: nowrap; border: 1px solid var(--line); }
  .badge.ok { background: #e3f5ea; color: var(--ok); border-color: #b7e2c6; }
  .badge.draft { background: #fff4e5; color: var(--warn); border-color: #f5d9a8; }
  .badge.tutor { background: #eef2ff; color: #3f4fb3; border-color: #c7cff2; }
  .badge.none { background: #f0f0f0; color: #777; }
  .count { color: var(--muted); font-weight: normal; font-size: 0.85em; }
  .tools { margin: 12px 0; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
  button { font: inherit; padding: 4px 10px; border: 1px solid var(--line); border-radius: 6px; background: var(--soft); cursor: pointer; }
  .hide-done tr.done { display: none; }
  @media print { .tools, nav { display: none; } body { padding: 0; } thead th { position: static; } }
</style>
</head>
<body>
<main>
<h1>Part 107 course: vetting guide and checklist</h1>
<p class="meta">Generated __TODAY__ from <a href="__STATUS__">STATUS.md</a>, <a href="__OBJECTIVES__">objectives.md</a>, the <a href="__FACTS__">reference facts</a>, and the <a href="__MOCK__">practice exam</a>. Regenerate with <code>python3 tools/vetting_guide.py</code>. The checkboxes on this page are a working aid saved in your browser; <a href="__STATUS__">STATUS.md</a> is the record.</p>

<div class="summary">
  <div><b>__VETTED__ of __UNITS_N__</b>units vetted in STATUS.md</div>
  <div><b>__FACTS_N__</b>reference facts to check</div>
  <div><b>__EXAM_N__</b>practice exam items to check</div>
  <div><b>__GEAR3_N__</b>Foundational files to check</div>
</div>

<nav><ul>
  <li><a href="#what">What vetting means</a></li>
  <li><a href="#where">Where everything is</a></li>
  <li><a href="#how">How to vet a unit</a></li>
  <li><a href="#record">How to record the result</a></li>
  <li><a href="#open">Open questions and currency findings</a></li>
  <li><a href="#units">Checklist: the 77 units</a></li>
  <li><a href="#exam">Checklist: the practice exam</a></li>
  <li><a href="#gear3">Checklist: Foundational files</a></li>
  <li><a href="#after">After vetting</a></li>
</ul></nav>

<h2 id="what">What vetting means</h2>
<p>A unit is vetted when a reviewer has checked every factual statement in its lesson files, and every one of its reference facts, against the source text in the knowledge base. The tutor teaches only from these files and keys its questions to the reference facts. A wrong fact teaches a wrong rule with confidence, so the check is sentence by sentence and number by number.</p>
<ul>
  <li>Check every number, date, section citation, defined term, and diagram label against the source chunk. Check the arithmetic in the worked example.</li>
  <li>The CFR outranks the Advisory Circular and the study guide. If two sources disagree, follow the CFR and write the conflict in the Notes column of <a href="__STATUS__">STATUS.md</a>. Do not smooth it over in the lesson.</li>
  <li>Review notes go in STATUS.md, never in a lesson file. The tutor reads lesson files verbatim, so a note there reaches a student.</li>
  <li>A unit is vetted when all its lesson files and its reference facts are vetted. Every unit has a Guided lesson; 7 units also have a Foundational file.</li>
  <li>The explanation layer of the knowledge base (the <code>.explained.md</code> companion chunks) is a separate, optional check, described in <a href="__EXPLANATION__">EXPLANATION-LAYER.md</a>.</li>
</ul>
<p>The full rules are in the README under <a href="__README__">Improving the tutor, section Vet</a>. The plan that produced Tasks B to F, with its as-built notes, is <a href="__PLAN__">content-tasks-b-to-f.md</a>.</p>

<h2 id="where">Where everything is</h2>
<div class="scroll"><table>
<thead><tr><th>File</th><th>What it holds</th><th>What to do with it</th></tr></thead>
<tbody>
<tr><td><a href="__STATUS__">curriculum/regulations/STATUS.md</a></td><td>The vetting record: one row per unit with the Gear 1, Gear 2, Gear 3, Reference facts, Status, and Notes cells. The legend at the bottom explains the cells.</td><td>Record every result here. Read a unit's Notes before you start on it.</td></tr>
<tr><td><a href="__OBJECTIVES__">curriculum/regulations/objectives.md</a></td><td>The 77 units, transcribed from the ACS, with the unit numbering rule.</td><td>Confirm that a lesson teaches its ACS element and not a neighbor's.</td></tr>
<tr><td><a href="__CURRICULUM__">curriculum/regulations/&lt;unit&gt;.md</a></td><td>The Guided lesson. <code>.gear1.md</code> and <code>.gear3.md</code> are the Fast-track and Foundational files where they exist. The header lists one <code>source:</code> line per source with its link.</td><td>Check every statement against the sources in the header.</td></tr>
<tr><td><a href="__FACTS__">reference/regulations-facts.md</a></td><td>The answer key: one or more rows per unit with the fact, the answer, the section, and the link.</td><td>Check each answer word for word against the section. Questions are keyed to these rows.</td></tr>
<tr><td><a href="__MOCK__">mock/regulations-mock.md</a></td><td>The 20 fixed practice exam items with keys, rationales, and links.</td><td>Check each item: one correct option, distinct wrong options, a rationale that matches the section.</td></tr>
<tr><td><a href="__KB__">knowledge-base/regulations/</a></td><td>839 chunks: 534 source chunks (<code>kind: source</code>) and 305 companions (<code>.explained.md</code>). The <code>url</code> line in a chunk header is the official text. <a href="__KB_INDEX__">index.md</a> lists them.</td><td>Vet against the source chunk, not the companion. Open the official link when the chunk is cut mid-sentence.</td></tr>
<tr><td><a href="__BUILD__">knowledge-base/BUILD.md</a></td><td>How the knowledge base was built on October 9, 2026, and two currency findings.</td><td>Read once. The findings are repeated below.</td></tr>
<tr><td><a href="__SOURCES__">sources/SOURCES.md</a></td><td>The authoritative references and their precedence.</td><td>Use when two sources disagree.</td></tr>
<tr><td><a href="__PLAN__">docs/plans/content-tasks-b-to-f.md</a></td><td>How Tasks B to F were written, the conventions, and the open questions per batch.</td><td>Background for the 63 lessons written on October 17, 2026.</td></tr>
<tr><td><a href="__INSTRUCTOR_PLAN__">docs/plans/instructor-interface.md</a></td><td>The instructor workspace: how saves raise versions and write STATUS.md.</td><td>Background if the workspace behaves unexpectedly.</td></tr>
<tr><td><a href="__CHECK_INTEGRITY__">tools/check_integrity.py</a>, <a href="__CHECK_LINKS__">check_links.py</a>, <a href="__CHECK_COMPANIONS__">check_companions.py</a></td><td>Structure, links, and companion-chunk checks.</td><td>Run after each batch of changes. They cannot check that a fact is true.</td></tr>
</tbody></table></div>

<h2 id="how">How to vet a unit</h2>
<ol>
  <li>Pick a unit from the checklist below and read its Notes in STATUS.md. The note names the open question the author left.</li>
  <li>Open the lesson. In the workspace: <code>./start.sh --instructor</code>, click Instructor, pick the unit and the Guided tab. By hand: open the file in an editor.</li>
  <li>Open each source named in the file header. The Sources column below links to the knowledge-base chunk and to the official text. Read the source chunk, not its <code>.explained.md</code> companion.</li>
  <li>Check each statement in the lesson: who the rule binds, what it requires, every number, date, and section citation, and each defined term. Check that the worked example follows the rule and that its arithmetic is right. Check that the common misreading is in fact wrong under the source.</li>
  <li>Check the unit's rows in the reference facts: the fact, the answer, the section, and the link. The answer must say what the section says, in the section's numbers.</li>
  <li>If the unit has a Foundational file, check it the same way. A tutor draft is a real lesson file that later students get; your first save removes the draft mark.</li>
  <li>Fix what is wrong, in the lesson and in the facts. A fix in the lesson alone is not enough, because questions are keyed to the facts.</li>
  <li>Record the result as described next, then run <code>python3 tools/check_integrity.py</code> and <code>python3 tools/check_links.py</code>.</li>
  <li>Click Try it as a student, or start the course, and teach the unit once.</li>
</ol>

<h2 id="record">How to record the result</h2>
<ul>
  <li><strong>In the workspace.</strong> Click Save, write a short note on what changed, and answer the question "Is this content vetted against the source text?" Choose Yes, vetted only after every fact, number, and label is checked. The save raises the file's version and writes <code>vN vetted</code> or <code>vN edited</code> into the unit's Gear cell, with a dated note.</li>
  <li><strong>By hand.</strong> Edit the file, then set the unit's Gear 2 cell (or Gear 3) to <code>vN vetted</code>, where N is the <code>version:</code> line in the file. Keep the version line; the course owns it.</li>
  <li><strong>The facts and the status.</strong> The workspace does not edit the Reference facts or Status columns. Write <code>vetted</code> in Reference facts when every row for the unit is checked, and set Status to <code>vetted</code> when all the unit's files and its facts are vetted. Add a dated note.</li>
  <li><strong>Conflicts.</strong> When a source conflicts with the CFR, follow the CFR in the lesson and write the conflict in the Notes column with the sections involved.</li>
</ul>

<h2 id="open">Open questions and currency findings</h2>
<p>Each note below is the author's open question for that unit, copied from the Notes column of STATUS.md. Two are currency findings from the knowledge-base build: 107.5 is reserved since November 3, 2025 and falsification now sits in 14 CFR 3.401 to 3.405, and 107.1(b) no longer names part 101. Later rules cite the old section in places; the notes say where.</p>
<ul>
__OPEN__
</ul>

<h2 id="units">Checklist: the 77 units</h2>
<p>Suggested order: the practice exam and the reference facts first, because they decide readiness; then Task A and the units with open questions; then Tasks B to F in course order. Tick a box when that part is checked and recorded.</p>
<div class="tools">
  <span id="progress"></span>
  <label><input type="checkbox" id="hide-done"> Hide rows with all three boxes ticked</label>
  <button id="clear" type="button">Clear all ticks on this page</button>
</div>
__UNITS__

<h2 id="exam">Checklist: the practice exam</h2>
<p>Twenty items in <a href="__MOCK__">regulations-mock.md</a>. For each: the keyed answer is right, the two wrong options are wrong and distinct, the rationale matches the section, and the link opens the section. Stems and options must not contain the pipe character.</p>
<div class="scroll"><table class="checklist">
<thead><tr><th>Item</th><th>Unit</th><th>Stem</th><th>Source</th><th>Checked</th></tr></thead>
<tbody>__EXAM__</tbody></table></div>

<h2 id="gear3">Checklist: Foundational files</h2>
<p>Seven units have a Foundational file. A tutor draft is a file the tutor wrote from the Guided lesson; later students get it as written. Review it for the same facts as the Guided lesson, and for whether it teaches the point at all.</p>
<div class="scroll"><table class="checklist">
<thead><tr><th>Unit</th><th>File</th><th>Form</th><th>STATUS Gear 3 cell</th><th>Checked</th></tr></thead>
<tbody>__GEAR3__</tbody></table></div>

<h2 id="after">After vetting</h2>
<ol>
  <li>Run the checks: <code>python3 tools/check_integrity.py</code> (no <code>--allow-incomplete</code>; every unit has content) and <code>python3 tools/check_links.py</code>.</li>
  <li>Regenerate this page: <code>python3 tools/vetting_guide.py</code>. The summary at the top counts the units whose Status cell says vetted.</li>
  <li>Run the course with a real model from Task A to the practice exam: <code>./start.sh</code>.</li>
  <li>Package: <code>python3 tools/package.py</code>. It refuses a course that fails the integrity check.</li>
  <li>Commit the changed files and any new images, with a message that names the units vetted.</li>
</ol>
</main>
<script>
(function () {
  var KEY = "part107-vetting-guide";
  var state = {};
  try { state = JSON.parse(localStorage.getItem(KEY) || "{}") || {}; } catch (e) { state = {}; }
  var boxes = Array.prototype.slice.call(document.querySelectorAll("input[type=checkbox][data-key]"));
  var progress = document.getElementById("progress");
  function save() { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} }
  function update() {
    var done = 0;
    boxes.forEach(function (b) { if (b.checked) done++; });
    progress.textContent = done + " of " + boxes.length + " boxes ticked on this page";
    Array.prototype.forEach.call(document.querySelectorAll("table.checklist tbody tr"), function (tr) {
      var own = Array.prototype.slice.call(tr.querySelectorAll("input[type=checkbox][data-key]"));
      tr.classList.toggle("done", own.length > 0 && own.every(function (b) { return b.checked; }));
    });
  }
  boxes.forEach(function (b) {
    if (state[b.dataset.key]) b.checked = true;
    b.addEventListener("change", function () { state[b.dataset.key] = b.checked; save(); update(); });
  });
  document.getElementById("hide-done").addEventListener("change", function (e) {
    document.body.classList.toggle("hide-done", e.target.checked);
  });
  document.getElementById("clear").addEventListener("click", function () {
    state = {}; save(); boxes.forEach(function (b) { b.checked = false; }); update();
  });
  update();
})();
</script>
</body>
</html>
"""
    fill = {
        "__TODAY__": today, "__VETTED__": str(vetted_units), "__UNITS_N__": str(len(units)),
        "__FACTS_N__": str(fact_rows), "__EXAM_N__": str(len(exam)), "__GEAR3_N__": str(len(gear3)),
        "__OPEN__": "\n".join(open_items) or "<li>None recorded.</li>",
        "__EXAM__": "".join(exam_rows), "__GEAR3__": "".join(gear3_rows),
    }
    # The unit tables go in last, so their own placeholders are not touched.
    for key, value in fill.items():
        page = page.replace(key, value)
    for key, value in REL.items():
        page = page.replace("__%s__" % key.upper(), value)
    page = page.replace("__UNITS__", "\n".join(unit_sections))
    with open(OUT, "w", encoding="utf-8") as handle:
        handle.write(page)
    print("wrote %s: %d units (%d vetted), %d facts, %d exam items, %d Foundational files"
          % (os.path.relpath(OUT, ROOT), len(units), vetted_units, fact_rows, len(exam), len(gear3)))


if __name__ == "__main__":
    build()
