(function () {
  "use strict";

  // ---- server API -------------------------------------------------------
  // The shell talks to the server through these calls. post() streams: the
  // lesson panel shows the block while the tutor writes it, and the promise
  // resolves with the finished block, or an error.
  var api = {
    getState: function () {
      return timedFetch("state", "/api/state");
    },
    post: function (payload) {
      logSent(payload);
      // The buttons on screen go dead at once, so a second click cannot send a second request.
      Array.prototype.forEach.call(document.querySelectorAll("#block-root button"), function (b) { b.disabled = true; });
      turn.busy = true;
      return streamRequest(payload.type, "/api/respond", payload, showProgress)
        .then(function (final) {
          return final.block || { type: "error", message: final.error };
        })
        .catch(function () {
          return { type: "error", message: "Could not reach the course server. Is it still running?" };
        })
        .then(function (block) {
          turn.busy = false;
          return block;
        });
    }
  };

  // ---- metrics ----------------------------------------------------------
  // The browser's side of the timing, sent to the server's metrics log.
  function report(record) {
    record.hidden = document.hidden;
    try { navigator.sendBeacon("/api/metrics", JSON.stringify(record)); } catch (e) { /* never break the course */ }
  }

  // Run fn as the next task, once the drawing in the current one is done.
  // A message channel is used because browsers delay timers in hidden tabs.
  var nextTask = (function () {
    var channel = new MessageChannel(), queue = [];
    channel.port1.onmessage = function () { queue.shift()(); };
    return function (fn) { queue.push(fn); channel.port2.postMessage(null); };
  }());

  // One request: the round trip, the server's share from its Server-Timing
  // header, and the time the caller's then-chain takes to draw the result.
  function timedFetch(what, url, options) {
    var started = performance.now();
    return fetch(url, options).then(function (r) {
      var server = /total;dur=([\d.]+)/.exec(r.headers.get("server-timing") || "");
      return r.json().then(function (data) {
        var arrived = performance.now();
        nextTask(function () {
          report({
            kind: "request", what: what,
            round_trip_ms: Math.round(arrived - started),
            server_ms: server ? Math.round(Number(server[1])) : null,
            draw_ms: Math.round(performance.now() - arrived)
          });
        });
        return data;
      });
    });
  }

  // One streamed request. "start", "status" and "delta" events go to onEvent
  // as they arrive; the promise resolves with the final event, {done} or
  // {error}. The report gives the round trip, the time to the first text, and
  // the time the caller takes to draw the finished block.
  function streamRequest(what, url, payload, onEvent) {
    var started = performance.now(), firstText = null, final = null;
    return fetch(url, {
      method: "POST",
      headers: { "content-type": "application/json", "accept": "application/x-ndjson" },
      body: JSON.stringify(payload)
    }).then(function (r) {
      return readLines(r.body, function (event) {
        if (event.done || event.error) { final = event; return; }
        if (event.type === "error") { final = { error: event.message }; return; }  // a plain JSON refusal
        if (event.delta !== undefined && firstText === null) { firstText = performance.now(); }
        onEvent(event);
      });
    }).then(function () {
      var arrived = performance.now();
      nextTask(function () {
        report({
          kind: "request", what: what,
          round_trip_ms: Math.round(arrived - started),
          first_text_ms: firstText === null ? null : Math.round(firstText - started),
          draw_ms: Math.round(performance.now() - arrived)
        });
      });
      return final || { error: "The answer stopped before it finished." };
    });
  }

  window.addEventListener("load", function () {
    // loadEventEnd is set only after the load handlers return.
    nextTask(function () {
      var nav = performance.getEntriesByType("navigation")[0];
      if (!nav) { return; }
      var files = { "index.html": Math.round(nav.responseEnd - nav.requestStart) };
      performance.getEntriesByType("resource").forEach(function (r) {
        if (r.initiatorType === "link" || r.initiatorType === "script") {
          files[r.name.split("/").pop()] = Math.round(r.duration);
        }
      });
      report({
        kind: "page_load",
        first_byte_ms: Math.round(nav.responseStart),
        dom_ready_ms: Math.round(nav.domContentLoadedEventEnd),
        load_ms: Math.round(nav.loadEventEnd),
        files: files
      });
    });
  });

  var currentUnit = null;
  var turn = { busy: false };   // a lesson, question or feedback request in flight

  // ---- small DOM helper -------------------------------------------------
  function el(tag, attrs, kids) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        var v = attrs[k];
        if (k === "class") { node.className = v; }
        else if (k.slice(0, 2) === "on" && typeof v === "function") { node.addEventListener(k.slice(2), v); }
        else if (v === true) { node.setAttribute(k, ""); }
        else if (v !== false && v != null) { node.setAttribute(k, v); }
      });
    }
    if (kids != null) {
      (Array.isArray(kids) ? kids : [kids]).forEach(function (c) {
        if (c == null) { return; }
        node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
      });
    }
    return node;
  }

  function iso() { return new Date().toISOString(); }
  function gearName(g) { return g === 1 ? "Fast-track" : g === 2 ? "Guided" : "Foundational"; }

  function gearTag(block) {
    if (!block.gear && !block.unit) { return null; }
    return el("div", null, [
      block.gear ? el("span", { class: "gear-tag" }, "Gear " + block.gear + " \u00b7 " + gearName(block.gear)) : null,
      block.unit ? el("span", { class: "unit-code" }, unitLabel(block.unit)) : null
    ]);
  }

  function citations(cites) {
    if (!cites || !cites.length) { return null; }
    var links = cites.map(function (c) {
      return el("div", { class: "citation" }, el("a", { href: c.url, target: "_blank", rel: "noopener" }, c.source));
    });
    return el("div", { class: "citations" }, [el("div", { class: "citations-label" }, "Sources")].concat(links));
  }

  // ---- block rendering --------------------------------------------------
  // Every turn goes through here: the server's reply is either a teaching
  // block or an error. Chat answers go to the chat panel instead.
  function render(result) {
    if (!result) { return; }
    stopTimer();
    stopProgress();
    renderBlock(result);
    api.getState().then(function (state) { renderMap(state, true); });
  }

  // ---- status indicator -------------------------------------------------
  // What the tutor is doing while a block or answer is on its way: the stage,
  // the model, whether text has started to arrive, and the seconds so far.
  function indicator(start) {
    var label = el("span", { class: "status-text" }, start.status);
    var meta = el("span", { class: "status-meta" });
    var node = el("div", { class: "status", role: "status" }, [el("span", { class: "pulse" }), label, meta]);
    var began = performance.now(), writing = false;
    function tick() {
      var seconds = Math.floor((performance.now() - began) / 1000);
      meta.textContent = (writing ? start.model : "waiting for " + start.model) + " · " + seconds + " s";
    }
    tick();
    var ticker = setInterval(tick, 1000);
    return {
      node: node,
      status: function (text) { label.textContent = text; },
      writing: function () {
        if (!writing) { writing = true; node.classList.add("writing"); tick(); }
      },
      stop: function () { clearInterval(ticker); }
    };
  }

  // Text arriving for one field: add it to the field's Markdown, show it
  // rendered, and move the caret there. Titles and stems are h2 fields.
  function streamInto(target, text) {
    Array.prototype.forEach.call(document.querySelectorAll(".streaming-text.active"), function (n) {
      if (n !== target) { n.classList.remove("active"); }
    });
    target.classList.add("active");
    target.raw = (target.raw || "") + text;
    target.replaceChildren(target.tagName === "H2" ? markdown.inline(target.raw) : markdown.block(target.raw));
  }

  // ---- streaming into the lesson panel ----------------------------------
  // While the tutor writes, the panel shows what is already known (the gear
  // and unit, a feedback verdict, an exam score) and fills in the text as it
  // arrives. render() then replaces it with the finished block.
  var progress = null;

  function showProgress(event) {
    if (event.start) {
      stopTimer();
      stopProgress();
      var b = event.start.block || {};
      currentUnit = b.unit || currentUnit;
      var fields = {};
      var field = function (name, tag, cls) {
        return (fields[name] = el(tag, { class: cls + " streaming-text" }));
      };
      var parts;
      if (b.type === "feedback") {
        parts = [gearTag(b), feedbackResult(b), field("message", "div", "block-body")];
      } else if (b.type === "question") {
        parts = [gearTag(b), b.review ? el("p", { class: "mock-pos" }, "Review check on a unit you mastered earlier") : null,
                 field("stem", "h2", "block-title")];
      } else if (b.type === "mock_result") {
        timer.deadline = 0;
        parts = mockResultParts(b).concat([field("body", "div", "block-body")]);
      } else {
        parts = [gearTag(b), field("title", "h2", "block-title"), field("body", "div", "block-body")];
      }
      var ind = indicator(event.start);
      var root = document.getElementById("block-root");
      root.innerHTML = "";
      root.appendChild(el("div", null, [ind.node].concat(parts)));
      progress = { indicator: ind, fields: fields };
      api.getState().then(function (state) { renderMap(state, true); });
      return;
    }
    if (!progress) { return; }
    if (event.status) { progress.indicator.status(event.status); }
    if (event.delta !== undefined && progress.fields[event.field]) {
      progress.indicator.writing();
      streamInto(progress.fields[event.field], event.delta);
    }
  }

  function stopProgress() {
    if (progress) { progress.indicator.stop(); progress = null; }
  }

  function renderBlock(block) {
    var root = document.getElementById("block-root");
    root.innerHTML = "";
    if (!block) {
      root.appendChild(el("p", { class: "done" }, "Nothing to show."));
      return;
    }
    currentUnit = block.unit || currentUnit;
    if (block.type === "lesson") { root.appendChild(renderLesson(block)); }
    else if (block.type === "question" && block.mock) { root.appendChild(renderMockQuestion(block)); }
    else if (block.type === "question") { root.appendChild(renderQuestion(block)); }
    else if (block.type === "feedback") { root.appendChild(renderFeedback(block)); }
    else if (block.type === "mock_result") { root.appendChild(renderMockResult(block)); }
    else if (block.type === "error") { root.appendChild(renderError(block)); }
  }

  function renderError(b) {
    return el("div", null, [
      el("p", { class: "result incorrect" }, "The tutor is unavailable"),
      el("div", { class: "block-body" }, markdown.block(b.message)),
      el("div", { class: "actions" }, el("button", {
        class: "btn secondary",
        onclick: function () { api.post({ type: "advance", unit: currentUnit, timestamp: iso() }).then(render); }
      }, "Try again"))
    ]);
  }

  function renderLesson(b) {
    return el("div", null, [
      gearTag(b),
      el("h2", { class: "block-title" }, markdown.inline(b.title)),
      el("div", { class: "block-body" }, markdown.block(b.body)),
      citations(b.citations),
      el("div", { class: "actions" }, el("button", {
        class: "btn",
        onclick: function () {
          api.post({ type: "advance", unit: b.unit, timestamp: iso() }).then(render);
        }
      }, "Continue"))
    ]);
  }

  function renderQuestion(b) {
    var selected = null;
    var submit;
    var opts = b.options.map(function (o) {
      return el("button", {
        class: "option",
        "aria-pressed": "false",
        onclick: function () {
          selected = o.id;
          opts.forEach(function (btn) { btn.setAttribute("aria-pressed", "false"); });
          this.setAttribute("aria-pressed", "true");
          submit.removeAttribute("disabled");
        }
      }, [o.id + ". ", markdown.inline(o.text)]);
    });
    submit = el("button", {
      class: "btn", disabled: true,
      onclick: function () {
        if (!selected) { return; }
        api.post({ type: "answer", question_id: b.question_id, unit: b.unit, selected_option: selected, timestamp: iso() }).then(render);
      }
    }, "Submit answer");
    return el("div", null, [
      gearTag(b),
      b.review ? el("p", { class: "mock-pos" }, "Review check on a unit you mastered earlier") : null,
      el("h2", { class: "block-title" }, markdown.inline(b.stem)),
      el("div", { class: "options" }, opts),
      el("div", { class: "actions" }, submit)
    ]);
  }

  // ---- practice exam ----------------------------------------------------
  var timer = { handle: null, deadline: 0 };

  function stopTimer() {
    if (timer.handle) { clearInterval(timer.handle); timer.handle = null; }
  }

  function startTimer(seconds, node, onExpire) {
    // One deadline for the whole attempt: it is set on the first question and
    // kept across questions, so the countdown is for the exam, not per item.
    if (!timer.deadline) { timer.deadline = Date.now() + seconds * 1000; }
    stopTimer();
    function tick() {
      var left = Math.max(0, Math.round((timer.deadline - Date.now()) / 1000));
      var m = Math.floor(left / 60), s = left % 60;
      node.textContent = m + ":" + (s < 10 ? "0" : "") + s + " left";
      node.classList.toggle("low", left < 120);
      if (left <= 0) { stopTimer(); timer.deadline = 0; onExpire(); }
    }
    tick();
    timer.handle = setInterval(tick, 1000);
  }

  function renderMockQuestion(b) {
    var selected = null;
    var submit;
    var opts = b.options.map(function (o) {
      return el("button", {
        class: "option",
        "aria-pressed": "false",
        onclick: function () {
          selected = o.id;
          opts.forEach(function (btn) { btn.setAttribute("aria-pressed", "false"); });
          this.setAttribute("aria-pressed", "true");
          submit.removeAttribute("disabled");
        }
      }, [o.id + ". ", markdown.inline(o.text)]);
    });
    submit = el("button", {
      class: "btn", disabled: true,
      onclick: function () {
        if (!selected) { return; }
        api.post({ type: "mock_answer", question_id: b.question_id, unit: b.unit, selected_option: selected, timestamp: iso() }).then(render);
      }
    }, b.position === b.total ? "Submit exam" : "Next question");
    var clock = el("span", { class: "mock-timer" });
    startTimer(b.time_limit_seconds, clock, function () {
      api.post({ type: "mock_submit", timestamp: iso() }).then(render);
    });
    return el("div", null, [
      el("div", { class: "mock-head" }, [
        el("span", { class: "mock-pos" }, "Practice exam \u00b7 question " + b.position + " of " + b.total),
        clock
      ]),
      el("h2", { class: "block-title" }, markdown.inline(b.stem)),
      el("div", { class: "options" }, opts),
      el("div", { class: "actions" }, submit)
    ]);
  }

  // The numbers of an attempt, decided before the tutor writes the debrief.
  function mockResultParts(b) {
    var rows = [];
    (b.by_task || []).forEach(function (t) {
      var pct = t.total ? Math.round(100 * t.correct / t.total) : 0;
      rows.push(el("span", null, "Task " + t.task));
      rows.push(el("div", { class: "bar" }, el("span", { style: "width:" + pct + "%" })));
      rows.push(el("span", null, t.correct + " / " + t.total));
    });
    return [
      el("p", { class: "mock-pos" }, "Practice exam result"),
      el("p", { class: "score" }, [b.score + " / " + b.total, el("span", { class: "pct" }, b.percent + "%")]),
      el("p", { class: "verdict " + (b.passed ? "pass" : "fail") },
        b.passed ? "Passed the " + b.pass_mark + "% mark" : "Below the " + b.pass_mark + "% mark"),
      el("div", { class: "bytask" }, rows),
      (b.missed_units && b.missed_units.length)
        ? el("p", { class: "missed" }, "Missed: " + b.missed_units.map(unitLabel).join(", "))
        : null
    ];
  }

  function renderMockResult(b) {
    timer.deadline = 0;
    return el("div", null, mockResultParts(b).concat([
      el("div", { class: "block-body" }, markdown.block(b.debrief)),
      citations(b.citations),
      el("div", { class: "actions" }, el("button", {
        class: "btn",
        onclick: function () { api.post({ type: "advance", unit: currentUnit, timestamp: iso() }).then(render); }
      }, "Back to the course"))
    ]));
  }

  function startMock() {
    timer.deadline = 0;
    api.post({ type: "mock_start", timestamp: iso() }).then(render);
  }

  function renderReadiness(state) {
    var node = document.getElementById("readiness");
    var r = state.readiness;
    node.innerHTML = "";
    if (!r) { return; }
    var btn = document.getElementById("mock-btn");
    btn.hidden = !state.mock_available || state.mock_in_progress;
    btn.textContent = "Practice exam" + (r.attempts ? " \u00b7 " + r.passes + "/" + r.passes_needed + " passed" : "");
    if (r.ready) {
      node.appendChild(el("div", { class: "ready" }, "Ready to schedule the real exam"));
      return;
    }
    node.appendChild(el("div", null, "Not yet ready for the real exam"));
    node.appendChild(el("ul", null, (r.reasons || []).map(function (x) { return el("li", null, x); })));
  }

  // Right or wrong is decided before the tutor writes, so it shows at once.
  function feedbackResult(b) {
    return el("div", null, [
      el("p", { class: "result " + (b.correct ? "correct" : "incorrect") }, b.correct ? "Correct" : "Not quite"),
      (!b.correct && b.correct_option) ? el("p", null, "The correct answer was " + b.correct_option + ".") : null
    ]);
  }

  function renderFeedback(b) {
    return el("div", null, [
      gearTag(b),
      feedbackResult(b),
      el("div", { class: "block-body" }, markdown.block(b.message)),
      citations(b.citations),
      el("div", { class: "actions" }, el("button", {
        class: "btn",
        onclick: function () {
          api.post({ type: "advance", unit: b.unit, timestamp: iso() }).then(render);
        }
      }, "Continue"))
    ]);
  }

  // ---- chat -------------------------------------------------------------
  // The conversation with the tutor. /api/ask streams one JSON object per
  // line: {"start"} and {"status"} for the indicator, {"delta"} pieces of
  // the answer, then {"done"} or {"error"}.
  var chat = { busy: false, paused: false };

  function chatMessage(m) {
    var kids = [el("div", { class: "msg-text" }, m.role === "student" ? m.text : markdown.block(m.text))];
    if (m.role === "tutor" && m.in_corpus === false && m.citations && m.citations.length) {
      kids.unshift(el("div", { class: "msg-note" }, "Not in the course material. These sources are from the web."));
    }
    if (m.role === "tutor") { kids.push(citations(m.citations)); }
    return el("div", { class: "msg " + m.role }, kids);
  }

  // New messages scroll into view; while an answer streams, the log follows it
  // only if the student has not scrolled up to read something earlier.
  function scrollChat(force) {
    var log = document.getElementById("chat-log");
    if (force || log.scrollHeight - log.scrollTop - log.clientHeight < 60) {
      log.scrollTop = log.scrollHeight;
    }
  }

  // A drawing in the chat is scaled down to the panel's width, which makes its
  // labels hard to read. A click shows it large in a dialog; a click anywhere
  // or Escape closes it.
  function enlargeDrawing(e) {
    if (!e.target.matches("img.drawn")) { return; }
    var dialog = el("dialog", {
      class: "enlarged",
      onclick: function () { dialog.close(); },
      onclose: function () { dialog.remove(); }
    }, el("img", { src: e.target.src, alt: e.target.alt }));
    document.body.appendChild(dialog);
    dialog.showModal();
  }

  function appendChat(node) {
    document.getElementById("chat-log").appendChild(node);
    scrollChat(true);
  }

  function showMeta(meta) {
    var node = document.getElementById("chat-meta");
    if (!meta || !meta.model) { node.textContent = ""; return; }
    var text = meta.model;
    if (meta.context_tokens) {
      text += " · context " + (meta.context_tokens / 1000).toFixed(1) + "k";
      if (meta.context_window) {
        text += " / " + (meta.context_window >= 1e6 ? meta.context_window / 1e6 + "M" : Math.round(meta.context_window / 1000) + "k");
      }
    }
    node.textContent = text;
  }

  function setChatState() {
    var input = document.getElementById("chat-input");
    input.disabled = chat.paused;
    input.placeholder = chat.paused ? "The chat is paused during the practice exam" : "Ask about anything in the course";
    document.getElementById("chat-send").disabled = chat.busy || chat.paused;
    document.getElementById("chat-mic").disabled = chat.paused;
    if (chat.paused) { Dictation.cancel(); }
  }

  // Read a response body as it arrives and pass on each complete JSON line.
  function readLines(body, onEvent) {
    var reader = body.getReader(), decoder = new TextDecoder(), buffer = "";
    function pump() {
      return reader.read().then(function (step) {
        buffer += decoder.decode(step.value || new Uint8Array(0), { stream: !step.done });
        var lines = buffer.split("\n");
        buffer = lines.pop();
        lines.forEach(function (line) { if (line.trim()) { onEvent(JSON.parse(line)); } });
        if (!step.done) { return pump(); }
        if (buffer.trim()) { onEvent(JSON.parse(buffer)); }
      });
    }
    return pump();
  }

  function sendChat(text) {
    if (!text.trim() || chat.busy || chat.paused) { return; }
    chat.busy = true;
    setChatState();
    appendChat(chatMessage({ role: "student", text: text }));
    var written = el("div", { class: "msg-text streaming-text" });
    var live = el("div", { class: "msg tutor" }, written);
    var status = null;
    appendChat(live);

    var payload = { type: "question", text: text, context_unit: currentUnit, timestamp: iso() };
    logSent(payload);
    streamRequest("ask", "/api/ask", payload, function (event) {
      if (event.start) {
        status = indicator(event.start);
        live.insertBefore(status.node, written);
      }
      if (event.status && status) { status.status(event.status); }
      if (event.delta !== undefined) {
        if (status) { status.writing(); }
        streamInto(written, event.delta);
        scrollChat(false);
      }
    }).then(function (final) {
      if (final.done) {
        live.replaceWith(chatMessage(final.message));
        showMeta(final.meta);
      } else {
        live.replaceWith(el("div", { class: "msg tutor error" }, final.error));
      }
    }).catch(function () {
      live.replaceWith(el("div", { class: "msg tutor error" }, "Could not reach the course server. Is it still running?"));
    }).then(function () {
      if (status) { status.stop(); }
      chat.busy = false;
      setChatState();
      scrollChat(false);
    });
  }

  function loadChat() {
    timedFetch("chat", "/api/chat").then(function (data) {
      (data.messages || []).forEach(function (m) { appendChat(chatMessage(m)); });
      showMeta(data.meta);
    });
  }

  // ---- course tree ------------------------------------------------------
  // The progress card draws the course as a tree (course-tree.js) from the
  // state the server derives from the ledger, and the intake page draws the
  // whole tree beside its card. A click on a lane or a unit opens the picker;
  // its Review sends a goto, and the server teaches that unit at that gear.
  var TASKS = {
    A: "General", B: "Operating Rules", C: "Remote Pilot Certification with an sUAS Rating",
    D: "Waivers", E: "Operations Over People", F: "Remote Identification (RID)"
  };
  var lastState = null, pickers = {}, glide = null;

  function currentOf(state) { return (state.units || []).filter(function (u) { return u.current; })[0]; }
  function unitById(state, id) { return (state.units || []).filter(function (u) { return u.id === id; })[0]; }
  // A unit code as people see it, or the bare code before the state arrives.
  function unitLabel(id) { var u = lastState && unitById(lastState, id); return u ? CourseTree.labelOf(u) : id; }

  // A glide the shell started is not the student scrolling away: when the
  // window is off the current unit, hold the recenter button until the window
  // arrives there (or, if it never does, for two seconds).
  function gliding() {
    clearTimeout(glide);
    glide = null;
    document.getElementById("tree-recenter").hidden = true;
    if (CourseTree.offCurrent(document.getElementById("course-tree"))) {
      glide = setTimeout(function () { glide = null; }, 2000);
    }
  }

  function renderMap(state, animate) {
    lastState = state;
    renderReadiness(state);
    document.getElementById("instructor-btn").hidden = !state.instructor;
    chat.paused = !!state.mock_in_progress;
    setChatState();
    document.getElementById("map-summary").textContent =
      (state.summary.mastered || 0) + " / " + (state.summary.total || 0);
    var cur = currentOf(state);
    document.getElementById("map-task-name").textContent =
      cur ? cur.number.split(".")[0] + " (Task " + cur.task + ") \u00b7 " + (TASKS[cur.task] || "") : "";
    if (pickers.sidebar) { pickers.sidebar.hide(); }
    var tree = document.getElementById("course-tree");
    CourseTree.render(tree, state, TASKS, "sidebar", !!animate, { width: tree.clientWidth });
    if (animate) { gliding(); }
    if (!document.getElementById("intake").hidden) {
      if (pickers.intake) { pickers.intake.hide(); }
      var fresh = (state.units || []).every(function (u) { return u.mastery === "unseen"; });
      document.getElementById("intake-summary").textContent =
        (state.summary.mastered || 0) + " of " + (state.summary.total || 0) + " mastered";
      CourseTree.render(document.getElementById("intake-tree"), state, TASKS, "full", false, { fresh: fresh });
    }
  }

  // The picker under a tree: the unit, its state, the speeds written for it,
  // and the three speeds as buttons with the clicked lane preselected.
  function picker(box, tree, onStart) {
    var title = box.querySelector(".tree-pick-title"), words = box.querySelector(".tree-pick-state");
    var gears = box.querySelectorAll(".tree-pick-gears button"), start = box.querySelector(".tree-pick-start");
    var chosen = null, said = "";
    function press() {
      Array.prototype.forEach.call(gears, function (b) {
        b.setAttribute("aria-pressed", String(Number(b.getAttribute("data-gear")) === chosen.gear));
      });
      // The state, then where the chosen speed's lesson comes from.
      var u = unitById(lastState, chosen.unit);
      words.textContent = said + " " + gearName(chosen.gear) + ": " + CourseTree.gearSource(u, chosen.gear) + ".";
      CourseTree.markSelected(tree, chosen.unit, chosen.gear);
    }
    function show(sel) {
      var u = lastState && unitById(lastState, sel.unit);
      if (!u || lastState.mock_in_progress || turn.busy) { return; }
      var written = CourseTree.writtenGears(u);
      chosen = { unit: u.id, gear: sel.gear && written.indexOf(sel.gear) >= 0 ? sel.gear : u.current_gear };
      title.textContent = CourseTree.labelOf(u) + " \u00b7 " + CourseTree.titleOf(u);
      said = (u.mastery === "unseen" ? "Not started"
        : (u.mastery === "mastered" ? "Mastered at gear " : "Learning at gear ") + u.current_gear + (u.parked ? ", set aside" : "")) + ".";
      Array.prototype.forEach.call(gears, function (b) {
        var g = Number(b.getAttribute("data-gear"));
        b.disabled = written.indexOf(g) < 0;
        b.title = b.disabled ? "Not written yet for this unit" : "";
      });
      start.textContent = u.mastery === "unseen" ? "Start here" : (u.current ? "Switch speed" : "Review");
      start.disabled = !written.length;
      box.hidden = false;
      press();
      start.focus();
    }
    function hide() {
      if (!box.hidden && box.contains(document.activeElement)) { tree.focus(); }
      box.hidden = true;
      chosen = null;
      CourseTree.markSelected(tree, null);
    }
    box.addEventListener("keydown", function (e) { if (e.key === "Escape") { hide(); } });
    Array.prototype.forEach.call(gears, function (b) {
      b.addEventListener("click", function () {
        if (chosen) { chosen.gear = Number(b.getAttribute("data-gear")); press(); }
      });
    });
    start.addEventListener("click", function () {
      if (!chosen) { return; }
      var sel = chosen;
      hide();
      onStart(sel);
    });
    box.querySelector(".tree-pick-cancel").addEventListener("click", hide);
    CourseTree.onSelect(tree, show);
    return { show: show, hide: hide };
  }

  // onError, when given, takes a refusal instead of the lesson panel showing it.
  function goTo(sel, onError) {
    if (turn.busy) { return; }
    api.post({ type: "goto", unit: sel.unit, gear: sel.gear, timestamp: iso() }).then(function (block) {
      if (onError && block.type === "error") { onError(block); } else { render(block); }
    });
  }

  // ---- sent log ---------------------------------------------------------
  function logSent(payload) {
    var log = document.getElementById("sent-log");
    log.insertBefore(el("pre", null, JSON.stringify(payload, null, 2)), log.firstChild);
  }

  // ---- intake and start -------------------------------------------------
  function chooseGear(g) {
    document.getElementById("intake").hidden = true;
    api.post({ type: "intake", default_gear: g, timestamp: iso() }).then(render);
  }

  // ---- wire up ----------------------------------------------------------
  document.addEventListener("DOMContentLoaded", function () {
    Array.prototype.forEach.call(document.querySelectorAll(".intake-btn"), function (btn) {
      btn.addEventListener("click", function () { chooseGear(Number(btn.getAttribute("data-gear"))); });
    });
    var input = document.getElementById("chat-input");
    function submitChat() {
      if (chat.busy || chat.paused || !input.value.trim()) { return; }
      Dictation.cancel();  // words still to come would land in the emptied box
      sendChat(input.value);
      input.value = "";
    }
    document.getElementById("chat-form").addEventListener("submit", function (e) {
      e.preventDefault();
      submitChat();
    });
    input.addEventListener("keydown", function (e) {
      // Enter sends; Shift+Enter starts a new line.
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
        e.preventDefault();
        submitChat();
      }
    });
    // The microphone (dictation.js) puts spoken words into the box; if it
    // fails, the chat says why.
    Dictation.attach(document.getElementById("chat-mic"), input, function (text) {
      appendChat(el("div", { class: "msg tutor error" }, text));
    });
    document.getElementById("mock-btn").addEventListener("click", startMock);
    document.getElementById("chat-log").addEventListener("click", enlargeDrawing);
    document.getElementById("key-lanes").innerHTML = CourseTree.laneGlyph();
    var tree = document.getElementById("course-tree"), recenter = document.getElementById("tree-recenter");
    tree.addEventListener("scroll", function () {
      var off = CourseTree.offCurrent(tree);
      if (glide && off) { return; }
      clearTimeout(glide);
      glide = null;
      recenter.hidden = !off;
    });
    recenter.addEventListener("click", function () { gliding(); CourseTree.scrollToCurrent(tree, true); });
    // The student sets the progress panel's width (panels.js): draw the tree
    // again at the new width, scrolled where it was.
    new ResizeObserver(function () {
      var drawn = tree.querySelector("svg");
      if (!lastState || !drawn || Number(drawn.getAttribute("width")) === tree.clientWidth) { return; }
      var top = tree.scrollTop;
      renderMap(lastState, false);
      tree.scrollTop = top;
    }).observe(tree);
    pickers.sidebar = picker(document.getElementById("tree-pick"), tree, goTo);
    pickers.intake = picker(document.getElementById("intake-pick"), document.getElementById("intake-tree"), function (sel) {
      // Picked from the first page: straight into that unit, at the pace of the
      // lane. A refusal keeps the first page, with the reason in the picker.
      document.getElementById("intake").hidden = true;
      goTo(sel, function (block) {
        document.getElementById("intake").hidden = false;
        pickers.intake.show(sel);
        document.querySelector("#intake-pick .tree-pick-state").textContent = block.message;
      });
    });
    // The instructor workspace (instructor.js) shares the streamed request, the
    // indicator, and the course state, and teaches a unit through the tree's goto.
    Instructor.init({
      streamRequest: streamRequest, indicator: indicator, streamInto: streamInto, el: el, citations: citations,
      units: function () { return (lastState && lastState.units) || []; },
      here: function () {
        var u = lastState && (unitById(lastState, currentUnit) || currentOf(lastState));
        return u ? { unit: u.id, gear: u.current_gear || 2 } : null;
      },
      refresh: function () { api.getState().then(renderMap); },
      tryIt: function (unit, gear) { goTo({ unit: unit, gear: gear }); }
    });
    api.getState().then(renderMap);
    loadChat();
  });
})();
