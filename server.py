"""The course server: standard library only, so the course runs from a folder.

The server owns the plumbing and the parts that must be reliable: it scores
answers, records attempts, and never lets a key reach the browser. Which unit,
gear, and stage come next are decided in orchestrator.py; how to teach and what
to ask are decided by the model through the stage prompts.
"""

import argparse
import difflib
import json
import os
import re
import tempfile
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import items as items_module
import ledger as ledger_module
import mockexam
import orchestrator
import retrieval
import status
from llm_client import LLMClient, LLMError, load_config

ROOT = os.path.dirname(os.path.abspath(__file__))

# The mock provider is keyed on the kind of block a stage produces.
_MOCK_STAGE = {
    "teach": "lesson",
    "remediate": "lesson",
    "quiz": "question",
    "score_diagnose": "feedback",
    "mock_gate": "debrief",
    "qa": "qa",
    "author": "revision",
}

# Earlier chat messages sent with each new question, so follow-ups make sense.
CHAT_MEMORY = 6

# Responses that move the teaching flow. A prefetch started while handling one
# of them is used by the next one, or not at all.
_FLOW = ("intake", "advance", "goto", "answer")

# Foundational drafts being written on background threads, by file path.
_DRAFTING = {}
_DRAFTING_LOCK = threading.Lock()


def wait_for_drafts(timeout=10):
    """Wait until every background draft has been written (for tests)."""
    with _DRAFTING_LOCK:
        threads = list(_DRAFTING.values())
    for thread in threads:
        thread.join(timeout)


def replace_file(path, text):
    """Write a file in one step, so a reader never sees half of it."""
    handle, temporary = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".save-")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            out.write(text)
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


def _header(text):
    """Split a lesson file into its header lines and the rest, which starts at
    the closing ---. A file without a complete header gives (None, text)."""
    if text.startswith("---"):
        head, found, rest = text[3:].partition("\n---")
        if found:
            return [line for line in head.split("\n") if line.strip()], "\n---" + rest
    return None, text


def _course_line(line):
    return line.split(":", 1)[0].strip().lower() in ("version", "draft")


def editor_text(path):
    """A lesson file as the instructor edits it: the source lines and the body.
    The version and the draft mark are the course's to keep; "" when there is
    no file."""
    if not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8") as handle:
        lines, rest = _header(handle.read())
    if lines is None:
        return rest
    return "---\n" + "".join(line + "\n" for line in lines if not _course_line(line)) + rest.lstrip("\n")


def with_version(text, version):
    """The editor text with the course's header lines: the version, and no
    draft mark, since an instructor has now saved it."""
    lines, rest = _header(text)
    if lines is None:
        return "---\nversion: %d\n---\n%s" % (version, text)
    kept = [line for line in lines if not _course_line(line)] + ["version: %d" % version]
    return "---\n" + "".join(line + "\n" for line in kept) + rest.lstrip("\n")


# A drawing the assistant made: a fenced block that starts ```svg <description>.
_DRAWING = re.compile(r"^```svg[ \t]*(?P<description>[^\n]*)\n(?P<svg><svg\b.*?</svg>)\s*\n```[ \t]*$",
                      re.S | re.M | re.I)
_UNSAFE_SVG = re.compile(r"<script|<foreignObject|\son\w+\s*=|javascript:|(?:xlink:)?href\s*=\s*['\"](?!#)", re.I)


def store_drawings(text, unit, folder):
    """Move each drawing into its own SVG file in the curriculum's images folder
    and put a Markdown image in its place, so the tutor shows the same reviewed
    picture every time. Returns the new text and the files written. Raises
    ValueError for a drawing that could run code."""
    drawings = list(_DRAWING.finditer(text))
    for match in drawings:
        if _UNSAFE_SVG.search(match.group("svg")):
            raise ValueError("A drawing holds a script, an event handler, or a link, so it was not saved. "
                             "Ask the assistant to draw it again with shapes and text only.")
    if not drawings:
        return text, []
    os.makedirs(folder, exist_ok=True)
    taken = [int(m.group(1)) for m in (re.match(r"%s-(\d+)\.svg$" % re.escape(unit), n) for n in os.listdir(folder)) if m]
    number, written = max(taken or [0]), []

    def store(match):
        nonlocal number
        number += 1
        name = "%s-%d.svg" % (unit, number)
        svg = match.group("svg")
        if "xmlns=" not in svg.split(">", 1)[0]:
            svg = svg.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"', 1)
        replace_file(os.path.join(folder, name), svg + "\n")
        written.append("images/" + name)
        description = match.group("description").strip().replace("]", "") or "Diagram"
        return "![%s](images/%s)" % (description, name)

    return _DRAWING.sub(store, text), written


def write_new(path, text):
    """Write a file that must not exist yet. The file appears complete or not at
    all, and an existing file is left alone. Returns whether it was written."""
    folder = os.path.dirname(path)
    handle, temporary = tempfile.mkstemp(dir=folder, prefix=".new-")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            out.write(text)
        os.link(temporary, path)
        return True
    except FileExistsError:
        return False
    finally:
        os.unlink(temporary)

# Pictures the curriculum may show, served from its images folder at /images/.
IMAGE_TYPES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".svg": "image/svg+xml", ".webp": "image/webp",
}

# Streaming: the text fields of each stage's block that are shown while the
# model writes them, and what the status indicator says. The quiz streams only
# its stem; the key and the rationale never leave the server.
_STREAMED = {
    "teach": ("title", "body"),
    "remediate": ("title", "body"),
    "quiz": ("stem",),
    "score_diagnose": ("message",),
    "mock_gate": ("body",),
    "qa": ("answer",),
    "author": ("note", "text"),
}
_STATUS = {
    "teach": "Writing your lesson",
    "remediate": "Writing a new explanation",
    "quiz": "Writing a question",
    "score_diagnose": "Explaining the answer",
    "mock_gate": "Writing your exam debrief",
    "qa": "Writing the answer",
    "author": "Revising the lesson",
}
# The status once a streamed field is complete and the model writes the rest.
_STATUS_AFTER = {
    ("teach", "body"): "Adding the sources",
    ("remediate", "body"): "Adding the sources",
    ("quiz", "stem"): "Writing the answer options",
    ("score_diagnose", "message"): "Adding the sources",
    ("qa", "answer"): "Adding the sources",
    ("author", "note"): "Writing the revised file",
}
# The status while the chat tutor runs a tool, by the tool's name.
_SEARCHING = {
    "Read": "Searching the course material",
    "Grep": "Searching the course material",
    "Glob": "Searching the course material",
    "WebSearch": "Searching the web",
    "WebFetch": "Searching the web",
}


