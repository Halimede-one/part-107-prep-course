(function () {
  "use strict";

  // The instructor workspace: one lesson file at a time, edited by hand or with
  // the authoring assistant, and previewed as a student would see it. Its
  // Questions tab edits a unit's guidance and questions instead. It exists
  // only when the course runs with --instructor. app.js hands in what the two
  // share: the streamed request, the status indicator, the DOM helpers, the
  // course state, and the way to teach a unit.
  var deps = null;
  var GEARS = { 1: "Fast-track", 2: "Guided", 3: "Foundational" };
  var my = { unit: null, gear: null, file: null, saved: "", proposal: null, history: [], busy: false };
  var qs = { on: false, saved: "", sources: [], cards: 0 };  // the Questions tab
  var timer = null;

  function $(id) { return document.getElementById(id); }
  function text() { return $("author-text").value; }

  // ---- the file -----------------------------------------------------------
  // A lesson file: a header of source lines between two --- lines, then the body.
  function split(file) {
    if (file.indexOf("---") === 0) {
      var end = file.indexOf("\n---", 3);
      if (end >= 0) {
        var sources = file.slice(3, end).split("\n").map(function (line) {
          var m = /^\s*source:\s*(.*?)\s*\|\s*(\S+)\s*$/i.exec(line);
          return m ? { source: m[1], url: m[2] } : null;
        }).filter(Boolean);
        return { sources: sources, body: file.slice(end + 4).replace(/^[^\n]*\n?/, "") };
      }
    }
    return { sources: [], body: file };
  }

  // The body as the course shows it, with the sources under it.
  function preview(file, isProposal) {
    var parts = split(file), root = $("author-preview");
    root.innerHTML = "";
    root.appendChild(window.markdown.block(parts.body));
    var cites = deps.citations(parts.sources);
    if (cites) { root.appendChild(cites); }
    root.classList.toggle("proposal", !!isProposal);
    $("author-preview-label").textContent = isProposal ? "Proposal from the assistant, not applied" : "Preview, as a student sees it";
  }

  // While the assistant writes, the proposal is drawn again at most every 150 ms.
  function previewSoon(file) {
    clearTimeout(timer);
    timer = setTimeout(function () { preview(file, true); }, 150);
  }

  function changed() { return text() !== my.saved; }

  function markChanged() {
    $("author-dirty").hidden = !changed();
  }

  function say(message, warn) {
    var node = $("author-message");
    node.textContent = message || "";
    node.classList.toggle("warn", !!warn);
  }

  function describe(info) {
    var f = info.files[String(info.gear)], cell = (info.status || {})["gear " + info.gear];
    if (!f) {
      return info.gear === 2 ? "No Guided lesson yet, so the tutor cannot teach this unit."
        : "No file: the tutor builds " + GEARS[info.gear] + " from the Guided lesson.";
    }
    return (f.draft ? "Tutor draft, not yet reviewed" : "Lesson file") + (f.version ? ", version " + f.version : "") +
      (cell ? " · STATUS.md: " + cell : "");
  }

  function showProposal(on) {
    $("author-proposal").hidden = !on;
    if (!on) { my.proposal = null; preview(text()); }
  }

  function keepOrDiscard() {
    return !(qs.on ? questionsChanged() : changed()) || window.confirm("Discard the unsaved changes to this file?");
  }

  // ---- loading a file -----------------------------------------------------
  function load(unit, gear) {
    return fetch("/api/author?unit=" + encodeURIComponent(unit) + "&gear=" + gear)
      .then(function (r) { return r.json(); })
      .then(function (info) {
        if (info.error) { say(info.error, true); return; }
        my.unit = unit; my.gear = gear; my.file = info; my.saved = info.text; my.history = [];
        $("author-unit").value = unit;
        showQuestions(false);
        $("author-text").value = info.text;
        $("author-file").textContent = describe(info);
        $("author-empty").hidden = !!info.text;
        $("author-from-guided").hidden = gear === 2 || !info.guided;
        $("author-log").innerHTML = "";
        markChanged();
        showProposal(false);
        say("");
      });
  }

  // ---- the assistant ------------------------------------------------------
  function scrollLog() { var log = $("author-log"); log.scrollTop = log.scrollHeight; }

  // The assistant's finished reply: its note, and the changes it proposes as a diff.
  function reply(final) {
    var el = deps.el, added = 0, removed = 0;
    var lines = (final.diff || []).filter(function (line) { return !/^(---|\+\+\+) /.test(line); }).map(function (line) {
      var kind = line[0] === "+" ? "add" : line[0] === "-" ? "del" : line.indexOf("@@") === 0 ? "hunk" : "same";
      if (kind === "add") { added++; } else if (kind === "del") { removed++; }
      return el("span", { class: kind }, line + "\n");
    });
    var parts = [el("div", { class: "msg-text" }, window.markdown.block(final.note))];
    if (lines.length) {
      parts.push(el("details", { class: "changes" }, [
        el("summary", null, "Changes: " + added + " lines added, " + removed + " removed"),
        el("pre", { class: "diff" }, lines)
      ]));
    } else {
      parts.push(el("p", { class: "changes" }, "No change to the file."));
    }
    return el("div", { class: "msg tutor" }, parts);
  }

  function ask(request) {
    if (my.busy || !request.trim() || !my.unit) { return; }
    my.busy = true;
    $("author-send").disabled = true;
    $("author-log").appendChild(deps.el("div", { class: "msg student" }, deps.el("div", { class: "msg-text" }, request)));
    var note = deps.el("div", { class: "msg-text streaming-text" });
    var live = deps.el("div", { class: "msg tutor" }, note), status = null, proposal = "";
    $("author-log").appendChild(live);
    scrollLog();
    deps.streamRequest("author", "/api/author/ask", {
      unit: my.unit, gear: my.gear, text: text(), request: request, history: my.history
    }, function (event) {
      if (event.start) {
        // A second start is the server asking again, for the whole file, when
        // the changes did not fit: begin the reply afresh.
        if (status) { status.stop(); status.node.remove(); }
        note.textContent = "";
        proposal = "";
        status = deps.indicator(event.start);
        live.insertBefore(status.node, note);
      }
      if (event.status && status) { status.status(event.status); }
      if (event.delta !== undefined) {
        if (status) { status.writing(); }
        if (event.field === "note") { deps.streamInto(note, event.delta); scrollLog(); }
        // A whole file streams into the preview; changes show when they are applied.
        if (event.field === "file") { proposal += event.delta; previewSoon(proposal); }
      }
    }).then(function (final) {
      clearTimeout(timer);
      if (final.done) {
        live.replaceWith(reply(final));
        my.history.push({ role: "instructor", text: request }, { role: "assistant", text: final.note });
        my.proposal = final.text;
        preview(final.text, true);
        $("author-proposal").hidden = false;
      } else {
        live.replaceWith(deps.el("div", { class: "msg tutor error" }, final.error));
        showProposal(false);
      }
    }).catch(function () {
      live.replaceWith(deps.el("div", { class: "msg tutor error" }, "Could not reach the course server. Is it still running?"));
    }).then(function () {
      if (status) { status.stop(); }
      my.busy = false;
      $("author-send").disabled = false;
      scrollLog();
    });
  }

  // ---- saving -------------------------------------------------------------
  // The dialog asks what changed and whether the content is vetted; "Not yet"
  // comes first, so Enter in the note field never marks a file vetted. Its
  // buttons close it (method="dialog"); a click on "Not yet" or "Yes, vetted"
  // also saves, and Escape or Cancel saves nothing.
  var afterSave = null;

  function save(then) {
    Dictation.cancel();  // the dialog covers the request box
    afterSave = then || null;
    $("author-note").value = "";
    $("author-save-dialog").showModal();
    $("author-note").focus();
  }

  function saveAs(choice) {
    var then = afterSave;
    afterSave = null;
    fetch("/api/author/save", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ unit: my.unit, gear: my.gear, text: text(), note: $("author-note").value, vetted: choice === "vetted" })
    }).then(function (r) { return r.json(); }).then(function (result) {
      if (result.error) { say(result.error, true); return; }
      my.file = result.file;
      my.saved = result.file.text;
      $("author-text").value = result.file.text;
      $("author-file").textContent = describe(result.file);
      $("author-empty").hidden = true;
      markChanged();
      showProposal(false);
      say("Saved as version " + result.version + (choice === "vetted" ? ", vetted." : ", not yet vetted.") +
          (result.images.length ? " Drawings saved as " + result.images.join(", ") + "." : "") +
          (result.warnings.length ? " " + result.warnings.join(" ") : ""), result.warnings.length > 0);
      deps.refresh();
      if (then) { then(); }
    }).catch(function () { say("Could not reach the course server. Nothing was saved.", true); });
  }

  // ---- the questions ------------------------------------------------------
  // The Questions tab edits one unit's questions file: guidance for the tutor
  // who writes the unit's questions, and the instructor's own questions, which
  // the course asks first. The server checks them and gives new ones their ids.
  var FIELDS = ["stem", "a", "b", "c", "rationale", "source", "url"];

  // The lesson columns or the Questions tab, with its tab marked.
  function showQuestions(on) {
    qs.on = on;
    document.querySelector(".author-body").hidden = on;
    $("author-questions").hidden = !on;
    $("author-try").hidden = on;  // the instructor's own progress would count the questions as asked
    $("author-questions-tab").setAttribute("aria-selected", String(on));
    Array.prototype.forEach.call(document.querySelectorAll(".author-gears button[data-gear]"), function (b) {
      b.setAttribute("aria-selected", String(!on && Number(b.getAttribute("data-gear")) === my.gear));
    });
  }

  // One question as a card of fields. A new question has no id until it is saved.
  function card(item) {
    var el = deps.el, n = ++qs.cards, node;
    function control(tag, name, attrs) {
      var c = el(tag, attrs);
      c.id = "q" + n + "-" + name;
      c.setAttribute("data-field", name);
      return c;
    }
    function labelled(c, label) {
      return el("div", { class: "question-field" }, [el("label", { for: c.id }, label), c]);
    }
    var stem = control("textarea", "stem", { rows: "2" });
    var options = ["a", "b", "c"].map(function (key) {
      var letter = key.toUpperCase();
      var radio = el("input", { type: "radio", name: "q" + n + "-key", value: letter, "aria-label": letter + " is the answer" });
      var text = control("input", key, { type: "text" });
      radio.checked = item.answer === letter;
      text.value = item[key] || "";
      return el("div", { class: "question-option" }, [radio, el("label", { for: text.id }, letter), text]);
    });
    var rationale = control("textarea", "rationale", { rows: "2" });
    var source = control("select", "source", {}), url = control("input", "url", { type: "text" });
    var listed = qs.sources.slice();
    if (item.source && !listed.some(function (s) { return s.source === item.source; })) {
      listed.push({ source: item.source, url: item.url });
    }
    source.appendChild(el("option", { value: "" }, "Choose a source"));
    listed.forEach(function (s) { source.appendChild(el("option", { value: s.source }, s.source)); });
    stem.value = item.stem || "";
    rationale.value = item.rationale || "";
    source.value = item.source || "";
    url.value = item.url || "";
    source.addEventListener("change", function () {
      var chosen = listed.filter(function (s) { return s.source === source.value; })[0];
      if (chosen) { url.value = chosen.url; }
    });
    var remove = el("button", { type: "button", class: "btn secondary question-delete" }, "Delete");
    node = el("fieldset", { class: "question-card" }, [
      el("legend", null, ""),
      labelled(stem, "Question"),
      el("div", { class: "question-field" }, [el("span", { class: "question-hint" }, "Options, with the answer marked")].concat(options)),
      labelled(rationale, "Why the answer is right, for the tutor's feedback"),
      el("div", { class: "question-source" }, [labelled(source, "Source"), labelled(url, "Link")]),
      remove
    ]);
    node.setAttribute("data-item", item.item || "");
    remove.addEventListener("click", function () { node.remove(); renumber(); markQuestions(); });
    return node;
  }

  function renumber() {
    Array.prototype.forEach.call($("questions-list").children, function (node, i) {
      var id = node.getAttribute("data-item");
      node.querySelector("legend").textContent = "Question " + (i + 1) + " · " + (id || "new");
    });
  }

  function collect() {
    return Array.prototype.map.call($("questions-list").children, function (node) {
      var item = { item: node.getAttribute("data-item") }, key = node.querySelector("input[type=radio]:checked");
      FIELDS.forEach(function (name) { item[name] = node.querySelector("[data-field=" + name + "]").value; });
      item.answer = key ? key.value : "";
      return item;
    });
  }

  function snapshot() { return JSON.stringify([$("questions-guidance").value, collect()]); }
  function questionsChanged() { return snapshot() !== qs.saved; }
  function markQuestions() { $("questions-dirty").hidden = !questionsChanged(); }

  function fillQuestions(info) {
    qs.sources = info.sources || [];
    $("questions-guidance").value = info.guidance;
    $("questions-list").innerHTML = "";
    info.items.forEach(function (item) { $("questions-list").appendChild(card(item)); });
    renumber();
    qs.saved = snapshot();
    markQuestions();
    var n = info.items.length;
    $("author-file").textContent = (n ? n + (n === 1 ? " question" : " questions") + ", asked before the tutor writes its own"
      : "No questions of your own: the tutor writes them all") + (info.guidance ? ", with guidance." : ", no guidance.");
  }

  function loadQuestions(unit) {
    Dictation.cancel();  // the request box goes out of reach
    return fetch("/api/author/questions?unit=" + encodeURIComponent(unit))
      .then(function (r) { return r.json(); })
      .then(function (info) {
        if (info.error) { say(info.error, true); return; }
        my.unit = unit;
        $("author-unit").value = unit;
        $("questions-problems").hidden = true;
        fillQuestions(info);
        showQuestions(true);
        say("");
      });
  }

  // The server checks every question and saves nothing if one fails; the
  // problems show above the cards, and the edits stay.
  function saveQuestions() {
    fetch("/api/author/questions", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ unit: my.unit, guidance: $("questions-guidance").value, items: collect() })
    }).then(function (r) { return r.json(); }).then(function (result) {
      var list = $("questions-problems"), problems = result.problems || [];
      list.innerHTML = "";
      problems.forEach(function (p) { list.appendChild(deps.el("li", null, p)); });
      list.hidden = !problems.length;
      if (!result.saved) { say(result.error, true); return; }
      fillQuestions(result);
      say("Saved the guidance and " + result.items.length + (result.items.length === 1 ? " question." : " questions."));
    }).catch(function () { say("Could not reach the course server. Nothing was saved.", true); });
  }

  // ---- opening and closing ------------------------------------------------
  function open() {
    Dictation.cancel();  // the workspace covers the chat
    var units = deps.units(), select = $("author-unit"), here = deps.here() || {};
    select.innerHTML = "";
    units.forEach(function (u) {
      select.appendChild(deps.el("option", { value: u.id }, u.number + " (" + u.id + ") · " + (u.title || "").replace(/\.$/, "")));
    });
    $("author").hidden = false;
    load(here.unit || (units[0] && units[0].id), here.gear || 2).then(function () { $("author-text").focus(); });
  }

  function close() {
    if (!keepOrDiscard()) { return; }
    Dictation.cancel();
    $("author").hidden = true;
    $("instructor-btn").focus();
  }

  function init(shared) {
    deps = shared;
    $("instructor-btn").addEventListener("click", open);
    $("author-close").addEventListener("click", close);
    $("author").addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !$("author-save-dialog").open) { e.preventDefault(); close(); }
      if (e.key === "s" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); if (qs.on) { saveQuestions(); } else { save(); } }
    });
    $("author-unit").addEventListener("change", function () {
      var unit = this.value;
      if (!keepOrDiscard()) { this.value = my.unit; } else if (qs.on) { loadQuestions(unit); } else { load(unit, my.gear); }
    });
    Array.prototype.forEach.call(document.querySelectorAll(".author-gears button[data-gear]"), function (b) {
      b.addEventListener("click", function () {
        var gear = Number(b.getAttribute("data-gear"));
        if ((gear !== my.gear || qs.on) && keepOrDiscard()) { load(my.unit, gear); }
      });
    });
    $("author-questions-tab").addEventListener("click", function () {
      if (!qs.on && keepOrDiscard()) { loadQuestions(my.unit); }
    });
    $("questions-add").addEventListener("click", function () {
      var node = card({});
      $("questions-list").appendChild(node);
      renumber();
      markQuestions();
      node.querySelector("textarea").focus();
    });
    ["input", "change"].forEach(function (kind) { $("author-questions").addEventListener(kind, markQuestions); });
    $("author-text").addEventListener("input", function () {
      markChanged();
      $("author-empty").hidden = true;
      if (!my.proposal) { clearTimeout(timer); timer = setTimeout(function () { preview(text()); }, 150); }
    });
    $("author-from-guided").addEventListener("click", function () {
      $("author-text").value = my.file.guided;
      $("author-empty").hidden = true;
      markChanged();
      preview(text());
    });
    $("author-first").addEventListener("click", function () {
      ask("Write a first version of the " + GEARS[my.gear] + " file for this unit" +
          (my.gear === 2 ? "." : ", from the Guided lesson."));
    });
    $("author-apply").addEventListener("click", function () {
      $("author-text").value = my.proposal;
      $("author-empty").hidden = true;
      markChanged();
      showProposal(false);
    });
    $("author-discard").addEventListener("click", function () { showProposal(false); });
    $("author-form").addEventListener("submit", function (e) {
      e.preventDefault();
      var input = $("author-request");
      if (my.busy || !input.value.trim()) { return; }
      Dictation.cancel();  // words still to come would land in the emptied box
      ask(input.value);
      input.value = "";
    });
    $("author-request").addEventListener("keydown", function (e) {
      // Enter sends; Shift+Enter starts a new line.
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
        e.preventDefault();
        $("author-form").requestSubmit();
      }
    });
    // The microphone (dictation.js) puts spoken words into the request box; if
    // it fails, the assistant column says why. It stops when the box goes out
    // of reach: on Send, Save, Close, and Try it.
    Dictation.attach($("author-mic"), $("author-request"), function (message) {
      $("author-log").appendChild(deps.el("div", { class: "msg tutor error" }, message));
      scrollLog();
    });
    $("author-save").addEventListener("click", function () { if (qs.on) { saveQuestions(); } else { save(); } });
    Array.prototype.forEach.call(document.querySelectorAll("#author-save-dialog button"), function (b) {
      b.addEventListener("click", function () {
        if (b.value === "vetted" || b.value === "edited") { saveAs(b.value); } else { afterSave = null; }
      });
    });
    $("author-revert").addEventListener("click", function () {
      if (!keepOrDiscard()) { return; }
      if (qs.on) { loadQuestions(my.unit); } else { load(my.unit, my.gear); }
    });
    $("author-try").addEventListener("click", function () {
      function tryIt() {
        Dictation.cancel();
        $("author").hidden = true;
        deps.tryIt(my.unit, my.gear);
      }
      if (changed()) { save(tryIt); } else { tryIt(); }
    });
  }

  window.Instructor = { init: init, split: split };
}());
