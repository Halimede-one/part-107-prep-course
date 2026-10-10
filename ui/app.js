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
      return streamRequest(payload.type, "/api/respond", payload, showProgress)
        .then(function (final) {
          return final.block || { type: "error", message: final.error };
        })
        .catch(function () {
          return { type: "error", message: "Could not reach the course server. Is it still running?" };
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
      block.unit ? el("span", { class: "unit-code" }, block.unit) : null
    ]);
  }

  function paragraphs(text) {
    return (text || "").split(/\n\s*\n/).map(function (p) { return el("p", null, p); });
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
    api.getState().then(renderMap);
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

  // Text arriving for one field: append it and move the caret there.
  function streamInto(target, text) {
    Array.prototype.forEach.call(document.querySelectorAll(".streaming-text.active"), function (n) {
      if (n !== target) { n.classList.remove("active"); }
    });
    target.classList.add("active");
    target.textContent += text;
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
      el("div", { class: "block-body" }, paragraphs(b.message)),
      el("div", { class: "actions" }, el("button", {
        class: "btn secondary",
        onclick: function () { api.post({ type: "advance", unit: currentUnit, timestamp: iso() }).then(render); }
      }, "Try again"))
    ]);
  }

  function renderLesson(b) {
    return el("div", null, [
      gearTag(b),
      el("h2", { class: "block-title" }, b.title),
      el("div", { class: "block-body" }, paragraphs(b.body)),
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
      }, o.id + ". " + o.text);
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
      el("h2", { class: "block-title" }, b.stem),
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
      }, o.id + ". " + o.text);
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
      el("h2", { class: "block-title" }, b.stem),
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
        ? el("p", { class: "missed" }, "Missed: " + b.missed_units.join(", "))
        : null
    ];
  }

  function renderMockResult(b) {
    timer.deadline = 0;
    return el("div", null, mockResultParts(b).concat([
      el("div", { class: "block-body" }, paragraphs(b.debrief)),
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
      el("div", { class: "block-body" }, paragraphs(b.message)),
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
    var kids = [el("div", { class: "msg-text" }, m.role === "student" ? m.text : paragraphs(m.text))];
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

  // ---- placeholder map --------------------------------------------------
  function renderMap(state) {
    renderReadiness(state);
    chat.paused = !!state.mock_in_progress;
    setChatState();
    document.getElementById("map-summary").textContent =
      (state.summary.mastered || 0) + " / " + (state.summary.total || 0);
    var wrap = document.getElementById("course-map");
    wrap.innerHTML = "";
    var byTask = {};
    (state.units || []).forEach(function (u) {
      (byTask[u.task] = byTask[u.task] || []).push(u);
    });
    Object.keys(byTask).forEach(function (task) {
      var grid = el("div", { class: "map-grid" }, byTask[task].map(function (u) {
        var cell = el("div", { class: "cell " + u.mastery + (u.current ? " current" : "") });
        cell.title = u.id + " (gears " + u.available_gears.join("/") + ")" + (u.parked ? ", set aside" : "");
        if (u.gears_taken && u.gears_taken.length > 1) { cell.appendChild(el("span", { class: "dot deeper" })); }
        if (u.needs_attention || u.parked) { cell.appendChild(el("span", { class: "dot attn" })); }
        return cell;
      }));
      wrap.appendChild(el("div", { class: "map-task" }, [el("span", { class: "lab" }, task), grid]));
    });
    wrap.appendChild(legend());
  }

  function legend() {
    function item(cls, dot, label) {
      var sw = el("span", { class: "sw " + cls });
      if (dot) { sw.appendChild(el("span", { class: "dot " + dot })); }
      return el("span", { class: "lg" }, [sw, label]);
    }
    return el("div", { class: "map-legend" }, [
      item("mastered", null, "Mastered"),
      item("learning", null, "Learning"),
      item("unseen", null, "Not started"),
      item("mastered current", null, "Current"),
      item("mastered", "deeper", "Deeper gear"),
      item("learning", "attn", "Needs attention")
    ]);
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
    document.getElementById("mock-btn").addEventListener("click", startMock);
    api.getState().then(renderMap);
    loadChat();
  });
})();