class Session:
    """Transient per-session state. Everything durable lives in the ledger."""

    def __init__(self):
        self.stage = None          # teach, quiz, feedback, review_quiz, review_feedback, done
        self.pending = None        # the question awaiting an answer, with its key
        self.next_action = None    # (action, gear) decided when the answer was scored
        self.asked = {}            # unit -> question ids already used this session
        self.misconception = None  # what the last wrong choice suggests, for remediation
        self.review_queue = []     # units awaiting a spaced-review check at a task boundary
        self.reviewing = None      # the unit whose review question is on screen
        self.returning = set()     # units unparked at the last boundary, for the remediate framing
        self.chosen = None         # a unit picked from the course tree, in play until mastered or set aside
        self.mock = None           # the practice-exam attempt in progress, if any
        self.resume_stage = None   # where the course was when the exam started


class Course:
    """Everything the request handler needs, assembled once at startup."""

    # Each request runs in its own thread, and a chat answer can overlap a
    # lesson, so the per-request record of model calls is kept per thread.
    _local = threading.local()

    def __init__(self, config_path=os.path.join(ROOT, "config.json"), instructor=False):
        self.config = load_config(config_path)
        # The instructor workspace edits the course material, so it exists only
        # when the course is started for an instructor.
        self.instructor = bool(instructor or self.config.get("instructor"))
        self.paths = {key: os.path.join(ROOT, value) for key, value in self.config["paths"].items()}
        self.client = LLMClient(self.config)
        self.items = items_module.load_items(self.paths["items"])
        self.chunks = retrieval.load_chunks(self.paths["knowledge_base"])
        self.tutor = orchestrator.Orchestrator(self.paths)
        self.ledger = ledger_module.Ledger.open_or_bootstrap(
            self.paths["ledger"], self.paths["objectives"], area=self.config.get("area", "Regulations")
        )
        self.session = Session()
        self.chat = []       # the conversation in the chat panel, for this server run
        self.chat_meta = {}  # model and context use of the last chat answer
        self.prefetches = {}  # (stage, message) -> Prefetch, calls started before they are needed
        self.turn = 0         # teaching-flow responses handled, so a prefetch knows when it went stale

    @property
    def calls(self):
        """Model calls made while handling the current request, for metrics."""
        if not hasattr(self._local, "calls"):
            self._local.calls = []
        return self._local.calls

    @calls.setter
    def calls(self, value):
        self._local.calls = value

    # ---- model ----------------------------------------------------------
    def generate(self, stage, context, preview=None):
        """Call the model for one stage and parse its block.

        When the request streams, the page first gets a "start" event with the
        status text and the parts of the block already known (`preview`), then
        the stage's text fields as the model writes them. A prefetch with the
        same stage and message stands in for the call; if it is still writing,
        the page gets the text so far at once and then the rest.
        """
        emit = getattr(self._local, "emit", None)
        forward = on_tool = begin = None
        if emit:
            live = {}

            def begin():
                emit({"start": {"stage": stage, "status": _STATUS.get(stage, "Writing"),
                                "model": self.client.model_name, "block": preview or {}}})
                live["fields"] = FieldStream(_STREAMED.get(stage, ()))
                live["searched"] = []  # set while a search status is showing

            def forward(chunk):
                for field, text, closed in live["fields"].feed(chunk):
                    if text:
                        if live["searched"]:
                            live["searched"].clear()
                            emit({"status": _STATUS.get(stage, "Writing")})
                        emit({"delta": text, "field": field})
                    if closed and (stage, field) in _STATUS_AFTER:
                        emit({"status": _STATUS_AFTER[(stage, field)]})

            def on_tool(name):
                if name in _SEARCHING:
                    live["searched"].append(name)
                    emit({"status": _SEARCHING[name]})

            begin()

        started = time.perf_counter()
        job = self.prefetches.pop((stage, context), None)
        if job is not None:
            ready = job.finished
            raw = job.follow(forward)
            if job.error is None:
                self.calls.append(dict(job.metrics, stage=stage, ms=round((time.perf_counter() - started) * 1000),
                                       prefetched="ready" if ready else "joined", written_ms=job.ms))
            else:
                # The early call failed. Make it now, from a clean start on the
                # page if the failed call had already shown some text.
                self.log_prefetch(job, "failed")
                if begin and job.chunks:
                    begin()
        if job is None or job.error is not None:
            # Only the chat and the authoring assistant may search, and only on a
            # backend that runs its own tools.
            research = self.research_dirs() if stage in ("qa", "author") and self.client.supports_course_search else None
            try:
                raw = self.client.complete(
                    self.tutor.system(stage), context, stage=_MOCK_STAGE.get(stage, "lesson"), on_text=forward,
                    research_dirs=research, on_tool=on_tool,
                )
            except LLMError as error:
                self.record_call(stage, started, error=True)
                return {"type": "error", "message": str(error)}
            self.record_call(stage, started)
        block = _parse_json_block(raw)
        if block is None:
            # Flagged in the metrics with the start of the reply, so a format
            # problem can be seen rather than guessed at.
            self.calls[-1].update(error="unparseable", reply=(raw or "")[:300])
            return {"type": "error", "message": "The tutor returned a response that was not a valid block."}
        return block

    def research_dirs(self):
        """The folders the chat tutor may read: the knowledge base first, as its
        working directory, then the lessons and the folder of the reference facts.
        Never the course root, which holds the practice-exam keys and the
        student's progress. A folder not built yet is left out."""
        folders = [self.paths["knowledge_base"], self.paths["curriculum"], os.path.dirname(self.paths["reference"])]
        return [folder for folder in folders if os.path.isdir(folder)]

    def record_call(self, stage, started, error=False):
        call = dict(self.client.last_metrics, stage=stage, ms=round((time.perf_counter() - started) * 1000))
        if error:
            call["error"] = True
        self.calls.append(call)

    # ---- prefetch ---------------------------------------------------------
    def prefetch(self, call):
        """Start the model call that Continue will make next, on a background
        thread, so it is written while the student reads. It is used only if
        the real call has the same stage and message (see `generate`), so a
        wrong guess costs one unused call, never a wrong block."""
        if call is None:
            return
        key = (call["stage"], call["context"])
        job = self.prefetches.get(key)
        if job is None:
            job = self.prefetches[key] = Prefetch(self, *key)
        job.turn = self.turn

    def drop_stale_prefetches(self):
        """A prefetch serves the response after the one that started it, or none."""
        for key, job in list(self.prefetches.items()):
            if job.turn < self.turn:
                del self.prefetches[key]
                self.log_prefetch(job, "unused")

    def log_prefetch(self, job, outcome):
        """Note a prefetch that was not used, so the cost of wrong guesses shows."""
        log_metrics(self.paths["metrics"], dict(
            job.metrics, source="server", kind="prefetch", stage=job.stage, outcome=outcome,
            finished=job.finished, ms=job.ms if job.finished else round((time.perf_counter() - job.started) * 1000),
        ))

    def unit_gear(self, unit):
        return self.ledger.units.get(unit, {}).get("current_gear", self.ledger.default_gear)

    def lesson_gear(self, unit, gear=None):
        return min(gear or self.unit_gear(unit), max(self.gears_for(unit)))

    def lesson_call(self, unit, stage="teach", gear=None, chosen=False):
        """The model call that teaches a unit: its stage, gear, and message, or
        None when there is no content at that gear. A unit just missed, or
        returning after being set aside, is re-taught from a fresh angle."""
        gear = self.lesson_gear(unit, gear)
        content = self.tutor.content(unit, gear)
        if content is None:
            return None
        returning = unit in self.session.returning
        if stage == "remediate" or returning:
            context = self.tutor.remediate_context(unit, gear, content, self.session.misconception, returning=returning)
            return {"stage": "remediate", "gear": gear, "context": context, "form": content["form"]}
        return {"stage": "teach", "gear": gear, "context": self.tutor.teach_context(unit, gear, content, chosen=chosen),
                "form": content["form"]}

    def quiz_call(self, unit, review=False):
        """The model call that asks a question on a unit, or None when there is
        no unit or no content at its gear."""
        if unit is None:
            return None
        gear = self.unit_gear(unit)
        content = self.tutor.content(unit, gear)
        if content is None:
            return None
        context = self.tutor.quiz_context(unit, gear, content, self.session.asked.get(unit, []), review=review)
        return {"stage": "quiz", "gear": gear, "context": context}

    def call_after_answer(self, review):
        """The model call that Continue will make after this answer's feedback,
        worked out as advance() works it out but without changing anything.
        None when it cannot be known yet: a task boundary or the end of the area."""
        action, gear = self.session.next_action or (None, None)
        if not review and action == "quiz":
            return self.quiz_call(self.session.chosen or orchestrator.current_unit(self.ledger))
        if not review and action == "remediate":
            unit = self.session.chosen or orchestrator.current_unit(self.ledger)
            return self.lesson_call(unit, "remediate", gear) if unit else None
        # A mastered or set-aside unit, and every review, go on through between_units().
        if self.session.review_queue:
            return self.quiz_call(self.session.review_queue[0], review=True)
        if orchestrator.boundary_due(self.ledger):
            return None
        unit = orchestrator.current_unit(self.ledger)
        return self.lesson_call(unit) if unit else None

    # ---- turns ----------------------------------------------------------
    def gears_for(self, unit):
        return ledger_module.available_gears(unit, self.paths["curriculum"])

    def teach(self, stage="teach", gear=None, chosen=False):
        unit = self.session.chosen or orchestrator.current_unit(self.ledger)
        if unit is None:
            return self.done_block()

        call = self.lesson_call(unit, stage, gear, chosen)
        if call is None:
            return self.missing_content(unit, self.lesson_gear(unit, gear))

        self.ledger.set_gear(unit, call["gear"])
        self.save_ledger()
        self.session.returning.discard(unit)

        # The question on this unit does not depend on the lesson, so it is
        # written alongside it and is ready when the student continues.
        self.prefetch(self.quiz_call(unit))
        block = self.generate(call["stage"], call["context"],
                              preview={"type": "lesson", "unit": unit, "gear": call["gear"]})
        if call["gear"] == 3 and call["form"] == "derived":
            # The unit has no Foundational file yet. A lesson the student picked
            # is general and becomes the draft; a re-teach starts from one
            # student's mistake, so a general draft is written separately.
            if call["stage"] == "teach":
                self.save_draft(unit, block)
            else:
                self.draft_in_background(unit)
        self.session.stage = "teach"
        return block

    # ---- Foundational drafts ----------------------------------------------
    def save_draft(self, unit, block):
        """Keep the tutor's first Foundational lesson for a unit as its
        .gear3.md, marked as a draft, so later students and instructors start
        from it. An existing file is never replaced."""
        if block.get("type") != "lesson" or not (block.get("body") or "").strip():
            return
        cited = [(c.get("source", ""), c.get("url", "")) for c in block.get("citations") or [] if c.get("url")]
        if not cited:
            guided = self.tutor.content(unit, 2) or {"sources": []}
            cited = [(s["source"], s["url"]) for s in guided["sources"]]
        header = "".join("source: %s | %s\n" % (name.replace("|", "/"), url) for name, url in cited)
        text = ("---\n%sversion: 1\ndraft: written by the tutor on %s from the Guided lesson; "
                "no instructor has reviewed it\n---\nObjective: %s\n\n%s\n") % (
            header, time.strftime("%Y-%m-%d"), self.tutor.objectives.get(unit, ""), block["body"].strip())
        if write_new(orchestrator.lesson_path(self.paths["curriculum"], unit, 3), text):
            status.record(os.path.join(self.paths["curriculum"], "STATUS.md"), unit, 3, "tutor draft v1",
                          note="Foundational draft written by the tutor; review it in the instructor interface.")
            log_metrics(self.paths["metrics"], {"source": "server", "kind": "draft", "unit": unit, "gear": 3})

    def draft_in_background(self, unit):
        """Write a general Foundational lesson for the unit on a background
        thread and save it as the draft, once per unit."""
        path = orchestrator.lesson_path(self.paths["curriculum"], unit, 3)
        content = self.tutor.content(unit, 3)
        if content is None or content["form"] != "derived":
            return
        with _DRAFTING_LOCK:
            if path in _DRAFTING:
                return
            context = self.tutor.teach_context(unit, 3, content)

            def run():
                try:
                    block = _parse_json_block(self.client.complete(self.tutor.system("teach"), context, stage="lesson"))
                    if block:
                        self.save_draft(unit, block)
                except (LLMError, OSError):
                    pass  # a draft is a convenience; without one the tutor keeps building Foundational from Guided
                finally:
                    with _DRAFTING_LOCK:
                        _DRAFTING.pop(path, None)

            _DRAFTING[path] = threading.Thread(target=run, daemon=True)
            _DRAFTING[path].start()

    def goto(self, payload):
        """The student picked a unit and a gear from the course tree. Teach it
        now at that gear. The unit stays in play until it is mastered or set
        aside; then the course resumes from the ledger as usual."""
        if self.session.mock is not None:
            return {"type": "error", "message": "Finish the practice exam first."}
        unit = payload.get("unit")
        if not isinstance(unit, str) or unit not in self.ledger.units:
            return {"type": "error", "message": "Unknown unit %r." % unit}
        try:
            gear = int(payload.get("gear") or self.ledger.units[unit]["current_gear"])
        except (TypeError, ValueError):
            gear = self.ledger.units[unit]["current_gear"]
        gear = max(1, min(gear, max(self.gears_for(unit))))
        if self.tutor.content(unit, gear) is None:
            return self.missing_content(unit, gear)
        self.session.chosen = unit
        self.session.pending = None
        self.session.next_action = None
        self.session.reviewing = None
        return self.teach(gear=gear, chosen=True)

    def done_block(self):
        """The end of the area. Parked units, if any, are offered for another try."""
        self.session.stage = "done"
        parked = self.ledger.parked_units()
        if parked:
            return {
                "type": "lesson",
                "gear": self.ledger.default_gear,
                "title": "Every unit is mastered except the ones set aside",
                "body": "These units were set aside after repeated misses: %s.\n\n"
                        "Readiness for the real exam needs all of them mastered. Continue "
                        "to try them again, and use the ask box if a different explanation "
                        "would help." % ", ".join(parked),
                "citations": [],
            }
        return {
            "type": "lesson",
            "gear": self.ledger.default_gear,
            "title": "Every unit in this area is mastered",
            "body": "You have worked through all of the tracked units. The practice exam is "
                    "the next step: two passes at 85 percent or better are the readiness "
                    "bar for scheduling the real test.",
            "citations": [],
        }

    def quiz(self, unit=None, review=False):
        unit = unit or self.session.chosen or orchestrator.current_unit(self.ledger)
        if unit is None:
            return self.done_block()
        call = self.quiz_call(unit, review)
        if call is None:
            return self.missing_content(unit, self.unit_gear(unit))

        block = self.generate(
            "quiz", call["context"],
            preview={"type": "question", "unit": unit, "gear": call["gear"], "review": review},
        )
        if block.get("type") == "question":
            # The key stays on the server. The browser never sees it.
            block["unit"] = unit
            self.session.pending = dict(block)
            self.session.asked.setdefault(unit, []).append(block.get("question_id", ""))
            block = {k: v for k, v in block.items() if k not in ("answer", "rationale")}
            if review:
                block["review"] = True
        self.session.stage = "review_quiz" if review else "quiz"
        self.session.reviewing = unit if review else None
        return block

    def missing_content(self, unit, gear):
        return {
            "type": "error",
            "message": "There is no vetted content for %s at gear %d yet, so the tutor has "
                       "nothing to teach from. Teaching this unit from the model's own "
                       "knowledge is not allowed, because a wrong regulation taught "
                       "confidently is worse than a gap." % (unit, gear),
        }

    # ---- response handling ----------------------------------------------
    def handle(self, payload, emit=None):
        """Handle one posted response and return the next block. With `emit`,
        progress events go to it while the model writes (see `generate`)."""
        self._local.emit = emit
        if payload.get("type") not in _FLOW:
            return self.dispatch(payload)
        self.turn += 1
        try:
            return self.dispatch(payload)
        finally:
            self.drop_stale_prefetches()

    def dispatch(self, payload):
        kind = payload.get("type")
        self.log_response(payload)

        if kind == "intake":
            self.ledger.set_default_gear(int(payload.get("default_gear", 1)))
            if self.ledger.last_task is None:
                self.ledger.last_task = orchestrator.next_task(self.ledger)
            self.save_ledger()
            self.session = Session()
            return self.teach()

        if kind == "advance":
            return self.advance()

        if kind == "goto":
            return self.goto(payload)

        if kind == "answer":
            return self.handle_answer(payload)

        if kind == "question":
            return self.handle_question(payload)

        if kind == "mock_start":
            return self.mock_start(payload)

        if kind == "mock_answer":
            return self.mock_answer(payload)

        if kind == "mock_submit":
            return self.mock_finish(payload)

        return {"type": "error", "message": "Unknown response type %r." % kind}

    # ---- practice exam ----------------------------------------------------
    def mock_time_limit(self):
        per_item = int(self.config.get("mock", {}).get("minutes_per_item", mockexam.MINUTES_PER_ITEM))
        return per_item * 60 * len(mockexam.mock_items(self.items))

    def mock_start(self, payload):
        if not mockexam.mock_items(self.items):
            return {
                "type": "error",
                "message": "The practice exam has no vetted items yet, so it cannot be taken. "
                           "It arrives with the mock exam content.",
            }
        self.session.mock = mockexam.new_attempt(self.items, seed=payload.get("timestamp"))
        self.session.resume_stage = self.session.stage
        self.session.stage = "mock"
        return mockexam.question_block(self.items, self.session.mock, self.mock_time_limit())

    def mock_answer(self, payload):
        attempt = self.session.mock
        if not attempt:
            return {"type": "error", "message": "No practice exam is in progress."}
        item_id = payload.get("question_id", "")
        if item_id in attempt["order"]:
            attempt["answers"][item_id] = payload.get("selected_option", "")
        attempt["index"] += 1
        if attempt["index"] >= len(attempt["order"]):
            return self.mock_finish(payload)
        return mockexam.question_block(self.items, attempt, self.mock_time_limit())

    def mock_finish(self, payload):
        attempt = self.session.mock
        if not attempt:
            return {"type": "error", "message": "No practice exam is in progress."}
        result = mockexam.score_attempt(self.items, attempt)
        self.ledger.record_mock_attempt(result, payload.get("timestamp", ""))
        self.save_ledger()
        ready = mockexam.readiness(self.ledger, self.ledger.mock_attempts)
        # The numbers are decided before the model writes, so the page shows
        # them at once and the debrief streams in below.
        shown = {
            "type": "mock_result",
            "score": result["score"],
            "total": result["total"],
            "percent": result["percent"],
            "passed": result["passed"],
            "pass_mark": result["pass_mark"],
            "by_task": result["by_task"],
            "missed_units": sorted({m["unit"] for m in result["missed"]}),
            "readiness": ready,
        }

        debrief = self.generate("mock_gate", self.tutor.mock_gate_context(result, ready), preview=shown)
        body = debrief.get("body", "") if debrief.get("type") == "debrief" else ""
        if debrief.get("type") == "error":
            body = "The tutor could not write a debrief: %s" % debrief.get("message", "")

        self.session.mock = None
        self.session.stage = self.session.resume_stage
        self.session.resume_stage = None
        return dict(
            shown,
            debrief=body,
            citations=debrief.get("citations", []) if debrief.get("type") == "debrief" else [],
        )

    def advance(self):
        stage = self.session.stage
        if stage == "teach":
            return self.quiz()

        if stage == "quiz":
            # Try again after a question that failed to arrive, or Back to the
            # course after an exam taken with a question on screen: ask again.
            return self.quiz()

        if stage == "feedback" and self.session.next_action:
            action, gear = self.session.next_action
            self.session.next_action = None
            if action == "quiz":
                return self.quiz()
            if action == "remediate":
                return self.teach(stage="remediate", gear=gear)
            # "advance" and "park" both leave the unit; fall through to the next one

        if stage == "done":
            # Continue on the done screen retries whatever was set aside.
            for unit in self.ledger.unpark_all():
                self.session.returning.add(unit)
            self.save_ledger()

        return self.between_units()

    def between_units(self):
        """Pick what comes next: a pending review, a task boundary, or the next unit."""
        self.session.chosen = None
        if self.session.review_queue:
            return self.quiz(unit=self.session.review_queue.pop(0), review=True)

        finished = orchestrator.boundary_due(self.ledger)
        if finished:
            # Record the task being entered before unparking, so a parked unit
            # that returns from an earlier task does not re-trigger the boundary.
            self.ledger.last_task = orchestrator.next_task(self.ledger)
            self.session.review_queue = orchestrator.review_candidates(self.ledger, finished)
            for unit in self.ledger.unpark_all():
                self.session.returning.add(unit)
            self.save_ledger()
            if self.session.review_queue:
                return self.quiz(unit=self.session.review_queue.pop(0), review=True)

        if self.ledger.last_task is None:
            self.ledger.last_task = orchestrator.next_task(self.ledger)
            self.save_ledger()

        return self.teach()

    def handle_answer(self, payload):
        item_id = payload.get("question_id", "")
        pending = self.session.pending or {}
        unit = payload.get("unit") or pending.get("unit") or orchestrator.current_unit(self.ledger)
        selected = payload.get("selected_option", "")
        gear = self.ledger.units.get(unit, {}).get("current_gear", self.ledger.default_gear)

        # A vetted key wins. Failing that, the key the tutor declared when it wrote
        # the question is used, so scoring stays a comparison rather than a judgement.
        method, correct = items_module.score(self.items, item_id, selected)
        if method == "lookup":
            keyed = self.items[item_id]["answer"]
        else:
            keyed = pending.get("answer", "")
            correct = bool(keyed) and keyed.strip().upper() == selected.strip().upper()

        content = self.tutor.content(unit, gear)
        if content is None:
            return self.missing_content(unit, gear)

        # Record and decide before writing feedback, so the feedback can say what
        # happens next. Routing is a ledger decision; the model only explains.
        self.ledger.record_attempt(unit, item_id, gear, bool(correct), payload.get("timestamp", ""))
        review = self.session.stage == "review_quiz"
        if review:
            demote_to = orchestrator.decide_after_review(
                self.ledger, unit, self.gears_for(unit), bool(correct)
            )
            if demote_to:
                self.ledger.set_gear(unit, demote_to)
            outcome = "demote" if demote_to else "review_ok"
            self.session.next_action = None
        else:
            action, next_gear = orchestrator.decide_after_answer(
                self.ledger, unit, self.gears_for(unit), bool(correct)
            )
            if action == "park":
                self.ledger.park(unit)
            elif action == "advance" and self.ledger.units[unit].get("parked"):
                self.ledger.units[unit]["parked"] = False   # mastered from the tree while set aside
            outcome = action
            self.session.next_action = (action, next_gear)
        self.save_ledger()
        self.session.misconception = None if correct else "they chose %s on: %s" % (
            selected, pending.get("stem", "")
        )

        # What Continue will ask the model for is known now, so it is written
        # while the tutor explains this answer and the student reads it.
        self.prefetch(self.call_after_answer(review))
        block = self.generate(
            "score_diagnose",
            self.tutor.feedback_context(
                unit, gear, content, dict(pending, answer=keyed), selected, correct, outcome=outcome
            ),
            preview={"type": "feedback", "unit": unit, "gear": gear,
                     "correct": bool(correct), "correct_option": keyed},
        )
        if block.get("type") == "feedback":
            block["correct"] = bool(correct)
            block["correct_option"] = keyed
            block["question_id"] = item_id
            block["unit"] = unit

        self.session.stage = "review_feedback" if review else "feedback"
        self.session.pending = None
        self.session.reviewing = None
        return block

    def handle_question(self, payload):
        return self.ask(payload.get("text", ""), payload.get("context_unit"))

    def ask(self, question, context_unit=None, emit=None):
        """Answer a chat question and add the exchange to the chat history.

        The material is the knowledge-base chunks that match, plus the vetted
        content of the unit on screen; a backend with course search can read
        more of the course, and the web, itself. With `emit`, progress events and the
        answer text go to it while the model writes (see `generate`). Returns
        the cited_answer block, or an error.
        """
        self._local.emit = emit
        if self.session.mock is not None:
            return {"type": "error", "message": "The chat is paused during the practice exam. "
                                                "It comes back when you submit."}

        found = retrieval.search(self.chunks, question)
        earlier = [m["text"] for m in self.chat if m["role"] == "student"]
        if not found and earlier:
            # A follow-up such as "what about at night?" leans on the last question.
            found = retrieval.search(self.chunks, earlier[-1] + " " + question)
        unit = context_unit if context_unit in self.ledger.units else self.ledger.current_unit
        content = self.tutor.content(unit, 2) if unit else None

        can_search = self.client.supports_web_search or self.client.supports_course_search
        if not found and content is None and not can_search:
            # Nothing to answer from: say so at once rather than spend a model call.
            block = {
                "type": "cited_answer", "question": question, "in_corpus": False, "citations": [],
                "answer": "This is not covered in the course material, and this backend cannot "
                          "search the web. Check the FAA sources listed in the course, or switch "
                          "to a backend with web search.",
            }
        else:
            context = self.tutor.qa_context(
                question, found, self.client.supports_web_search,
                unit=unit, content=content, history=self.chat[-CHAT_MEMORY:],
                can_search_course=self.client.supports_course_search,
            )
            block = self.generate("qa", context, preview={"type": "cited_answer"})
            if block.get("type") != "cited_answer":
                return block
            block["question"] = question
            metrics = self.client.last_metrics
            self.chat_meta = {
                "model": metrics.get("model") or self.client.name,
                "context_tokens": metrics.get("context_tokens"),
                "context_window": metrics.get("context_window"),
            }

        self.chat.append({"role": "student", "text": question})
        self.chat.append({
            "role": "tutor", "text": block.get("answer", ""),
            "citations": block.get("citations", []), "in_corpus": block.get("in_corpus", True),
        })
        return block

    # ---- instructor -----------------------------------------------------
    # Instructor mode only (see Handler). The page names a unit and a gear,
    # never a path, so nothing but a unit's lesson files and its images can
    # be written.
    def author_target(self, unit, gear):
        """The unit and gear of a lesson file, or None when either is not real."""
        try:
            gear = int(gear)
        except (TypeError, ValueError):
            return None
        if unit not in self.tutor.objectives or gear not in orchestrator.LESSON_FILES:
            return None
        return unit, gear

    def author_file(self, unit, gear):
        """What the instructor workspace shows for one lesson file."""
        path = orchestrator.lesson_path(self.paths["curriculum"], unit, gear)
        guided = orchestrator.lesson_path(self.paths["curriculum"], unit, 2)
        return {
            "unit": unit,
            "gear": gear,
            "title": self.tutor.objectives.get(unit, ""),
            "text": editor_text(path),
            "guided": editor_text(guided),
            "files": {str(g): f for g, f in orchestrator.lesson_files(self.paths["curriculum"], unit).items()},
            "status": status.row(os.path.join(self.paths["curriculum"], "STATUS.md"), unit),
        }

    def author_ask(self, unit, gear, text, request, history=(), emit=None):
        """The authoring assistant's revision of the file in the editor. Returns
        the final stream event: the note, the revised text, and the diff."""
        self._local.emit = emit
        found = retrieval.search(self.chunks, request + " " + self.tutor.objectives.get(unit, ""))
        context = self.tutor.author_context(
            unit, gear, text, request, chunks=found, history=list(history)[-CHAT_MEMORY:],
            can_search=self.client.supports_course_search,
        )
        block = self.generate("author", context, preview={"type": "revision", "unit": unit, "gear": gear})
        if block.get("type") != "revision" or not isinstance(block.get("text"), str):
            return {"error": block.get("message", "The assistant returned no revision.")}
        revised = block["text"].rstrip("\n") + "\n"
        diff = list(difflib.unified_diff(text.splitlines(), revised.splitlines(), "editor", "proposal", lineterm="", n=2))
        return {"done": True, "note": block.get("note", ""), "text": revised, "diff": diff}

    def author_save(self, unit, gear, text, note="", vetted=False):
        """Save a lesson file from the workspace: move new drawings into image
        files, raise the version, drop the draft mark, and record the save in
        STATUS.md. Returns the outcome, with warnings for the instructor."""
        images = os.path.join(self.paths["curriculum"], "images")
        try:
            text, saved_images = store_drawings(text, unit, images)
        except ValueError as error:
            return {"error": str(error)}
        path = orchestrator.lesson_path(self.paths["curriculum"], unit, gear)
        old = None
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as handle:
                old = orchestrator.parse_content(handle.read())
        version = (old["version"] or 1) + 1 if old else 1
        replace_file(path, with_version(text, version))

        cell = "v%d %s" % (version, "vetted" if vetted else "edited")
        status.record(os.path.join(self.paths["curriculum"], "STATUS.md"), unit, gear, cell,
                      status=None if vetted else "draft",
                      note="%s lesson v%d, %s: %s" % (orchestrator.GEAR_NAMES[gear], version,
                                                     "vetted" if vetted else "not yet vetted",
                                                     note.strip() or "edited in the instructor interface"))
        parsed = orchestrator.parse_content(with_version(text, version))
        warnings = []
        if not any(s["url"] for s in parsed["sources"]):
            warnings.append("The file has no source line with a link. Add one: source: <name> | <link>.")
        for name in re.findall(r"\]\((images/[^)\s]+)\)", parsed["body"]):
            if not os.path.isfile(os.path.join(self.paths["curriculum"], name)):
                warnings.append("The image %s does not exist." % name)
        if gear != 2 and orchestrator.lesson_files(self.paths["curriculum"], unit)[2] is None:
            warnings.append("This unit has no Guided lesson, so the tutor cannot teach it yet.")
        return {"saved": True, "version": version, "images": saved_images, "warnings": warnings,
                "file": self.author_file(unit, gear)}

    # ---- persistence ----------------------------------------------------
    def log_response(self, payload):
        path = self.paths["responses"]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")

    def save_ledger(self):
        self.ledger.save(self.paths["ledger"])

    def state(self):
        state = self.ledger.state(self.paths["curriculum"], self.tutor.objectives)
        state["readiness"] = mockexam.readiness(self.ledger, self.ledger.mock_attempts)
        state["mock_available"] = bool(mockexam.mock_items(self.items))
        state["mock_in_progress"] = self.session.mock is not None
        state["instructor"] = getattr(self, "instructor", False)
        return state


