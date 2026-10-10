// Wiring for the mockup page only: scene and state selection, the Step button,
// and the recenter control. The pieces the shell would own are marked.
(function () {
  "use strict";
  var q = {};
  location.search.slice(1).split("&").forEach(function (kv) {
    if (!kv) { return; }
    var p = kv.split("="); q[decodeURIComponent(p[0])] = decodeURIComponent(p[1] || "");
  });
  var scene = q.scene || "sidebar", stateName = q.state || "mid";
  var state = (window.MOCK_STATES[stateName] || window.MOCK_STATES.mid)();
  for (var n = Number(q.steps) || 0; n > 0; n--) { window.MOCK_STATES.step(state); }
  if (q.goto) { window.MOCK_STATES.goto(state, q.goto, Number(q.gear) || state.default_gear); }
  if (q.bare === "1") { document.body.classList.add("bare"); }
  document.body.classList.add("scene-" + scene);

  Array.prototype.forEach.call(document.querySelectorAll(".scene"), function (s) { s.hidden = s.id !== "scene-" + scene; });
  Array.prototype.forEach.call(document.querySelectorAll(".mock-bar a"), function (a) {
    a.classList.toggle("on", a.dataset.scene === scene);
    a.href = "?scene=" + a.dataset.scene + "&state=" + stateName;
  });
  var select = document.getElementById("state-select");
  select.value = stateName;
  select.addEventListener("change", function () { location.search = "?scene=" + scene + "&state=" + select.value; });
  document.getElementById("step-btn").hidden = scene !== "sidebar";

  // ---- shell-owned: renderMap(state) in app.js would do this ------------
  function currentUnit(s) { return s.units.filter(function (u) { return u.current; })[0]; }
  function unitById(s, id) { return s.units.filter(function (u) { return u.id === id; })[0]; }

  // The picker under a tree: the chosen unit, its state, the three speeds
  // (the clicked lane preselected, unwritten ones disabled) and the action.
  function picker(box, tree, s, onStart) {
    var title = box.querySelector(".tree-pick-title"), words = box.querySelector(".tree-pick-state");
    var gears = box.querySelectorAll(".tree-pick-gears button"), start = box.querySelector(".tree-pick-start"), chosen = null;
    function press() {
      Array.prototype.forEach.call(gears, function (b) { b.setAttribute("aria-pressed", String(Number(b.dataset.gear) === chosen.gear)); });
      window.CourseTree.markSelected(tree, chosen.unit, chosen.gear);
    }
    function show(sel) {
      var u = unitById(s, sel.unit);
      if (!u) { return; }
      var written = window.CourseTree.writtenGears(u);
      chosen = { unit: u.id, gear: sel.gear && written.indexOf(sel.gear) >= 0 ? sel.gear : (u.current_gear || s.default_gear) };
      title.textContent = u.id + " \u00b7 " + window.CourseTree.titleOf(u);
      words.textContent = u.mastery === "unseen" ? "Not started" : (u.mastery === "mastered" ? "Mastered at gear " + u.current_gear : "Learning at gear " + u.current_gear) +
        (u.parked ? ", set aside" : "") + ". Speeds written: " + (written.map(window.CourseTree.gearName).join(", ") || "none yet") + ".";
      Array.prototype.forEach.call(gears, function (b) {
        var g = Number(b.dataset.gear);
        b.disabled = written.indexOf(g) < 0;
        b.title = b.disabled ? "Not written yet for this unit" : "";
      });
      start.textContent = u.mastery === "unseen" ? "Start here" : (u.current ? "Switch speed" : "Review");
      start.disabled = !written.length;
      box.hidden = false;
      press();
    }
    function hide() { box.hidden = true; chosen = null; window.CourseTree.markSelected(tree, null); }
    Array.prototype.forEach.call(gears, function (b) {
      b.addEventListener("click", function () { if (chosen) { chosen.gear = Number(b.dataset.gear); press(); } });
    });
    start.addEventListener("click", function () { if (chosen) { onStart(chosen); } });
    box.querySelector(".tree-pick-cancel").addEventListener("click", hide);
    return { show: show, hide: hide };
  }

  function renderReadiness(s) {
    var node = document.getElementById("readiness"), r = s.readiness;
    node.innerHTML = "";
    if (r.ready) { node.innerHTML = '<div class="ready">Ready to schedule the real exam</div>'; return; }
    node.appendChild(document.createTextNode("Not yet ready for the real exam"));
    var ul = document.createElement("ul");
    r.reasons.forEach(function (x) { var li = document.createElement("li"); li.textContent = x; ul.appendChild(li); });
    node.appendChild(ul);
  }

  function renderSidebar(s, animate) {
    document.getElementById("map-summary").textContent = s.summary.mastered + " / " + s.summary.total;
    var cur = currentUnit(s);
    document.getElementById("map-task-name").textContent = cur ? "Task " + cur.task + " · " + window.COURSE_TASKS[cur.task] : "";
    window.CourseTree.render(document.getElementById("course-tree"), s, window.COURSE_TASKS, "sidebar", animate);
    renderReadiness(s);
    if (cur) {
      document.getElementById("lesson-gear").textContent = "Gear " + cur.current_gear + " \u00b7 " + window.CourseTree.gearName(cur.current_gear);
      document.getElementById("lesson-code").textContent = cur.id;
      document.getElementById("lesson-title").textContent = cur.title;
    }
    document.getElementById("tree-recenter").hidden = true;
  }

  if (scene === "sidebar") {
    document.getElementById("key-lanes").innerHTML = window.CourseTree.laneGlyph();
    renderSidebar(state, false);
    var win = document.getElementById("course-tree"), btn = document.getElementById("tree-recenter"), glide = null;
    // A glide the shell started is not the student scrolling away: when the
    // window is off the current unit, hold the button until it arrives there
    // (two seconds at most).
    function gliding() {
      clearTimeout(glide); glide = null; btn.hidden = true;
      if (window.CourseTree.offCurrent(win)) { glide = setTimeout(function () { glide = null; }, 2000); }
    }
    win.addEventListener("scroll", function () {
      var off = window.CourseTree.offCurrent(win);
      if (glide && off) { return; }
      clearTimeout(glide); glide = null;
      btn.hidden = !off;
    });
    btn.addEventListener("click", function () { gliding(); window.CourseTree.scrollToCurrent(win, true); });
    document.getElementById("step-btn").addEventListener("click", function () {
      renderSidebar(window.MOCK_STATES.step(state), true);
      gliding();
    });
    // pick a unit and a speed from the tree: the mockup makes it current at once
    var pick = picker(document.getElementById("tree-pick"), win, state, function (sel) {
      pick.hide();
      renderSidebar(window.MOCK_STATES.goto(state, sel.unit, sel.gear), true);
      gliding();
    });
    window.CourseTree.onSelect(win, pick.show);
    if (q.pick) { pick.show({ unit: q.pick.split(":")[0], gear: Number(q.pick.split(":")[1]) || null }); }
  } else if (scene === "intake") {
    document.getElementById("intake-summary").textContent = state.summary.mastered + " of " + state.summary.total + " mastered";
    var panel = document.getElementById("intake-tree");
    var fresh = state.units.every(function (u) { return u.mastery === "unseen"; });
    window.CourseTree.render(panel, state, window.COURSE_TASKS, "full", false, { fresh: fresh });
    // pick a unit and a speed: the course opens there (the mockup switches scene)
    var intakePick = picker(document.getElementById("intake-pick"), panel, state, function (sel) {
      location.search = "?scene=sidebar&state=" + stateName + "&goto=" + encodeURIComponent(sel.unit) + "&gear=" + sel.gear;
    });
    window.CourseTree.onSelect(panel, intakePick.show);
    if (q.pick) { intakePick.show({ unit: q.pick.split(":")[0], gear: Number(q.pick.split(":")[1]) || null }); }
  } else {
    var out = window.CourseTree.render(document.getElementById("full-tree"), state, window.COURSE_TASKS, "full", false);
    document.getElementById("full-caption").textContent = "Sample state “" + stateName + "”: " + state.summary.mastered + " of " + state.summary.total +
      " units mastered. Bottom to top, " + Math.round(out.height) + " px tall at the sidebar scale.";
  }
  window.__treeReady = true;
})();
