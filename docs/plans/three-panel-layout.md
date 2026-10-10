# Three-panel layout: implementation plan

Status: approved and implemented, October 10, 2026. Decisions: redraw the tree at the panel width (Option A), remember the widths, full window width, no change to the "Sent to tutor" log. See "As built" at the end for the changes made during implementation.

## Goal

Move the progress card out of the right column into a new left panel. The page then has three panels side by side: progress, lesson, and tutor chat. The user can drag the two vertical dividers between the panels to change their widths.

## Current layout

- `ui/index.html`: `main.layout` holds two grid columns: `section.content` (the lesson) and `div.side`.
- `div.side` holds `aside.map` (the progress card) above `section.chat`.
- `ui/styles.css`: `.layout` is a grid of `1fr 360px` with a max width of 1120 px, centered.
- `.side` is sticky and fills the viewport height. The chat takes the space that the progress card does not use.
- The tree window (`.tree-window`) has a fixed height of 240 px.
- `ui/course-tree.js` draws the sidebar tree at a fixed SVG width of 316 px (`METRICS.sidebar.width`). Labels wrap to that width.
- Below 820 px the layout stacks into one column.

## Proposed layout

```
+-----------+---+--------------------------+---+------------+
| Progress  | | | Lesson                   | | | Ask the    |
| (sticky)  | | | (scrolls with the page)  | | | tutor      |
| tree fills| | |                          | | | (sticky)   |
| the panel | | |                          | | |            |
| key       | | |                          | | |            |
| readiness | | |                          | | |            |
+-----------+---+--------------------------+---+------------+
            divider                        divider
```

- The layout uses the full window width. The 1120 px max width goes away.
- Grid columns: `var(--left) 12px minmax(0, 1fr) 12px var(--right)`.
- Default widths: left 340 px, right 360 px. The lesson takes the rest.
- Both side panels are sticky and as tall as the viewport minus the top bar.
- In the progress panel, the tree window fills the free height. The picker, task name, key, and readiness stay below it at their natural height. The tree window keeps a minimum height of 240 px.
- The chat panel keeps its current inner layout. It now has the full column height.
- Below 820 px: one column, dividers hidden, panels not sticky. The lesson stays first, then progress, then chat, as today.

## The dividers

Each divider is an element between two panels:

```html
<div class="divider" role="separator" aria-orientation="vertical"
     aria-label="Resize the progress panel" tabindex="0" data-side="left"></div>
```

- Mouse and touch: pointer events with pointer capture. A drag sets `--left` or `--right` on `main.layout`.
- Keyboard: the divider takes focus with Tab. ArrowLeft and ArrowRight move it by 20 px. This follows the ARIA window splitter pattern. `aria-valuenow` holds the panel width in px.
- Limits: progress panel at least 280 px, chat panel at least 300 px, lesson at least 400 px. A drag past a limit stops at the limit.
- A window resize applies the same limits again, so the lesson never goes below 400 px while the window is wide enough.
- Look: a 12 px hit area with a 2 px line in `--line`. The line turns `--accent` on hover, focus, and drag. The cursor is `col-resize`.
- The code goes in a new file, `ui/panels.js` (about 50 lines). It does not depend on `app.js`.

## The tree width

The tree SVG is 316 px wide. A resizable panel makes this a problem in two directions:

- A narrower panel clips the labels, because the tree window hides horizontal overflow.
- A wider panel leaves blank space to the right of the tree.

Two options:

- **Option A (recommended): draw the tree at the panel width.** `CourseTree.render` takes an optional `opts.width` that replaces `METRICS.sidebar.width`. `app.js` passes the tree window's inner width. A `ResizeObserver` on the tree window draws the tree again when its width changes, and keeps the scroll position. About 10 changed lines in `course-tree.js` and `app.js`. The intake tree does not change.
- **Option B: keep the fixed 316 px width.** No change to `course-tree.js`. The progress panel minimum becomes 360 px so the tree is never clipped. A wider panel shows blank space beside the tree.

A known side effect of Option A: a redraw during a resize closes an open picker. This is the same as today when the state changes.

## Decisions for you

