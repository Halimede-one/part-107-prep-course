# Course tree mockup

Status: implemented in the shell on October 10, 2026. `ui/course-tree.js` is a
copy of `course-tree.js` here; the markup and rules went into `ui/index.html`,
`ui/styles.css` and `ui/app.js`, and the server gained `title`, `attempts` and
`written` per unit in `/api/state` and the `goto` request. This folder stays as
the design record; the plan below is the plan as built.

A mockup of the redesigned progress indicator: the course drawn as a tree that
grows from the bottom (Start) to the top (the practice exam and the readiness
gate), with the gears as parallel lanes through every unit. Nothing here is
wired to the server; the mockup runs on sample states.

## Files

| File | What it is |
|---|---|
| `index.html` | The mockup page. Three scenes: the course shell with the tree in the progress card, the intake page with the whole course in a panel beside the card, and the full tree as a document. |
| `course-tree.js` | The layout and drawing module, copied as `ui/course-tree.js`. One `layout()` serves all three placements; the sidebar and the full tree each have a metrics entry, and the intake panel uses the full tree's. |
| `course-tree.css` | The rules to add to `ui/styles.css`: the three-unit window, the key, the recenter button, the intake panel. |
| `units.js` | The 77 units with titles, generated from `curriculum/regulations/objectives.md` by `make_units.py`. Do not edit by hand. |
| `states.js` | Three sample student states (fresh, mid-course, late) in the shape of `/api/state`, and a `step()` that masters the current unit and moves on. |
| `mockup.js` | Wiring for the mockup page only: scene and state selection, the Step button, the recenter button. |
| `render.py` | Renders the screenshots and exports the two SVG files with Playwright. |
| `course-tree.svg` | The whole course with the mid-course sample state, exported from the full-tree scene. |
| `course-window.svg` | The sidebar window with the same state: the span the card shows, cropped from the full tree. |
| `screenshots/` | Light and dark renders of every scene and state, including the task-boundary cases. |
| `concepts/` | The three candidate concepts from the design panel (see below), for comparison. Delete after the decision. |

## How to view it

Open `index.html` in a browser. It works from `file://`, no server needed. The
bar at the bottom switches the scene and the sample state. In the sidebar scene,
Step masters the current unit and moves to the next one, which shows the tree
scrolling up. The window itself scrolls with the mouse wheel; a Back to current
unit button appears when the current unit is out of view. Your operating
system's dark mode applies.

Direct links: `index.html?scene=sidebar|intake|full&state=fresh|mid|late`.
`&steps=N` advances the sample state N units first (`state=fresh&steps=8` puts
the student on the first unit of task B). `&bare=1` hides the mockup bar.

Regenerate from the repo root:

```bash
python3 docs/mockups/course-tree/make_units.py   # units.js from objectives.md
python3 docs/mockups/course-tree/render.py       # screenshots and the SVG files
```

`render.py` needs Python with Playwright and a Chromium it can launch.

## The design

The course is one trunk, read from the bottom up. Each unit is a node on the
trunk. Between two nodes run the three speed lanes of the upper unit. Gear 1
(Fast-track) is the trunk itself, the most direct route. Gear 2 (Guided) leaves
the trunk to the right, runs parallel to it, and rejoins at the node. Gear 3
(Foundational) runs further right, the longest detour. Every unit shows all
three lanes as light-grey tracks. The student's route is colored; lanes not
taken stay faint. Where a speed is not written yet for a unit (today only two
units have foundational content), the lane is still drawn as a possible track;
the picker names it and disables it.

| State | Mark |
|---|---|
| Not started | Hollow node, three faint lanes |
| Learning | Amber node |
| Mastered | Green node |
| Current unit | Blue ring around the node, the tag "now, gear N", and a pulsing blue dot on the lane in use (static under reduced motion) |
| Set aside (parked) | Hollow node with a dashed red outline, a red pennant, the tag "set aside" |
| Needs attention, not parked | A red dot on the node, the tag "needs attention" |
| Lane taken | Colored in the unit's state hue: green when mastered, amber otherwise. Red stays on the node and the tag |
| Lane not written yet | Drawn like any other track; the picker names it and disables it |
| New student, intake page | Every track, link, hollow node and knot in a soft green: the whole course open ahead |
| Attempts on a lane | One attempt: thin, half opaque. Two: thicker, three quarters. Three or more: thickest, solid. The count is attempts at that gear, from the ledger |
| Mastered at a deeper gear | The tag "mastered at gear N" |
| Learning, not current | The tag "learning" |
| Sub-element | Smaller node, shorter code, indented title |
| Task boundary | A hollow knot on the trunk, a hairline, and the task name. The knot's hover text explains the review check |
| Start, practice exam, readiness gate | A ground line at the bottom; two square gates at the top with their criteria, filled green when passed |