def _parse_json_block(raw):
    """Extract the tutor's block from a model reply.

    The contract is one bare JSON object, and a clean reply parses directly.
    Replies that ran a web search can carry prose before the object, and some
    models wrap it in code fences, so the fallback scans for the last JSON
    object in the text. Anything else is treated as no block at all.
    """
    text = (raw or "").strip()
    text = re.sub(r"^```[a-z]*\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        block = json.loads(text)
        return block if isinstance(block, dict) else None
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    found = None
    for match in re.finditer(r"\{", text):
        try:
            candidate, _ = decoder.raw_decode(text, match.start())
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict) and "type" in candidate:
            found = candidate
    return found


class FieldStream:
    """Reads named string fields out of a JSON block while it streams.

    The model writes one JSON object, and the student should see its text as
    it is written rather than after the closing brace. This finds each named
    string field, in whatever order the model writes them, and decodes it
    piece by piece, holding back an escape sequence until it is complete.
    Everything else in the block is left to the final parse.
    """

    _ESCAPES = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}

    def __init__(self, fields):
        self.raw = ""
        self.unread = list(fields)
        self.field = None     # the field being read, if any
        self.position = 0     # index in raw of the next character to look at
        self._start = re.compile(r'"(%s)"\s*:\s*"' % "|".join(re.escape(f) for f in fields)) if fields else None

    def feed(self, chunk):
        """Add streamed text. Returns (field, text, closed) for each piece it
        completes; `closed` is true when that field's string has ended."""
        self.raw += chunk
        pieces = []
        while self._start:
            if self.field is None:
                match = self._start.search(self.raw, self.position)
                while match and match.group(1) not in self.unread:
                    match = self._start.search(self.raw, match.end())
                if not match:
                    break
                self.field = match.group(1)
                self.unread.remove(self.field)
                self.position = match.end()
            text, closed = self._read()
            if text or closed:
                pieces.append((self.field, text, closed))
            if not closed:
                break
            self.field = None
        return pieces

    def _read(self):
        raw, i, out = self.raw, self.position, []
        closed = False
        while i < len(raw):
            char = raw[i]
            if char == '"':
                closed = True
                i += 1
                break
            if char != "\\":
                out.append(char)
                i += 1
                continue
            if i + 1 >= len(raw):
                break
            code = raw[i + 1]
            if code == "u":
                if i + 6 > len(raw):
                    break
                out.append(chr(int(raw[i + 2:i + 6], 16)))
                i += 6
            else:
                out.append(self._ESCAPES.get(code, code))
                i += 2
        self.position = i
        return "".join(out), closed