1. Tree width: Option A or Option B. I recommend Option A.
2. Remember the divider positions after a page reload, in `localStorage`. I recommend yes. It is about 6 lines. Without it, each reload goes back to the default widths.
3. Full window width (no 1120 px max). I recommend yes. With three panels, a 1120 px page leaves the lesson about 380 px wide.
4. The "Sent to tutor" log below the panels keeps its 1120 px max width. I propose no change, because it is a debug panel.

## Files to change

| File | Change |
|---|---|
| `ui/index.html` | Move `aside.map` to before `section.content`. Remove the `div.side` wrapper. Add two divider elements. Load `panels.js`. |
| `ui/styles.css` | New `.layout` grid. Sticky and height rules move from `.side` to `.map` and `.chat`. Tree window fills the panel. Divider styles. Narrow-screen rules. |
| `ui/panels.js` | New. Drag, keyboard, limits, and (decision 2) `localStorage`. |
| `ui/course-tree.js` | Option A only: `opts.width` in `svg()`. |
| `ui/app.js` | Option A only: pass the width in `renderMap`, and the `ResizeObserver`. |
| `tests/fixtures/panels.html`, `tests/test_layout.py` | New browser test (see below). |

No server, prompt, or ledger change.

## Testing approach

### Automatic test (headless Chrome)

A new fixture page, `tests/fixtures/panels.html`, loads the real `index.html` markup parts, `styles.css`, and `panels.js`. It runs the checks and writes PASS, or one line per failed check, into `#result`. `tests/test_layout.py` loads it the same way as `tests/test_markdown.py` does. The test sets `--window-size=1600,1000`, because the headless default of 800 x 600 gives the stacked layout.

Checks:

1. At the start, the three panels are side by side, at the default widths.
2. A drag of the left divider by +100 px makes the progress panel 100 px wider and the lesson 100 px narrower.
3. A drag of the right divider by -100 px makes the chat panel 100 px wider.
4. A drag far past each limit stops at 280 px (progress), 300 px (chat), and 400 px (lesson).
5. ArrowRight on a focused divider moves it by 20 px. `aria-valuenow` changes to match.
6. Option A: after a resize, the tree SVG width equals the tree window's inner width.
7. Decision 2: a second page load shows the stored widths.

### Existing tests

Run `python3 -m unittest discover -s tests -v` before and after the change. All tests must pass. The chat drawing fixture stubs the elements that `app.js` reads. If Option A adds a read, the stub gets it too.

### Manual check

1. Start the app with `./start.sh`.
2. Take headless Chrome screenshots at 2000, 1400, and 800 px wide. Compare them with the screenshot from this request.
3. Drag each divider with the mouse. Check that the tree labels wrap to the new width and that the lesson text reflows.
4. Tab to each divider and use the arrow keys.
5. Check the intake page. It must not change.

## As built

The implementation follows the plan, with these changes:

- **Minimum widths.** Progress panel 300 px (not 280), chat panel 300 px, lesson 400 px. The limits are in `MIN` and `MIN_LESSON` at the top of `ui/panels.js`.
- **Tree scroll target.** A tall tree window cannot center a unit near either end of the course. Before the fix, `offCurrent` then reported "off current" and showed "Back to current unit" at once. `targetTop` in `ui/course-tree.js` now stops at the furthest scroll position.
- **Picker speed buttons.** At 300 px the three buttons did not fit on one line. `.tree-pick-gears` now wraps.
- **Progress panel overflow.** With the picker open on a short, narrow panel, the content was taller than the panel. `.map` now scrolls (`overflow-y: auto`) in that case.
- **Test stub for ResizeObserver.** Headless Chrome renders no frames when it dumps the DOM, so `ResizeObserver` callbacks never run there. `tests/fixtures/panels.html` replaces `ResizeObserver` with a stub and calls the callback itself. A screenshot in a real browser frame confirmed the redraw after five ArrowRight presses.
- **Extra automatic checks:** the one-column layout at 800 px, the tree on the current unit at start, and the scroll position kept across a redraw.

Tests: `python3 -m unittest discover -s tests` runs 138 tests, all pass (1 skip, pdftotext). Each new check failed when the code it covers was broken on purpose.