Every node has hover text with the code, title, state, lanes, and attempts, so
nothing is carried by color alone. Codes and titles are annotated on the tree
in the sidebar and full views. Colors come from the page's tokens when the SVG
is embedded, with the course palette as the fallback when the SVG stands alone.

A lane is colored by the unit's state, not by the result at that gear: a missed
gear-1 attempt on a unit later mastered at gear 2 draws green. The data has no
result per attempt, so the key says "color: the unit's state; weight: attempts".

### The three placements

1. Sidebar. The progress card holds a window of 240 px, about three units
   plus the room for two task rows. The window frames three rows: the unit
   above the current one, the current unit, and the unit below it, with any
   task-boundary row between them, so the past and the next unit stay in view
   across a boundary and at task D, which has a boundary on both sides.
   The window scrolls, with fades at both edges to show that the tree goes on,
   and it glides up one unit each time the student advances. The task name sits
   under the window, then the key, then the readiness text the card already has.
2. Intake page. The whole course, 77 units, stands in a panel beside the
   intake card at the same scale as the full tree, with every code and title.
   The panel stays in place while the page scrolls and scrolls on its own; it
   opens centred on the current unit, which for a new student is the first unit
   at the bottom, above Start. A returning student sees their route. Hidden
   below 1160 px of viewport width.
3. Full tree. The same layout at document scale, exported as `course-tree.svg`.

### Navigating with the tree

Click a lane, or a unit's node, in the sidebar window or in the intake panel.
Tab reaches every node, and Enter opens it. A picker appears under the window
(in the sidebar) or at the foot of the panel (on the intake page) with the
unit, its state, the speeds written for it, and the three speeds as buttons,
the clicked lane preselected. The action reads Review for a unit the student
has seen, Start here for one they have not, and Switch speed for the current
unit. In the mockup, Review makes the unit current at that speed and the window
glides to it; on the intake page it opens the course at that unit. In the shell
this becomes a request to the server (see the plan).

## Data the tree needs from `/api/state`

Everything is drawn from the existing payload plus three fields per unit:

- `title`: the unit's ACS title. The server already has this map in
  `orchestrator.py` (`objectives`); the ledger's `state()` can add it.
- `attempts`: attempts per gear, for example `{"1": 1, "2": 2}`, counted from
  the ledger's attempts table, which records the gear of every attempt.
- `written`: whether the unit's content file exists. Today 14 of the 77 units
  have one; the picker disables Start and Review for the others and says so.

`available_gears` decides which speeds the picker offers.

The task names come from a small map (letter to name), which the mockup takes
from `units.js` and the shell would take from the server or keep in `app.js`.
Lettered sub-elements are recognised by their code (K21a), so no field is
needed for them.
No other data is invented. The tree does not claim time spent, scores per unit,
or which boundary re-checks happened.

## The design panel

Three independent concepts were drawn and judged by three reviewers before
this build: a transit map (parallel lanes, like a rail diagram), a vine (organic
bows, leaflets for sub-elements), and a worn trail (switchbacks, waypoints,
status words). The judges tied them at 72 points each and each judge named a
different winner, so this mockup is a synthesis:

- From the transit concept: the lane geometry (leave, run parallel, rejoin).
- From the trail concept: the code on the node's own line with the title below
  it, the status words driven by data, the dot on the lane in use.
- From the vine concept: the key under the window, the hollow knots at task
  boundaries, the page tokens for color.

