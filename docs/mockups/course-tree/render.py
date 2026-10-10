"""Render the course-tree mockup to PNG screenshots and export the SVGs.

Run from the repo root:  python3 docs/mockups/course-tree/render.py

Needs python3 with playwright and a Chromium it can launch (the bundled one, or
Google Chrome). Writes to docs/mockups/course-tree/screenshots/ and overwrites
course-tree.svg and course-window.svg next to this script.
"""

import os
import re
import sys

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = "file://" + os.path.join(HERE, "index.html")
SHOTS = os.path.join(HERE, "screenshots")

# (file stem, query string, color scheme, selector to clip to or None for the viewport)
SHOTS_TO_TAKE = [
    ("sidebar-mid-light", "scene=sidebar&state=mid", "light", None),
    ("sidebar-mid-dark", "scene=sidebar&state=mid", "dark", None),
    ("card-mid-light", "scene=sidebar&state=mid", "light", "#progress-card"),
    ("card-mid-dark", "scene=sidebar&state=mid", "dark", "#progress-card"),
    ("card-fresh-light", "scene=sidebar&state=fresh", "light", "#progress-card"),
    ("card-late-light", "scene=sidebar&state=late", "light", "#progress-card"),
    ("card-boundary-light", "scene=sidebar&state=fresh&steps=8", "light", "#progress-card"),
    ("card-taskd-light", "scene=sidebar&state=fresh&steps=48", "light", "#progress-card"),
    ("card-pick-light", "scene=sidebar&state=mid&pick=UA.I.B.K16:2", "light", "#progress-card"),
    ("intake-pick-light", "scene=intake&state=mid&pick=UA.I.B.K14:2", "light", None),
    ("intake-fresh-light", "scene=intake&state=fresh", "light", None),
    ("intake-mid-light", "scene=intake&state=mid", "light", None),
    ("intake-fresh-dark", "scene=intake&state=fresh", "dark", None),
    ("full-mid-light", "scene=full&state=mid", "light", "#full-tree"),
    ("full-mid-dark", "scene=full&state=mid", "dark", "#full-tree"),
]

# (file name, query string, selector of the <svg> to export)
SVGS_TO_EXPORT = [
    ("course-tree.svg", "scene=full&state=mid", "#full-tree svg"),
    ("course-window.svg", "scene=sidebar&state=mid", "#course-tree svg"),
]


def launch(p):
    try:
        return p.chromium.launch()
    except Exception:  # no bundled Chromium: fall back to an installed Chrome
        return p.chromium.launch(channel="chrome")


def main():
    os.makedirs(SHOTS, exist_ok=True)
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
        page.on("pageerror", lambda err: print("page error:", err, file=sys.stderr))
        page.on("console", lambda msg: print("console:", msg.text, file=sys.stderr) if msg.type in ("error", "warning") else None)
        for stem, query, scheme, selector in SHOTS_TO_TAKE:
            page.emulate_media(color_scheme=scheme)
            page.goto(PAGE + "?" + query)
            page.wait_for_function("window.__treeReady === true")
            path = os.path.join(SHOTS, stem + ".png")
            if selector:
                page.locator(selector).screenshot(path=path)
            else:
                page.screenshot(path=path)
            print("wrote", os.path.relpath(path, HERE))
        page.emulate_media(color_scheme="light")
        for name, query, selector in SVGS_TO_EXPORT:
            page.goto(PAGE + "?" + query)
            page.wait_for_function("window.__treeReady === true")
            svg = page.locator(selector).evaluate("node => node.outerHTML")
            if name == "course-window.svg":  # crop to the span the sidebar window shows
                win = page.locator("#course-tree").evaluate("n => ({top: n.scrollTop, h: n.clientHeight})")
                svg = re.sub(r'viewBox="0 0 (\d+) [\d.]+" width="\d+" height="[\d.]+"',
                             lambda m: 'viewBox="0 %d %s %d" width="%s" height="%d"' % (win["top"], m.group(1), win["h"], m.group(1), win["h"]), svg, count=1)
            path = os.path.join(HERE, name)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write('<?xml version="1.0" encoding="UTF-8"?>\n' + svg + "\n")
            print("wrote", name)
        browser.close()


if __name__ == "__main__":
    main()