class Prefetch:
    """One model call started before it is needed, on a background thread.

    It keeps the text written so far, so a request that arrives while it is
    still running can show that text at once and then follow the rest. It
    never raises: a failure is kept in `error` for the request to see.
    """

    def __init__(self, course, stage, context):
        self.stage, self.context = stage, context
        self.turn = course.turn
        self.started = time.perf_counter()
        self.chunks = []
        self.raw = self.error = self.ms = None
        self.metrics = {}
        self.finished = False
        self._changed = threading.Condition()
        threading.Thread(target=self._run, args=(course,), daemon=True).start()

    def _run(self, course):
        raw = error = None
        try:
            raw = course.client.complete(course.tutor.system(self.stage), self.context,
                                         stage=_MOCK_STAGE.get(self.stage, "lesson"), on_text=self._add)
        except Exception as caught:  # kept for the request, which then makes the call itself
            error = caught
        with self._changed:
            self.raw, self.error = raw, error
            self.metrics = dict(course.client.last_metrics)
            self.ms = round((time.perf_counter() - self.started) * 1000)
            self.finished = True
            self._changed.notify_all()

    def _add(self, chunk):
        with self._changed:
            self.chunks.append(chunk)
            self._changed.notify_all()

    def follow(self, on_text=None):
        """Pass on the text written so far, then the rest as it comes, and
        return the full reply once the call has finished."""
        sent = 0
        while True:
            with self._changed:
                while sent == len(self.chunks) and not self.finished:
                    self._changed.wait()
                new, finished = self.chunks[sent:], self.finished
            sent += len(new)
            if on_text:
                for chunk in new:
                    on_text(chunk)
            if finished and sent == len(self.chunks):
                return self.raw


