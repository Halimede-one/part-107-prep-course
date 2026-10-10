// Course tree: the progress indicator drawn as a bottom-to-top tree flow.
//
// One layout serves three placements (sidebar window, intake panel, full
// document) through a metrics table. render(container, state, tasks, variant,
// animate, opts) builds the SVG from a /api/state payload, whose units carry
// title, attempts (per gear) and written (content exists). No libraries; the
// DOM it touches is a canvas for text measuring, the container's innerHTML,
// scroll position and focus, and matchMedia for reduced motion.
(function () {
  "use strict";

  // ---- metrics: every number the layout uses, per placement ---------------
  var METRICS = {
    sidebar: {
      width: 316, trunkX: 22, laneGap: 16, labelX: 76,
      unitH: 58, subH: 50, taskH: 30, startH: 34, gateH: 52, padTop: 10, padBottom: 10,
      nodeInset: 14, nodeR: 5.5, subR: 3.5, ringGap: 3.5, knotR: 4,
      laneW: [1, 2, 2.5, 3], laneOpacity: [1, 0.5, 0.75, 1],
      font: 13, codeFont: 11, labelLines: 2
    },
    full: {
      width: 420, trunkX: 24, laneGap: 18, labelX: 84,
      unitH: 58, subH: 50, taskH: 30, startH: 34, gateH: 52, padTop: 10, padBottom: 10,
      nodeInset: 14, nodeR: 5.5, subR: 3.5, ringGap: 3.5, knotR: 4,
      laneW: [1, 2, 2.5, 3], laneOpacity: [1, 0.5, 0.75, 1],
      font: 13, codeFont: 11, labelLines: 2
    }
  };

  // ---- layout -----------------------------------------------------------
  // Rows run top-down in SVG space: the two gates, then the units from last to
  // first with a task row before each task's first unit, then the start.
  // Lettered sub-elements (K21a) are recognised by their code; no extra field is needed.
  function isSub(u) { return /K\d+[a-d]$/.test(u.id); }

  // The title as shown: the ACS text without its lettered prefix or final period.
  function titleOf(u) { return String(u.title || "").replace(/^[a-d]\.\s*/, "").replace(/\.$/, ""); }

  // The gears a unit can be taught at today: none while its content is unwritten.
  function writtenGears(u) { return u.written === false ? [] : u.available_gears; }

  function layout(state, m) {
    var units = state.units, rows = [], y = m.padTop;
    rows.push({ kind: "gate", key: "ready", h: m.gateH });
    rows.push({ kind: "gate", key: "exam", h: m.gateH });
    for (var i = units.length - 1; i >= 0; i--) {
      rows.push({ kind: "unit", unit: units[i], index: i, h: isSub(units[i]) ? m.subH : m.unitH });
      if (i === 0 || units[i].task !== units[i - 1].task) {
        rows.push({ kind: "task", task: units[i].task, first: i === 0, h: m.taskH });
      }
    }
    rows.push({ kind: "start", h: m.startH });
    rows.forEach(function (r) {
      r.y = y; y += r.h;
      r.anchor = r.kind === "unit" || r.kind === "gate" ? r.y + m.nodeInset : r.kind === "start" ? r.y + m.startH * 0.35 : r.y + r.h / 2;
    });
    var height = y + m.padBottom;

    // Links run bottom-up: each row's lanes start at the anchor below it.
    var lanes = [], links = [], prev = null;
    for (var k = rows.length - 1; k >= 0; k--) {
      var r = rows[k];
      if (!prev) { prev = r; continue; }
      if (r.kind === "unit") {
        lanes.push({ row: r, from: prev.anchor, to: r.anchor });
      } else {
        var below = prev.kind === "unit" ? prev.unit : null;
        links.push({ from: prev.anchor, to: r.anchor, passed: below ? below.mastery !== "unseen" : r.kind === "task" });
      }
      prev = r;
    }
    return { width: m.width, height: height, rows: rows, lanes: lanes, links: links };
  }

  // ---- lane geometry ----------------------------------------------------
  // Gear 1 is the trunk itself. Deeper gears leave the trunk to the right,
  // run parallel to it, and rejoin above: the longer the detour, the slower
  // the gear. Swap this function to change the look without touching layout.
  function lanePath(m, gear, yFrom, yTo) {
    var x = m.trunkX;
    if (gear === 1) { return "M" + x + "," + f(yFrom) + " L" + x + "," + f(yTo); }
    var dx = m.laneGap * (gear - 1), k = Math.min(m.laneGap * 0.45, (yFrom - yTo) / 6);
    return "M" + x + "," + f(yFrom) +
      " C" + x + "," + f(yFrom - k) + " " + (x + dx) + "," + f(yFrom - k) + " " + (x + dx) + "," + f(yFrom - 2 * k) +
      " L" + (x + dx) + "," + f(yTo + 2 * k) +
      " C" + (x + dx) + "," + f(yTo + k) + " " + x + "," + f(yTo + k) + " " + x + "," + f(yTo);
  }
  function f(n) { return Math.round(n * 10) / 10; }

  // ---- text helpers -----------------------------------------------------
  function esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  var FONT = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
  var NARROW = /[iljtfrI.,:;'|!() ]/, WIDE = /[mwMW]/, UPPER = /[A-Z]/;
  var measure = (function () {
    try { var c = document.createElement("canvas").getContext("2d"); return c || null; } catch (e) { return null; }
  }());
  function textWidth(s, size) {
    if (measure) { measure.font = size + "px " + FONT; return measure.measureText(s).width; }
    var w = 0;
    for (var i = 0; i < s.length; i++) {
      var c = s[i];
      w += NARROW.test(c) ? 0.32 : WIDE.test(c) ? 0.9 : UPPER.test(c) ? 0.68 : 0.57;
    }
    return w * size;
  }
  // Word-wrap to at most `lines` lines of `maxW` px; the last line gets an ellipsis if it overflows.
  function wrap(text, size, maxW, lines) {
    var words = text.split(/\s+/), out = [], line = "";
    for (var i = 0; i < words.length; i++) {
      var probe = line ? line + " " + words[i] : words[i];
      if (textWidth(probe, size) <= maxW || !line) { line = probe; continue; }
      out.push(line); line = words[i];
      if (out.length === lines) { break; }
    }
    if (out.length < lines) { out.push(line); }
    else {
      var last = out[lines - 1] + " " + words.slice(i).join(" ");
      while (last.length > 1 && textWidth(last + "…", size) > maxW) { last = last.slice(0, -1).replace(/\s+$/, ""); }
      out[lines - 1] = last + "…";
    }
    return out.slice(0, lines);
  }

  // ---- state words (also the hover text, so nothing is colour-only) -----
  function gearName(g) { return g === 1 ? "Fast-track" : g === 2 ? "Guided" : "Foundational"; }
  function attemptCount(u, g) { return (u.attempts && (u.attempts[g] || u.attempts[String(g)])) || 0; }
  function stateTag(u) {
    if (u.current) { return { text: "now · gear " + u.current_gear, cls: "tag-now" }; }
    if (u.parked) { return { text: "set aside", cls: "tag-bad" }; }
    if (u.needs_attention) { return { text: "needs attention", cls: "tag-bad" }; }
    if (u.mastery === "learning") { return { text: "learning", cls: "tag-warn" }; }
    if (u.mastery === "mastered" && u.current_gear > 1) { return { text: "mastered at gear " + u.current_gear, cls: "tag-muted" }; }
    return null;
  }
  function hoverText(u) {
    var words = u.mastery === "unseen" ? "Not started" : u.mastery === "mastered" ? "Mastered at gear " + u.current_gear : "Learning at gear " + u.current_gear;
    if (u.current) { words += ", current unit"; }
    if (u.parked) { words += ", set aside until the next task boundary"; }
    else if (u.needs_attention) { words += ", needs attention"; }
    var taken = (u.gears_taken || []).map(function (g) {
      var p = attemptCount(u, g); return "gear " + g + " " + gearName(g) + (p ? " (" + p + (p === 1 ? " attempt" : " attempts") + ")" : "");
    });
    var written = writtenGears(u).map(function (g) { return gearName(g); }).join(", ") || "none yet";
    return u.id + ": " + titleOf(u) + ". " + words + ". Speeds written: " + written + (taken.length ? ". Taken: " + taken.join(", ") : "") +
      ". Lane color is the unit's state; weight is attempts at that gear." + (u.mastery === "unseen" ? " Click to start." : " Click to review.");
  }

  // ---- drawing ----------------------------------------------------------
  function laneClass(u, gear) {
    var taken = (u.gears_taken || []).indexOf(gear) >= 0;
    if (!taken) { return "lane"; }
    var p = Math.min(3, Math.max(1, attemptCount(u, gear)));
    var tone = u.mastery === "mastered" ? "good" : "warn";
    return "lane taken " + tone + " p" + p;
  }

  function drawUnit(m, r, lane, parts) {
    var u = r.unit, x = m.trunkX, ny = r.anchor, sub = isSub(u), rad = sub ? m.subR : m.nodeR;
    // the three speed lanes, faint tracks first, then the student's routes on top
    var taken = [];
    [1, 2, 3].forEach(function (g) {
      var d = lanePath(m, g, lane.from, lane.to), cls = laneClass(u, g), isTaken = cls !== "lane";
      var written = writtenGears(u).indexOf(g) >= 0, p = attemptCount(u, g);
      var tip = u.id + ", gear " + g + " (" + gearName(g) + "): " + (isTaken ? "taken" + (p ? ", " + p + (p === 1 ? " attempt" : " attempts") : "") : "not taken") +
        (written ? ". Click to " + (u.mastery === "unseen" ? "start" : "review") + " at this speed." : ". Not written yet for this unit.");
      var group = '<g class="lane-g" data-unit="' + esc(u.id) + '" data-gear="' + g + '"><title>' + esc(tip) + '</title>' +
        '<path class="' + cls + '" d="' + d + '"/><path class="hit" d="' + d + '"/></g>';
      (isTaken ? taken : parts.lanes).push(group);
    });
    parts.routes.push(taken.join(""));
    // the moving marker on the lane the student is on now
    if (u.current) {
      var cx = x + m.laneGap * ((u.current_gear || 1) - 1), cy = lane.to + (lane.from - lane.to) * 0.5;
      parts.marks.push('<circle class="now-dot" cx="' + cx + '" cy="' + f(cy) + '" r="' + (rad * 0.6) + '"/>');
    }
    // node
    var cls = "node " + u.mastery + (u.current ? " current" : "") + (u.parked ? " parked" : "") + (u.needs_attention && !u.parked ? " attention" : "");
    var node = '<g class="unit" data-id="' + esc(u.id) + '" tabindex="' + (u.current ? 0 : -1) + '" role="button"><title>' + esc(hoverText(u)) + '</title>';
    if (u.current) { node += '<circle class="ring" cx="' + x + '" cy="' + f(ny) + '" r="' + (rad + m.ringGap) + '"/>'; }
    node += '<circle class="' + cls + '" cx="' + x + '" cy="' + f(ny) + '" r="' + rad + '"/>';
    if (u.parked && rad >= 3) {
      // set aside: a small pennant to the left of the node, pointing away from it
      var px = x - rad - m.ringGap - 2, ph = rad * 2.4;
      node += '<path class="flag" d="M' + f(px) + ',' + f(ny + ph / 2) + ' V' + f(ny - ph / 2) + ' h-' + f(rad * 1.5) + ' l' + f(rad * 0.6) + ',' + f(rad * 0.6) + ' l-' + f(rad * 0.6) + ',' + f(rad * 0.6) + ' h' + f(rad * 1.5) + '"/>';
    } else if (u.needs_attention) {
      node += '<circle class="attn" cx="' + (x + rad * 0.9) + '" cy="' + f(ny - rad * 0.9) + '" r="' + Math.max(1.2, rad * 0.42) + '"/>';
    }
    // labels: the code with its state tag, then the title
    var lx = m.labelX + (sub ? 12 : 0), maxW = m.width - lx - 6, tag = stateTag(u);
    node += '<text class="code" x="' + lx + '" y="' + f(ny + m.codeFont * 0.36) + '">' + esc(sub ? u.id.replace(/^UA\.I\./, "") : u.id) +
      (tag ? '<tspan class="' + tag.cls + '" dx="7">' + esc(tag.text) + '</tspan>' : "") + '</text>';
    wrap(titleOf(u), m.font, maxW, m.labelLines).forEach(function (line, i) {
      node += '<text class="title" x="' + lx + '" y="' + f(ny + m.codeFont * 0.36 + (i + 1) * (m.font + 3) + 1) + '">' + esc(line) + '</text>';
    });
    node += "</g>";
    parts.nodes.push(node);
  }

  function drawTask(m, r, tasks, parts) {
    var x = m.trunkX, y = r.anchor, name = tasks[r.task] || "";
    parts.marks.push('<line class="rule" x1="' + (m.labelX - 10) + '" y1="' + f(y) + '" x2="' + m.width + '" y2="' + f(y) + '"/>');
    parts.marks.push('<circle class="knot" cx="' + x + '" cy="' + f(y) + '" r="' + m.knotR + '"><title>' +
      esc(r.first ? "Start of task " + r.task + ", " + name : "Task boundary: review check of up to three mastered units, then set-aside units return. Task " + r.task + " starts here") + '</title></circle>');
    var label = wrap("Task " + r.task + " · " + name, m.codeFont, m.width - m.labelX - 6, 1)[0];
    parts.nodes.push('<text class="task" x="' + m.labelX + '" y="' + f(y - 5) + '">' + esc(label) + '</text>');
  }

  function drawGate(m, r, state, parts) {
    var x = m.trunkX, y = r.anchor, s = m.nodeR * 0.9, rd = state.readiness || {};
    var done = r.key === "exam" ? (rd.passes || 0) >= (rd.passes_needed || 2) : !!rd.ready;
    var label = r.key === "exam" ? "Practice exam" : "Readiness gate";
    var detail = r.key === "exam" ? (rd.passes || 0) + " of " + (rd.passes_needed || 2) + " passes at 85 percent or better"
                                  : (rd.ready ? "Ready for the real exam" : "Every unit mastered, none set aside, two exam passes");
    var g = '<g class="gate' + (done ? " done" : "") + '"><title>' + esc(label + ": " + detail) + '</title>' +
      '<rect class="gate-mark" x="' + (x - s) + '" y="' + f(y - s) + '" width="' + (2 * s) + '" height="' + (2 * s) + '" rx="' + (s * 0.3) + '"/>';
    g += '<text class="code" x="' + m.labelX + '" y="' + f(y + m.codeFont * 0.36) + '">' + esc(label) + '</text>';
    wrap(detail, m.font, m.width - m.labelX - 6, m.labelLines).forEach(function (line, i) {
      g += '<text class="title" x="' + m.labelX + '" y="' + f(y + m.codeFont * 0.36 + (i + 1) * (m.font + 3) + 1) + '">' + esc(line) + '</text>';
    });
    parts.nodes.push(g + "</g>");
  }

  function drawStart(m, r, parts) {
    var x = m.trunkX, y = r.anchor;
    parts.marks.push('<line class="ground" x1="' + (x - m.nodeR * 1.6) + '" y1="' + f(y) + '" x2="' + (x + m.nodeR * 1.6) + '" y2="' + f(y) + '"/>');
    parts.nodes.push('<text class="task" x="' + m.labelX + '" y="' + f(y + m.codeFont * 0.36) + '">Start</text>');
  }

  var STYLE =
    '.course-tree{--ct-surface:var(--surface,#fff);--ct-text:var(--text,#1f1f1d);--ct-muted:var(--muted,#5f5f5a);--ct-line:var(--line,#e2e2dc);--ct-accent:var(--accent,#2f6f8f);--ct-good:var(--good,#2e7d54);--ct-warn:var(--warn,#b26a12);--ct-bad:var(--bad,#b23b3b);' +
    'font-family:' + FONT + '}' +
    '@media (prefers-color-scheme:dark){.course-tree{--ct-surface:var(--surface,#242422);--ct-text:var(--text,#eceae4);--ct-muted:var(--muted,#a6a49c);--ct-line:var(--line,#3a3a36);--ct-accent:var(--accent,#7fb8d4);--ct-good:var(--good,#7fce9f);--ct-warn:var(--warn,#e0a24a);--ct-bad:var(--bad,#e07a7a)}}' +
    '.course-tree .lane{fill:none;stroke:var(--ct-muted);stroke-opacity:.35;stroke-linecap:round;stroke-linejoin:round}' +
    '.course-tree .link{fill:none;stroke:var(--ct-muted);stroke-opacity:.35}.course-tree .link.passed{stroke-opacity:.6}' +
    '.course-tree .lane.taken{stroke-opacity:1}.course-tree .lane.good{stroke:var(--ct-good)}.course-tree .lane.warn{stroke:var(--ct-warn)}' +
    '.course-tree .node{stroke:var(--ct-surface);stroke-width:2}' +
    '.course-tree .node.unseen{fill:var(--ct-surface);stroke:var(--ct-muted);stroke-opacity:.65;stroke-width:1.5}' +
    '.course-tree .node.learning{fill:var(--ct-warn)}.course-tree .node.mastered{fill:var(--ct-good)}' +
    '.course-tree .node.parked{fill:var(--ct-surface);stroke:var(--ct-bad);stroke-width:1.5;stroke-dasharray:2.5 2}' +
    '.course-tree .ring{fill:none;stroke:var(--ct-accent);stroke-width:2}' +
    '.course-tree .flag{fill:var(--ct-bad);stroke:var(--ct-bad);stroke-width:1;stroke-linejoin:round}' +
    '.course-tree .attn{fill:var(--ct-bad);stroke:var(--ct-surface);stroke-width:1}' +
        '.course-tree .now-dot{fill:var(--ct-accent);stroke:var(--ct-surface);stroke-width:1.5;pointer-events:none;animation:ct-pulse 1.6s ease-in-out infinite}' +
    '@keyframes ct-pulse{0%,100%{opacity:1}50%{opacity:.35}}@media (prefers-reduced-motion:reduce){.course-tree .now-dot{animation:none}}' +
    '.course-tree .knot{fill:var(--ct-surface);stroke:var(--ct-muted);stroke-width:1.5}' +
    '.course-tree .rule{stroke:var(--ct-line);stroke-width:1}.course-tree .ground{stroke:var(--ct-muted);stroke-width:1.5;stroke-linecap:round}' +
    '.course-tree .gate-mark{fill:var(--ct-surface);stroke:var(--ct-muted);stroke-width:1.5}.course-tree .gate.done .gate-mark{fill:var(--ct-good);stroke:var(--ct-good)}' +
    '.course-tree text{fill:var(--ct-text)}.course-tree .code,.course-tree .task{fill:var(--ct-muted)}' +
    '.course-tree .tag-now{fill:var(--ct-accent);font-weight:500}.course-tree .tag-bad{fill:var(--ct-bad)}.course-tree .tag-warn{fill:var(--ct-warn)}.course-tree .tag-muted{fill:var(--ct-muted)}' +
    '.course-tree .hit{fill:none;stroke:transparent;stroke-width:12;pointer-events:stroke}.course-tree .lane-g,.course-tree g.unit{cursor:pointer}' +
    '.course-tree .lane-g:hover .lane,.course-tree .lane-g.selected .lane{stroke-opacity:1}' +
    '.course-tree .lane-g:hover .lane:not(.taken),.course-tree .lane-g.selected .lane{stroke:var(--ct-accent)}' +
    '.course-tree g.unit:focus{outline:none}.course-tree g.unit:hover .node,.course-tree g.unit:focus-visible .node,.course-tree g.unit.selected .node{stroke:var(--ct-accent);stroke-opacity:1}' +
    '.course-tree.fresh .lane,.course-tree.fresh .link{stroke:var(--ct-good);stroke-opacity:.5}.course-tree.fresh .lane{stroke-width:1.5}' +
    '.course-tree.fresh .node.unseen,.course-tree.fresh .knot{stroke:var(--ct-good);stroke-opacity:.8}';

  function laneStyle(m) {
    return '.course-tree .lane{stroke-width:' + m.laneW[0] + '}' +
      '.course-tree .lane.p1{stroke-width:' + m.laneW[1] + ';stroke-opacity:' + m.laneOpacity[1] + '}' +
      '.course-tree .lane.p2{stroke-width:' + m.laneW[2] + ';stroke-opacity:' + m.laneOpacity[2] + '}' +
      '.course-tree .lane.p3{stroke-width:' + m.laneW[3] + ';stroke-opacity:' + m.laneOpacity[3] + '}' +
      '.course-tree .link{stroke-width:' + m.laneW[0] + '}' +
      '.course-tree .code{font-size:' + m.codeFont + 'px}.course-tree .title{font-size:' + m.font + 'px}.course-tree .task{font-size:' + m.codeFont + 'px}';
  }

  // Build the whole SVG as a string. tasks: letter -> task name. opts.fresh
  // draws every track in green, the whole course open ahead of a new student.
  // opts.width replaces the placement's width, for a panel the student resizes.
  function svg(state, tasks, variant, opts) {
    var m = METRICS[variant] || METRICS.sidebar;
    if (opts && opts.width) { m = Object.assign({}, m, { width: opts.width }); }
    var lay = layout(state, m);
    var parts = { lanes: [], routes: [], marks: [], nodes: [] };
    lay.links.forEach(function (l) {
      parts.lanes.push('<path class="link' + (l.passed ? " passed" : "") + '" d="' + lanePath(m, 1, l.from, l.to) + '"/>');
    });
    var laneByRow = {};
    lay.lanes.forEach(function (l) { laneByRow[l.row.index] = l; });
    lay.rows.forEach(function (r) {
      if (r.kind === "unit") { drawUnit(m, r, laneByRow[r.index], parts); }
      else if (r.kind === "task") { drawTask(m, r, tasks, parts); }
      else if (r.kind === "gate") { drawGate(m, r, state, parts); }
      else if (r.kind === "start") { drawStart(m, r, parts); }
    });
    var body = '<style>' + STYLE + laneStyle(m) + '</style>' +
      '<g class="lanes">' + parts.lanes.join("") + '</g><g class="routes">' + parts.routes.join("") + '</g>' +
      '<g class="marks">' + parts.marks.join("") + '</g><g class="nodes">' + parts.nodes.join("") + '</g>';
    var ci = -1;
    lay.rows.forEach(function (r, i) { if (r.kind === "unit" && r.unit.current) { ci = i; } });
    var span = windowSpan(lay.rows, ci);
    return {
      markup: '<svg class="course-tree course-tree-' + variant + (opts && opts.fresh ? " fresh" : "") + '" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + lay.width + ' ' + f(lay.height) +
        '" width="' + lay.width + '" height="' + f(lay.height) + '" role="img" aria-label="Course tree, ' + state.summary.mastered + ' of ' + state.summary.total + ' units mastered">' + body + '</svg>',
      height: lay.height, width: lay.width, currentY: span
    };
  }

  // The middle of the three rows the window should show: the unit or gate above
  // the current unit, the current unit, and the unit or start below it. Task
  // rows in between are included in the span, so a boundary never pushes the
  // past or the next unit out of the window.
  function windowSpan(rows, ci) {
    if (ci < 0) { return 0; }
    var above = null, below = null, i;
    for (i = ci - 1; i >= 0 && !above; i--) { if (rows[i].kind === "unit" || rows[i].kind === "gate") { above = rows[i]; } }
    for (i = ci + 1; i < rows.length && !below; i++) { if (rows[i].kind === "unit" || rows[i].kind === "start") { below = rows[i]; } }
    var top = (above || rows[ci]).y, bottom = (below || rows[ci]).y + (below || rows[ci]).h;
    return (top + bottom) / 2;
  }

  // Render into a container and scroll it so the current unit sits in the
  // middle (a no-op when the container does not scroll). `animate` false jumps
  // (first paint and reduced motion), true glides, which is the tree scrolling
  // up on progress.
  function render(container, state, tasks, variant, animate, opts) {
    var out = svg(state, tasks, variant, opts);
    container.innerHTML = out.markup;
    container.dataset.currentY = out.currentY;
    scrollToCurrent(container, animate);
    return out;
  }

  // A unit near either end of the course stops short of the middle: the
  // window cannot scroll past the tree's ends.
  function targetTop(container) {
    var middle = Number(container.dataset.currentY || 0) - container.clientHeight / 2;
    return Math.max(0, Math.min(container.scrollHeight - container.clientHeight, middle));
  }

  function scrollToCurrent(container, animate) {
    var top = targetTop(container);
    var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (animate && !reduce && container.scrollTo) { container.scrollTo({ top: top, behavior: "smooth" }); }
    else { container.scrollTop = top; }
  }

  function offCurrent(container) {
    return Math.abs(container.scrollTop - targetTop(container)) > METRICS.sidebar.unitH * 0.6;
  }

  // Clicks and keyboard activation on lanes and nodes. handler({unit, gear})
  // gets the lane's gear, or null when the unit's node itself was chosen. The
  // current unit is the tree's one Tab stop; the arrow keys move the focus to
  // the next unit up or down the course.
  function onSelect(container, handler) {
    function step(node, dir) {
      var nodes = container.querySelectorAll("g.unit"), i;
      for (i = 0; i < nodes.length; i++) { if (nodes[i] === node) { break; } }
      // nodes run top-down in the DOM, so up the course is the previous one
      var next = nodes[i + (dir === "up" ? -1 : 1)];
      if (next) { next.focus(); }
    }
    function pick(target) {
      if (!target || !target.closest) { return null; }
      var lane = target.closest("g.lane-g");
      if (lane) { return { unit: lane.getAttribute("data-unit"), gear: Number(lane.getAttribute("data-gear")) }; }
      var node = target.closest("g.unit");
      return node ? { unit: node.getAttribute("data-id"), gear: null } : null;
    }
    container.addEventListener("click", function (e) { var p = pick(e.target); if (p) { handler(p); } });
    container.addEventListener("keydown", function (e) {
      var node = e.target && e.target.closest ? e.target.closest("g.unit") : null;
      if (node && (e.key === "ArrowUp" || e.key === "ArrowDown")) {
        e.preventDefault();
        step(node, e.key === "ArrowUp" ? "up" : "down");
        return;
      }
      if (e.key !== "Enter" && e.key !== " ") { return; }
      var p = pick(e.target);
      if (p) { e.preventDefault(); handler(p); }
    });
  }

  // Highlight the chosen lane (or node when gear is null); unit null clears it.
  function markSelected(container, unit, gear) {
    Array.prototype.forEach.call(container.querySelectorAll(".selected"), function (n) { n.classList.remove("selected"); });
    if (!unit) { return; }
    var n = container.querySelector(gear ? 'g.lane-g[data-unit="' + unit + '"][data-gear="' + gear + '"]' : 'g.unit[data-id="' + unit + '"]');
    if (n) { n.classList.add("selected"); }
  }

  // The lanes glyph for the key: the three lanes of one unit, drawn by lanePath.
  function laneGlyph() {
    var g = { trunkX: 6, laneGap: 13 };
    return '<svg width="40" height="30" viewBox="0 0 40 30" aria-hidden="true" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">' +
      '<path d="' + lanePath(g, 3, 27, 3) + '" stroke-width="1.2" stroke-opacity=".35"/>' +
      '<path d="' + lanePath(g, 2, 27, 3) + '" stroke-width="1.6" stroke-opacity=".6"/>' +
      '<path d="' + lanePath(g, 1, 27, 3) + '" stroke-width="2.5"/></svg>';
  }

  window.CourseTree = { laneGlyph: laneGlyph, METRICS: METRICS, layout: layout, svg: svg, render: render, scrollToCurrent: scrollToCurrent,
                        offCurrent: offCurrent, lanePath: lanePath, onSelect: onSelect, markSelected: markSelected, gearName: gearName, titleOf: titleOf, writtenGears: writtenGears };
})();
