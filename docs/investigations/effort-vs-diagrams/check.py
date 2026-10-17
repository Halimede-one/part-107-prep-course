#!/usr/bin/env python3
"""Render and measure the diagrams that run.py collected.

For each diagram in svg/: draws it in headless Chrome (Playwright, system
Chrome), measures every label's box on screen, and records the labels that
reach past the drawing's edge (clipped when shown) and the pairs of labels
that overlap. Writes png/<run>.png, one comparison sheet per request in
sheets/<task>.png (effort levels across, runs down), and adds the measurements
to results.json. Prints a Markdown table for the report.

Run from the course folder after run.py:  python3 docs/investigations/effort-vs-diagrams/check.py
"""

import base64
import html
import json
import os

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
EFFORTS = ["low", "medium", "default", "max"]

MEASURE = """() => {
  const svg = document.querySelector('svg');
  const frame = svg.getBoundingClientRect();
  const boxes = Array.from(svg.querySelectorAll('text')).map(t => {
    const r = t.getBoundingClientRect();
    return { text: t.textContent.trim(), left: r.left, top: r.top, right: r.right, bottom: r.bottom };
  }).filter(b => b.text && b.right > b.left);
  const outside = boxes.filter(b => b.left < frame.left - 1 || b.top < frame.top - 1 ||
                                    b.right > frame.right + 1 || b.bottom > frame.bottom + 1).map(b => b.text);
  const overlaps = [];
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i], b = boxes[j];
      const w = Math.min(a.right, b.right) - Math.max(a.left, b.left);
      const h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      const smaller = Math.min((a.right - a.left) * (a.bottom - a.top), (b.right - b.left) * (b.bottom - b.top));
      if (w > 0 && h > 0 && w * h > 0.2 * smaller) { overlaps.push([a.text, b.text]); }
    }
  }
  return { width: svg.getAttribute('width'), height: svg.getAttribute('height'),
           viewBox: svg.getAttribute('viewBox'), labels: boxes.length, outside: outside, overlaps: overlaps };
}"""


def main():
    with open(os.path.join(HERE, "results.json"), encoding="utf-8") as handle:
        results = json.load(handle)
    os.makedirs(os.path.join(HERE, "png"), exist_ok=True)
    os.makedirs(os.path.join(HERE, "sheets"), exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 900, "height": 700}, device_scale_factor=2)
        for record in results:
            path = os.path.join(HERE, "svg", record["run"] + ".svg")
            if not os.path.isfile(path):
                continue
            with open(path, encoding="utf-8") as handle:
                svg = handle.read()
            page.set_content("<html><body style='margin:16px;background:#fff'>%s</body></html>" % svg)
            record["measured"] = page.evaluate(MEASURE)
            page.locator("svg").first.screenshot(path=os.path.join(HERE, "png", record["run"] + ".png"))
        for task in sorted({r["task"] for r in results}):
            cells = []
            for sample in sorted({r["sample"] for r in results}):
                row = []
                for effort in EFFORTS:
                    r = next((x for x in results if x["task"] == task and x["effort"] == effort and x["sample"] == sample), None)
                    png = os.path.join(HERE, "png", r["run"] + ".png") if r else ""
                    m = (r or {}).get("measured") or {}
                    caption = "%s, run %d: %s s" % (effort, sample, (r or {}).get("seconds"))
                    if r and r.get("error"):
                        caption += " | " + r["error"]
                    elif m:
                        caption += " | clipped %d, overlaps %d, unsupported %s" % (
                            len(m["outside"]), len(m["overlaps"]), ",".join(r["unsupported_numbers"]) or "none")
                    # Inline, because a page made with set_content may not load file:// images.
                    image = ("<img src='data:image/png;base64,%s' style='max-width:100%%'>" % base64.b64encode(
                        open(png, "rb").read()).decode("ascii")) if os.path.isfile(png) else "<p>no diagram</p>"
                    row.append("<td><div class='c'>%s</div>%s</td>" % (html.escape(caption), image))
                cells.append("<tr>%s</tr>" % "".join(row))
            sheet = ("<html><body style='font:13px sans-serif;margin:10px;background:#fff'><h3>%s</h3>"
                     "<table style='table-layout:fixed;width:1600px;border-collapse:collapse'>%s</table>"
                     "<style>td{width:400px;vertical-align:top;border:1px solid #ccc;padding:6px}.c{margin-bottom:6px}</style>"
                     "</body></html>") % (task, "".join(cells))
            sheet_page = browser.new_page(viewport={"width": 1640, "height": 900})
            sheet_page.set_content(sheet)
            sheet_page.wait_for_timeout(300)
            sheet_page.screenshot(path=os.path.join(HERE, "sheets", task + ".png"), full_page=True)
            sheet_page.close()
        browser.close()
    with open(os.path.join(HERE, "results.json"), "w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=1)

    print("| Run | Seconds | Output tokens | Thinking | Mode | Lines removed | Clipped labels | Overlapping labels | Unsupported numbers |")
    print("|---|---|---|---|---|---|---|---|---|")
    for r in results:
        m = r.get("measured") or {}
        print("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["run"], r.get("seconds"), r.get("output_tokens"), r.get("thinking_tokens"), r.get("mode", r.get("error", "")),
            r.get("lines_removed", ""), len(m.get("outside", [])) if m else "", len(m.get("overlaps", [])) if m else "",
            ", ".join(r.get("unsupported_numbers", [])) or ("none" if m else "")))


if __name__ == "__main__":
    main()