# ---- metrics --------------------------------------------------------------
def log_metrics(path, record):
    """Print one line to the terminal and append the full record to the metrics file."""
    record = dict(record, ts=time.strftime("%Y-%m-%dT%H:%M:%S"))
    print(_metrics_line(record), flush=True)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def _ms(value):
    if value >= 1000:
        return "%.1f s" % (value / 1000.0)
    return "%.1f ms" % value if value < 10 else "%d ms" % round(value)


def _metrics_line(r):
    """The terminal form of a metrics record. The file keeps every field."""
    if r.get("source") == "browser":
        hidden = ", tab hidden" if r.get("hidden") else ""
        if r.get("kind") == "page_load":
            files = ", ".join("%s %s" % (k, _ms(v)) for k, v in sorted((r.get("files") or {}).items()))
            return "[browser] page load: first byte %s, DOM ready %s, loaded %s (%s)%s" % (
                _ms(r.get("first_byte_ms", 0)), _ms(r.get("dom_ready_ms", 0)), _ms(r.get("load_ms", 0)), files, hidden)
        if r.get("kind") == "request":
            parts = ["round trip " + _ms(r.get("round_trip_ms", 0))]
            if r.get("first_text_ms") is not None:
                parts.append("first text on screen " + _ms(r["first_text_ms"]))
            if r.get("server_ms") is not None:
                parts.append("server " + _ms(r["server_ms"]))
            if r.get("draw_ms") is not None:
                parts.append("draw " + _ms(r["draw_ms"]))
            return "[browser] %-14s %s%s" % (r.get("what"), ", ".join(parts), hidden)
        return "[browser] %s" % json.dumps(r)
    if r.get("kind") == "draft":
        return "[server]  draft    %s gear %s saved as a tutor draft" % (r.get("unit"), r.get("gear"))
    if r.get("kind") == "prefetch":
        state = ("written in " if r.get("finished") else "still writing after ") + _ms(r.get("ms") or 0)
        if r.get("output_tokens"):
            state += ", out %d tok" % r["output_tokens"]
        return "[server]  prefetch %-10s %s (%s)" % (r.get("stage"), r.get("outcome"), state)
    label = r.get("type") or r.get("path")
    line = "[server]  %-4s %-14s %8s  %5.1f kB" % (r["method"], label, _ms(r["ms"]), r["bytes"] / 1024.0)
    if r.get("first_text_ms") is not None:
        line += "  first text %s" % _ms(r["first_text_ms"])
    for call in r.get("calls") or []:
        parts = []
        if call.get("prefetched"):
            # "ready": written before the student asked; "joined": still writing then.
            parts.append("prefetched, %s, written in %s" % (call["prefetched"], _ms(call.get("written_ms") or 0)))
        if call.get("api_ms"):
            parts.append("api " + _ms(call["api_ms"]))
        if call.get("context_tokens"):
            window = call.get("context_window")
            parts.append("context %.1fk%s" % (call["context_tokens"] / 1000.0,
                                              " of %dk" % (window // 1000) if window else ""))
        if call.get("output_tokens"):
            parts.append("out %d tok" % call["output_tokens"])
        if call.get("model"):
            parts.append(call["model"])
        if call.get("error"):
            parts.append("ERROR" if call["error"] is True else "ERROR " + call["error"])
        line += "\n          model %-14s %8s  %s" % (call["stage"], _ms(call["ms"]), ", ".join(parts))
    return line


class Handler(BaseHTTPRequestHandler):
    server_version = "Part107Course/0.2"

    @property
    def course(self):
        return self.server.course

    def instructor(self):
        """Whether the instructor endpoints exist: only when the course was started for an instructor."""
        return getattr(self.course, "instructor", False)

    def do_GET(self):
        self.started = time.perf_counter()
        if self.path in ("/", "/index.html"):
            return self.send_file(os.path.join(ROOT, "ui", "index.html"), "text/html")
        if self.path == "/api/state":
            return self.send_json(self.course.state())
        if self.path == "/api/chat":
            return self.send_json({"messages": self.course.chat, "meta": self.course.chat_meta})
        if self.path.startswith("/api/author?") and self.instructor():
            query = urllib.parse.parse_qs(self.path.split("?", 1)[1])
            target = self.course.author_target((query.get("unit") or [""])[0], (query.get("gear") or [""])[0])
            if target is None:
                return self.send_json({"error": "Unknown unit or gear."}, status=400)
            return self.send_json(self.course.author_file(*target))
        if self.path.startswith("/images/"):
            # A unit file writes images/x.png, which the page asks for as /images/x.png.
            name = os.path.basename(self.path)
            candidate = os.path.join(self.course.paths["curriculum"], "images", name)
            content_type = IMAGE_TYPES.get(os.path.splitext(name)[1].lower())
            if content_type and os.path.isfile(candidate):
                return self.send_file(candidate, content_type)
            return self.send_error(404, "Not found")
        name = os.path.basename(self.path)
        candidate = os.path.join(ROOT, "ui", name)
        if name and os.path.isfile(candidate):
            content_type = "text/css" if name.endswith(".css") else "text/javascript"
            return self.send_file(candidate, content_type)
        self.send_error(404, "Not found")

    def do_POST(self):
        self.started = time.perf_counter()
        if self.path == "/api/metrics":
            return self.receive_metrics()
        authoring = self.path in ("/api/author/ask", "/api/author/save")
        if not (self.path in ("/api/respond", "/api/ask") or (authoring and self.instructor())):
            return self.send_error(404, "Not found")
        length = int(self.headers.get("content-length") or 0)
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = None
        if not isinstance(payload, dict):
            return self.send_json({"type": "error", "message": "Malformed request."}, status=400)

        if authoring:
            target = self.course.author_target(payload.get("unit"), payload.get("gear"))
            if target is None:
                return self.send_json({"error": "Unknown unit or gear."}, status=400)
            text = payload.get("text") if isinstance(payload.get("text"), str) else ""
            if self.path == "/api/author/save":
                return self.send_json(self.course.author_save(
                    *target, text=text, note=str(payload.get("note") or ""), vetted=payload.get("vetted") is True))
            history = [m for m in payload.get("history") or [] if isinstance(m, dict) and "role" in m and "text" in m]
            return self.stream_events("author", lambda emit: self.course.author_ask(
                *target, text=text, request=str(payload.get("request") or ""), history=history, emit=emit))

        if self.path == "/api/ask":
            def ask(emit):
                self.course.log_response(payload)
                block = self.course.ask(payload.get("text", ""), payload.get("context_unit"), emit=emit)
                if block.get("type") == "cited_answer":
                    return {"done": True, "message": self.course.chat[-1], "meta": self.course.chat_meta}
                return {"error": block.get("message", "The tutor returned a response that was not an answer.")}
            return self.stream_events("ask", ask)

        # The page asks for a stream; anything else gets the block as plain JSON.
        if "application/x-ndjson" in (self.headers.get("accept") or ""):
            return self.stream_events(
                payload.get("type"), lambda emit: {"done": True, "block": self.course.handle(payload, emit=emit)}
            )
        self.request_type = payload.get("type")
        self.course.calls = []
        result = self.course.handle(payload)
        self.calls = self.course.calls
        return self.send_json(result)

    def stream_events(self, label, run):
        """Answer with one JSON object per line while the model writes: "start",
        "status" and "delta" events from `run`, then the final event it returns.
        There is no content length; the response ends when the connection closes."""
        self.send_response(200)
        self.send_header("content-type", "application/x-ndjson")
        self.send_header("cache-control", "no-store")
        self.end_headers()

        sent = {"bytes": 0, "first": None, "gone": False}

        def emit(event):
            if "delta" in event and sent["first"] is None:
                sent["first"] = (time.perf_counter() - self.started) * 1000
            if sent["gone"]:
                return
            line = (json.dumps(event) + "\n").encode("utf-8")
            try:
                self.wfile.write(line)
                self.wfile.flush()
            except OSError:  # the page went away; finish the work for the ledger and history anyway
                sent["gone"] = True
            sent["bytes"] += len(line)

        self.course.calls = []
        emit(run(emit))
        log_metrics(self.course.paths["metrics"], {
            "source": "server", "method": "POST", "path": self.path, "type": label, "status": 200,
            "bytes": sent["bytes"], "ms": round((time.perf_counter() - self.started) * 1000, 1),
            "first_text_ms": None if sent["first"] is None else round(sent["first"], 1),
            "calls": self.course.calls,
        })

    def receive_metrics(self):
        """A timing record from the browser: page load, or one request's round trip."""
        length = int(self.headers.get("content-length") or 0)
        try:
            record = json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            record = None
        if isinstance(record, dict):
            log_metrics(self.course.paths["metrics"], dict(record, source="browser"))
        self.send_response(204)
        self.end_headers()

    def send_json(self, data, status=200):
        self.send_body(status, json.dumps(data).encode("utf-8"), "application/json")

    def send_file(self, path, content_type):
        with open(path, "rb") as handle:
            body = handle.read()
        self.send_body(200, body, content_type)

    def send_body(self, status, body, content_type):
        """Send a response, with its timing in a Server-Timing header, and log it."""
        elapsed = (time.perf_counter() - self.started) * 1000
        calls = getattr(self, "calls", [])
        timing = ["total;dur=%.1f" % elapsed] + ["%s;dur=%d" % (c["stage"], c["ms"]) for c in calls]
        log_metrics(self.course.paths["metrics"], {
            "source": "server",
            "method": self.command,
            "path": self.path,
            "type": getattr(self, "request_type", None),
            "status": status,
            "bytes": len(body),
            "ms": round(elapsed, 1),
            "calls": calls,
        })
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(body)))
        self.send_header("server-timing", ", ".join(timing))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # the metrics lines replace the access log


class CourseServer(ThreadingHTTPServer):
    def __init__(self, address, course):
        super().__init__(address, Handler)
        self.course = course


def main():
    parser = argparse.ArgumentParser(description="The Part 107 course server.")
    parser.add_argument("--instructor", action="store_true",
                        help="add the instructor workspace, which edits the course material")
    course = Course(instructor=parser.parse_args().instructor)
    port = int(course.config.get("port", 8107))
    print("Part 107 course running at http://localhost:%d" % port)
    print("Provider: %s. Press Ctrl+C to stop." % course.client.name)
    if course.instructor:
        print("Instructor mode: on. The Instructor button edits the course material.")
    server = CourseServer(("127.0.0.1", port), course)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