Their renders are in `concepts/`. The warnings every judge raised are handled:
text is measured with a canvas rather than estimated, faint lanes use the muted
token so they survive dark mode, the window reserves a scrollbar gutter, the
three-row rule holds at task boundaries, and the invented gear-3 waypoints were
dropped (the data has no sub-steps).

## Implementation plan (as built)

1. `ledger.py`: add `title` and `attempts` to `state()`. Verify: a test in
   `tests/` asserts both fields for a unit with attempts at two gears.
2. `server.py` and `orchestrator.py`: a `goto` request, `{"type": "goto",
   "unit": ..., "gear": ...}`, that records the gear on the ledger
   (`set_gear`), makes the unit current, and teaches it at that gear with a
   review framing. The server caps the gear at the deepest written one. After
   the review the course resumes at the earliest unmastered unit, as it does
   today. Verify: a test posts `goto` and asserts the ledger's current unit and
   gear, and that the next block is a lesson for that unit at that gear.
3. `ui/index.html` and `ui/styles.css`: replace the grid markup in the progress
   card with the window, the recenter button, and the key; add the tree panel
   to the intake overlay (the overlay's padding moves onto the card, and the
   panel sticks beside it with its own scroll); add the rules from
   `course-tree.css`, and the picker markup under the window and at the foot
   of the panel. Remove the placeholder note.
4. `ui/app.js`: add the functions from `course-tree.js`, and from `mockup.js`
   the pieces the shell owns (the sidebar render with the task-name line, the
   key glyph, the recenter button and its hold during a glide, the picker).
   The picker's Review posts the `goto` request and renders the reply. Make `renderMap`
   call `render(..., "sidebar", animate)` and, while the intake is shown,
   `render(..., "full")` into the panel. `renderReadiness` stays as it is. The SVG keeps the
   same height from turn to turn, so the scroll position carries over and the
   glide starts from where the window was. Verify: a Playwright check that
   advancing a unit lowers `scrollTop` by one unit height and that the recenter
   button appears after a manual scroll.
5. Light and dark mode and reduced motion by eye, with the screenshots from
   `render.py` as the reference.

Testing approach: `layout()` is a pure function of the state and the metrics,
so it can be unit-tested in isolation (row count, bottom-to-top order, lanes
per unit, the three-row window span). The scroll behavior and the picker are
tested through the browser: a click on a lane opens the picker with that speed
pressed, an unwritten speed is disabled, and Review changes the current unit
and gear.

## Review pass

Four reviewers (requirements, visual and accessibility, code, layout math)
checked the mockup and a skeptic verified each finding. Fixed: a word-wrap bug
that garbled the end of truncated titles, the task C label running past the
sidebar edge, the window too short for task D, the keyboard focus ring hidden by
the edge fades, the "Not started" key swatch too faint to see, a parked
sub-element getting the wrong mark, the recenter button flashing during a
glide, and the sample state's readiness text not following a step. Refuted: one
finding about the text size of the former compact margin tree. Known and left as is: the
amber "learning" tag is just under the AA contrast ratio for small text in
light mode; the trunk across a task boundary stays grey after the student
passes it (the panel's judges disagreed on whether it should color).

After the review the intake page changed on request: the compact margin tree
(200 px wide, no titles) was replaced by the full-scale tree in a panel that
scrolls on its own, and the compact variant was removed from the code. Then,
also on request, every unit got all three speed lanes, the intake tree turned
green for a new student, and the picker for navigating by unit and speed was
added.

## Open questions for the review

1. Route color. The lanes take the unit's state hue (green or amber). The
   alternative is one trail color for every route, with the state on the node
   only.
2. Window height. About three units. Taller shows more context but weakens
   the "past, current, next" reading.
3. The key. One judge would drop it, since the tags and hover text explain
   every mark, and give the card the space back.
4. Task boundaries. The review check is explained only in the knot's hover
   text. A second line under the task name ("re-check first, then set-aside
   units return") is the alternative.
5. The intake panel opens centred on the current unit. The alternative is to
   open at Start every time.
6. Jumping ahead. The picker allows any unit, including ones not started
   (Start here). Limit it to units the student has seen?
7. The foundational lane is drawn for every unit although only two units have
   that content today. Keep all three lanes everywhere, or draw the unwritten
   lane dotted?
