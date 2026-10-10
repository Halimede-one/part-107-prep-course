// Sample student states for the mockup, in the shape /api/state returns today
// plus two proposed fields per unit: title (from objectives.md) and attempts
// (attempts per gear, derived from the ledger's attempts table).
(function () {
  "use strict";

  function base(defaultGear) {
    return window.COURSE_UNITS.map(function (u) {
      return {
        id: u.id, task: u.task, title: u.title, sub: u.sub, written: u.written,
        mastery: "unseen", current: false,
        available_gears: u.available_gears.slice(), gears_taken: [],
        current_gear: defaultGear, attempts: {},
        needs_attention: false, parked: false
      };
    });
  }

  // mastered(unit) : two correct at the last gear taken.
  // Each entry: [id, gears taken, attempts per gear, mastery, flags]
  function apply(units, rows, currentId) {
    var byId = {};
    units.forEach(function (u) { byId[u.id] = u; });
    rows.forEach(function (r) {
      var u = byId[r[0]];
      u.gears_taken = r[1];
      u.current_gear = r[1][r[1].length - 1];
      u.attempts = r[2];
      u.mastery = r[3];
      if (r[4]) { u.needs_attention = !!r[4].needs_attention; u.parked = !!r[4].parked; }
    });
    units.forEach(function (u) { u.current = u.id === currentId; });
    return units;
  }

  function reasons(units, exam) {
    var mastered = units.filter(function (u) { return u.mastery === "mastered"; }).length;
    var parked = units.filter(function (u) { return u.parked; }).length, out = [];
    if (mastered < units.length) { out.push((units.length - mastered) + " units not yet mastered"); }
    if (parked) { out.push(parked + " unit set aside"); }
    out.push(exam.passes + " of " + exam.needed + " passing practice exams");
    return out;
  }

  function finish(units, defaultGear, lastTask, exam) {
    var mastered = units.filter(function (u) { return u.mastery === "mastered"; }).length;
    return {
      area: "Regulations", default_gear: defaultGear, last_task: lastTask,
      units: units,
      summary: { mastered: mastered, total: units.length },
      readiness: { ready: false, reasons: reasons(units, exam), attempts: exam.attempts, passes: exam.passes, passes_needed: exam.needed },
      mock_available: true, mock_in_progress: false, exam: exam
    };
  }

  function fresh() {
    var units = base(1);
    units[0].current = true;
    return finish(units, 1, null, { attempts: 0, passes: 0, needed: 2 });
  }

  // The brief's sample state: task A done, task B under way.
  function mid() {
    var rows = [
      ["UA.I.A.K1", [1], { 1: 2 }, "mastered"],
      ["UA.I.A.K2", [1, 2], { 1: 1, 2: 2 }, "mastered"],
      ["UA.I.A.K3", [1], { 1: 3 }, "mastered"],
      ["UA.I.A.K4", [1], { 1: 2 }, "mastered"],
      ["UA.I.A.K5", [1], { 1: 2 }, "mastered"],
      ["UA.I.A.K6", [1], { 1: 2 }, "mastered"],
      ["UA.I.A.K7", [1], { 1: 2 }, "mastered"],
      ["UA.I.A.K8", [1], { 1: 2 }, "mastered"]
    ];
    ["K1", "K2", "K3", "K4", "K4a", "K5", "K6", "K6a", "K6b", "K7", "K9", "K10", "K11", "K12", "K13"].forEach(function (k) {
      rows.push(["UA.I.B." + k, [1], { 1: 2 }, "mastered"]);
    });
    rows.push(["UA.I.B.K8", [1, 2], { 1: 1, 2: 2 }, "mastered"]);
    rows.push(["UA.I.B.K14", [1, 2], { 1: 1, 2: 3 }, "learning", { needs_attention: true, parked: true }]);
    rows.push(["UA.I.B.K14a", [1], { 1: 2 }, "mastered"]);
    rows.push(["UA.I.B.K15", [1], { 1: 2 }, "mastered"]);
    rows.push(["UA.I.B.K16", [1, 2, 3], { 1: 1, 2: 1, 3: 2 }, "mastered"]);
    rows.push(["UA.I.B.K17", [1, 2], { 1: 1, 2: 1 }, "learning"]);
    return finish(apply(base(1), rows, "UA.I.B.K17"), 1, "B", { attempts: 1, passes: 0, needed: 2 });
  }

  // Near the end: everything through task E mastered, task F under way, with
  // one unit set aside in E that will return at the next boundary.
  function late() {
    var rows = [];
    window.COURSE_UNITS.forEach(function (u, i) {
      if (u.task === "F") { return; }
      var deeper = (i % 7 === 3);
      rows.push([u.id, deeper ? [1, 2] : [1], deeper ? { 1: 1, 2: 2 } : { 1: (i % 11 === 5 ? 3 : 2) }, "mastered"]);
    });
    function set(id, row) { rows = rows.filter(function (r) { return r[0] !== id; }); rows.push(row); }
    set("UA.I.E.K3", ["UA.I.E.K3", [1, 2, 3], { 1: 1, 2: 1, 3: 3 }, "mastered"]);
    set("UA.I.E.K13", ["UA.I.E.K13", [1, 2], { 1: 1, 2: 3 }, "learning", { needs_attention: true, parked: true }]);
    set("UA.I.D.K1", ["UA.I.D.K1", [1, 2], { 1: 2, 2: 2 }, "mastered"]);
    rows.push(["UA.I.F.K1", [1], { 1: 2 }, "mastered"]);
    rows.push(["UA.I.F.K2", [1], { 1: 1 }, "learning"]);
    return finish(apply(base(1), rows, "UA.I.F.K2"), 1, "F", { attempts: 2, passes: 1, needed: 2 });
  }

  // Advance the sample state one unit, as a turn would: the current unit is
  // mastered at its gear and the next unit becomes current. Used by the
  // mockup's Step button to show the tree scrolling up.
  function step(state) {
    var units = state.units, i = -1, k;
    for (k = 0; k < units.length; k++) { if (units[k].current) { i = k; break; } }
    if (i < 0 || i >= units.length - 1) { return state; }
    var u = units[i];
    u.mastery = "mastered";
    if (!u.gears_taken.length) { u.gears_taken = [u.current_gear]; }
    u.attempts[u.current_gear] = (u.attempts[u.current_gear] || 0) + 1;
    u.current = false;
    var n = units[i + 1];
    n.current = true;
    if (n.mastery === "unseen") { n.mastery = "learning"; n.gears_taken = [n.current_gear]; n.attempts[n.current_gear] = 1; }
    state.summary.mastered = units.filter(function (x) { return x.mastery === "mastered"; }).length;
    state.readiness.reasons = reasons(units, state.exam);
    state.last_task = n.task;
    return state;
  }

  // A unit and a speed picked from the tree: the unit becomes current at that
  // gear, as the server's goto would do. Attempts and mastery stay as they are.
  function goto(state, id, gear) {
    var u = state.units.filter(function (x) { return x.id === id; })[0];
    if (!u) { return state; }
    state.units.forEach(function (x) { x.current = false; });
    u.current = true;
    u.current_gear = gear;
    if (u.gears_taken.indexOf(gear) < 0) { u.gears_taken.push(gear); }
    state.last_task = u.task;
    return state;
  }

  window.MOCK_STATES = { fresh: fresh, mid: mid, late: late, step: step, goto: goto };
})();
