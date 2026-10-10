"""Phase 2 tests: server plumbing, scoring, retrieval, ledger, and the client.

Run from the course folder:  python3 -m unittest discover -s tests -v
"""

import contextlib
import io
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(ROOT, "tests", "fixtures")
sys.path.insert(0, ROOT)

import items as items_module          # noqa: E402
import ledger as ledger_module        # noqa: E402
import orchestrator                   # noqa: E402
import retrieval                      # noqa: E402
import server as server_module        # noqa: E402
from llm_client import LLMClient, LLMError  # noqa: E402

OBJECTIVES = os.path.join(ROOT, "curriculum", "regulations", "objectives.md")


def mock_config(tmp, provider="mock"):
    return {
        "provider": provider,
        "providers": {
            "anthropic": {
                "endpoint": "https://api.anthropic.com/v1/messages",
                "model": "claude-sonnet-4-6",
                "api_key_env": "TEST_KEY_THAT_IS_NOT_SET",
                "supports_web_search": True,
            },
            "claude_code": {
                "command": "claude",
                "model": "",
                "timeout_seconds": 30,
                "supports_web_search": False,
            },
            "ollama": {"endpoint": "http://localhost:11434/api/chat", "model": "gemma3", "supports_web_search": False},
            "mock": {"supports_web_search": False},
        },
        "paths": {
            "objectives": os.path.join(FIXTURES, "objectives-stub.md"),
            "curriculum": os.path.join(FIXTURES, "curriculum"),
            "knowledge_base": os.path.join(FIXTURES, "kb"),
            "items": os.path.join(FIXTURES, "items.md"),
            "reference": os.path.join(FIXTURES, "facts-stub.md"),
            "prompts": os.path.join(ROOT, "prompts"),
            "ledger": os.path.join(tmp, "ledger.md"),
            "responses": os.path.join(tmp, "responses.jsonl"),
            "metrics": os.path.join(tmp, "metrics.jsonl"),
        },
        "area": "Regulations",
        "port": 8107,
    }


class TestLLMClient(unittest.TestCase):
    def test_config_selects_provider_and_capability(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(LLMClient(mock_config(tmp, "ollama")).supports_web_search)
            self.assertTrue(LLMClient(mock_config(tmp, "anthropic")).supports_web_search)

    def test_missing_key_raises_a_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = LLMClient(mock_config(tmp, "anthropic"))
            with self.assertRaises(LLMError) as caught:
                client.complete("system", "user")
            self.assertIn("TEST_KEY_THAT_IS_NOT_SET", str(caught.exception))

    def test_unknown_provider_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = mock_config(tmp)
            config["provider"] = "nope"
            with self.assertRaises(LLMError):
                LLMClient(config)

    def test_mock_provider_returns_a_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            block = json.loads(LLMClient(mock_config(tmp)).complete("s", "u", stage="question"))
            self.assertEqual(block["type"], "question")

    def test_mock_provider_streams_the_same_text_in_pieces(self):
        with tempfile.TemporaryDirectory() as tmp:
            pieces = []
            out = LLMClient(mock_config(tmp)).complete("s", "u", stage="qa", on_text=pieces.append)
            self.assertGreater(len(pieces), 1)
            self.assertEqual("".join(pieces), out)

    def test_post_stream_reads_server_sent_events_and_json_lines(self):
        class Stream(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers["content-length"]))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'event: a\ndata: {"n": 1}\n\n: comment\n{"n": 2}\n')

            def log_message(self, *args):
                pass

        with tempfile.TemporaryDirectory() as tmp:
            httpd = HTTPServer(("127.0.0.1", 0), Stream)
            threading.Thread(target=httpd.handle_request, daemon=True).start()
            client = LLMClient(mock_config(tmp, "ollama"))
            events = list(client._post_stream("http://127.0.0.1:%d/" % httpd.server_address[1], {}, {}))
            httpd.server_close()
            self.assertEqual(events, [{"n": 1}, {"n": 2}])

    def test_ollama_streams_and_reads_the_counts_from_the_last_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = LLMClient(mock_config(tmp, "ollama"))

            def fake_stream(url, body, headers):
                self.assertTrue(body["stream"])
                yield {"message": {"content": "Hel"}}
                yield {"message": {"content": "lo"}, "done": True, "model": "gemma3",
                       "prompt_eval_count": 12, "eval_count": 2}

            client._post_stream = fake_stream
            pieces = []
            self.assertEqual(client.complete("s", "u", on_text=pieces.append), "Hello")
            self.assertEqual(pieces, ["Hel", "lo"])
            self.assertEqual((client.last_metrics["context_tokens"], client.last_metrics["output_tokens"]), (12, 2))


class TestAnthropicAdapter(unittest.TestCase):
    """Drives the adapter against a captured request, no network."""

    def capture(self, tmp, flag):
        config = mock_config(tmp, "anthropic")
        config["providers"]["anthropic"]["supports_web_search"] = flag
        client = LLMClient(config)
        sent = {}

        def fake_post(url, body, headers):
            sent.update(body)
            return {"content": [
                {"type": "text", "text": "Searching first."},
                {"type": "text", "text": '{"type": "cited_answer", "answer": "x", "in_corpus": false, "citations": []}'},
            ]}

        client._post_json = fake_post
        os.environ["TEST_KEY_THAT_IS_NOT_SET"] = "present"
        try:
            out = client.complete("s", "u")
        finally:
            del os.environ["TEST_KEY_THAT_IS_NOT_SET"]
        return sent, out

    def test_streaming_passes_text_on_and_reads_usage_from_the_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = LLMClient(mock_config(tmp, "anthropic"))
            sent = {}

            def fake_stream(url, body, headers):
                sent.update(body)
                yield {"type": "message_start", "message": {"model": "claude-x", "usage": {"input_tokens": 9}}}
                yield {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hel"}}
                yield {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "lo"}}
                yield {"type": "message_delta", "usage": {"output_tokens": 2}}

            client._post_stream = fake_stream
            pieces = []
            os.environ["TEST_KEY_THAT_IS_NOT_SET"] = "present"
            try:
                out = client.complete("s", "u", on_text=pieces.append)
            finally:
                del os.environ["TEST_KEY_THAT_IS_NOT_SET"]
            self.assertTrue(sent["stream"])
            self.assertEqual((out, pieces), ("Hello", ["Hel", "lo"]))
            metrics = client.last_metrics
            self.assertEqual((metrics["model"], metrics["context_tokens"], metrics["output_tokens"]), ("claude-x", 9, 2))

    def test_web_search_tool_is_sent_only_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            sent, _ = self.capture(tmp, False)
            self.assertNotIn("tools", sent)
            sent, _ = self.capture(tmp, True)
            self.assertEqual(sent["tools"][0]["name"], "web_search")
            self.assertTrue(sent["tools"][0]["type"].startswith("web_search_"))

    def test_multi_block_reply_still_yields_the_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, out = self.capture(tmp, True)
            self.assertEqual(server_module._parse_json_block(out)["type"], "cited_answer")


class TestClaudeCodeAdapter(unittest.TestCase):
    """Exercises the adapter against a stand-in `claude` binary, so the tests
    run anywhere without Claude Code installed or a plan signed in."""

    def fake_claude(self, tmp, body):
        path = os.path.join(tmp, "claude")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("#!/usr/bin/env python3\n" + body)
        os.chmod(path, 0o755)
        return path

    def client_with(self, tmp, command):
        config = mock_config(tmp, "claude_code")
        config["providers"]["claude_code"]["command"] = command
        return LLMClient(config)

    def test_parses_the_result_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = self.fake_claude(tmp, (
                "import sys, json\n"
                "sys.stdin.read()\n"
                "print(json.dumps({'type': 'result', 'subtype': 'success', 'result': '{\"type\": \"lesson\"}'}))\n"
            ))
            out = self.client_with(tmp, fake).complete("system", "user", stage="lesson")
            self.assertEqual(json.loads(out)["type"], "lesson")

    def test_passes_the_prompt_on_stdin_and_locks_down_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = self.fake_claude(tmp, (
                "import sys, json\n"
                "piped = sys.stdin.read()\n"
                "print(json.dumps({'result': json.dumps({'argv': sys.argv[1:], 'stdin': piped})}))\n"
            ))
            out = json.loads(self.client_with(tmp, fake).complete("SYSTEM", "USER"))
            self.assertEqual(out["stdin"], "USER")
            self.assertIn("--system-prompt", out["argv"])
            self.assertIn("SYSTEM", out["argv"])
            argv = out["argv"]
            self.assertEqual(argv[argv.index("--tools") + 1], "")
            self.assertEqual(argv[argv.index("--setting-sources") + 1], "")
            self.assertIn("-p", out["argv"])

    def test_reports_the_main_model_tokens_and_timings(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = self.fake_claude(tmp, (
                "import sys, json\n"
                "sys.stdin.read()\n"
                "print(json.dumps({'result': '{}', 'duration_ms': 900, 'duration_api_ms': 800,\n"
                "    'usage': {'input_tokens': 2, 'cache_read_input_tokens': 2800, 'output_tokens': 500},\n"
                "    'modelUsage': {'claude-haiku-x': {'outputTokens': 10},\n"
                "                   'claude-opus-5[1m]': {'outputTokens': 500, 'contextWindow': 1000000,\n"
                "                                         'canonicalModel': 'claude-opus-5'}}}))\n"
            ))
            client = self.client_with(tmp, fake)
            client.complete("system", "user")
            metrics = client.last_metrics
            self.assertEqual(metrics["model"], "claude-opus-5")
            self.assertEqual(metrics["context_tokens"], 2802)
            self.assertEqual(metrics["output_tokens"], 500)
            self.assertEqual(metrics["context_window"], 1000000)
            self.assertEqual(metrics["api_ms"], 800)

    def test_streams_text_pieces_and_still_returns_the_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = self.fake_claude(tmp, (
                "import sys, json\n"
                "sys.stdin.read()\n"
                "assert 'stream-json' in sys.argv and '--include-partial-messages' in sys.argv\n"
                "def out(event):\n"
                "    print(json.dumps(event), flush=True)\n"
                "out({'type': 'system'})\n"
                "for piece in ['{\"answer\": ', '\"Hel', 'lo\"}']:\n"
                "    out({'type': 'stream_event', 'event': {'type': 'content_block_delta',\n"
                "         'delta': {'type': 'text_delta', 'text': piece}}})\n"
                "out({'type': 'result', 'result': '{\"answer\": \"Hello\"}', 'duration_api_ms': 5,\n"
                "     'usage': {'input_tokens': 7, 'output_tokens': 3}, 'modelUsage': {'m': {'outputTokens': 3}}})\n"
            ))
            client = self.client_with(tmp, fake)
            pieces = []
            out = client.complete("s", "u", on_text=pieces.append)
            self.assertEqual(pieces, ['{"answer": ', '"Hel', 'lo"}'])
            self.assertEqual(json.loads(out)["answer"], "Hello")
            self.assertEqual((client.last_metrics["model"], client.last_metrics["output_tokens"]), ("m", 3))

    def test_missing_binary_fails_clearly(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = self.client_with(tmp, os.path.join(tmp, "not-installed"))
            with self.assertRaises(LLMError) as caught:
                client.complete("s", "u")
            self.assertIn("Install Claude Code", str(caught.exception))

    def test_nonzero_exit_fails_clearly(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = self.fake_claude(tmp, (
                "import sys\n"
                "sys.stdin.read()\n"
                "sys.stderr.write('not signed in')\n"
                "sys.exit(1)\n"
            ))
            with self.assertRaises(LLMError) as caught:
                self.client_with(tmp, fake).complete("s", "u")
            self.assertIn("not signed in", str(caught.exception))

    def test_capability_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(LLMClient(mock_config(tmp, "claude_code")).supports_web_search)


class TestScoring(unittest.TestCase):
    def setUp(self):
        self.items = items_module.load_items(os.path.join(FIXTURES, "items.md"))

    def test_loads_keyed_items(self):
        self.assertEqual(self.items["fx-1"]["answer"], "B")
        self.assertEqual(self.items["fx-1"]["unit"], "UA.I.B.K16")

    def test_lookup_scoring(self):
        self.assertEqual(items_module.score(self.items, "fx-1", "B"), ("lookup", True))
        self.assertEqual(items_module.score(self.items, "fx-1", "A"), ("lookup", False))
        self.assertEqual(items_module.score(self.items, "fx-1", "b"), ("lookup", True))

    def test_unknown_item_falls_back_to_model_scoring(self):
        self.assertEqual(items_module.score(self.items, "not-vetted", "B"), ("model", None))

    def test_missing_file_is_empty_not_an_error(self):
        self.assertEqual(items_module.load_items(os.path.join(FIXTURES, "nope.md")), {})


class TestRetrieval(unittest.TestCase):
    def setUp(self):
        self.chunks = retrieval.load_chunks(os.path.join(FIXTURES, "kb"))

    def test_chunks_carry_citation_metadata(self):
        self.assertEqual(len(self.chunks), 2)
        self.assertTrue(all(c["source"] and c["url"] for c in self.chunks))

    def test_returns_the_expected_chunk(self):
        top = retrieval.search(self.chunks, "anti-collision lighting at night")[0]
        self.assertEqual(top["source"], "Fixture 107.29")
        top = retrieval.search(self.chunks, "authorization for controlled airspace")[0]
        self.assertEqual(top["source"], "Fixture 107.41")

    def test_no_match_returns_nothing(self):
        self.assertEqual(retrieval.search(self.chunks, "photosynthesis chlorophyll"), [])

    def test_missing_directory_is_empty_not_an_error(self):
        self.assertEqual(retrieval.load_chunks(os.path.join(FIXTURES, "nope")), [])


class TestLedger(unittest.TestCase):
    def test_seeds_all_tracked_units_from_objectives(self):
        led = ledger_module.Ledger.bootstrap(OBJECTIVES)
        self.assertEqual(len(led.order), 77)
        self.assertIn("UA.I.B.K21c", led.order)

    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "ledger.md")
            led = ledger_module.Ledger.bootstrap(OBJECTIVES)
            led.set_default_gear(2)
            led.record_attempt("UA.I.B.K16", "fx-1", 2, True, "2026-07-16T18:00:00Z")
            led.save(path)

            reloaded = ledger_module.Ledger.load(path)
            self.assertEqual(reloaded.default_gear, 2)
            self.assertEqual(len(reloaded.order), 77)
            self.assertEqual(len(reloaded.attempts), 1)
            self.assertEqual(reloaded.units["UA.I.B.K16"]["gears_taken"], [2])
            self.assertEqual(reloaded.current_unit, "UA.I.B.K16")

    def test_mastery_derivation(self):
        led = ledger_module.Ledger.bootstrap(OBJECTIVES)
        unit = "UA.I.B.K16"
        self.assertEqual(led.mastery(unit), "unseen")
        led.record_attempt(unit, "i1", 1, True, "t1")
        self.assertEqual(led.mastery(unit), "learning")
        led.record_attempt(unit, "i2", 1, True, "t2")
        self.assertEqual(led.mastery(unit), "mastered")
        led.record_attempt(unit, "i3", 1, False, "t3")
        self.assertEqual(led.mastery(unit), "learning")

    def test_repeating_one_item_does_not_confer_mastery(self):
        led = ledger_module.Ledger.bootstrap(OBJECTIVES)
        led.record_attempt("UA.I.B.K16", "i1", 1, True, "t1")
        led.record_attempt("UA.I.B.K16", "i1", 1, True, "t2")
        self.assertEqual(led.mastery("UA.I.B.K16"), "learning")

    def test_state_shape(self):
        led = ledger_module.Ledger.bootstrap(OBJECTIVES)
        led.record_attempt("UA.I.B.K16", "i1", 1, True, "t1")
        state = led.state(os.path.join(ROOT, "curriculum", "regulations"))
        self.assertEqual(state["summary"]["total"], 77)
        unit = next(u for u in state["units"] if u["id"] == "UA.I.B.K16")
        self.assertEqual(unit["task"], "B")
        self.assertTrue(unit["current"])
        # K16 is a gear-3 exemplar in the real curriculum, so it offers all three.
        self.assertEqual(unit["available_gears"], [1, 2, 3])
        self.assertEqual(unit["gears_taken"], [1])


class TestFieldStream(unittest.TestCase):
    """The page shows a block's text while the model is still writing it."""

    # Prose before the block, an escaped "body" key inside another field, and
    # escapes of every kind inside the streamed fields.
    BLOCK = ('Searching first. {"type": "lesson", "note": "is \\"body\\": x a key?", '
             '"title": "Class \\"D\\"", '
             '"body": "Line one.\\n\\nSay \\"hi\\" in \\u00e9t\\u00e9 at C:\\\\path\\/x", '
             '"citations": [{"source": "s", "url": "u"}]}')

    def stream(self, text, fields, size):
        stream = server_module.FieldStream(fields)
        got, closed = {}, []
        for i in range(0, len(text), size):
            for field, piece, done in stream.feed(text[i:i + size]):
                got[field] = got.get(field, "") + piece
                if done:
                    closed.append(field)
        return got, closed

    def test_pieces_of_any_size_give_the_exact_fields(self):
        block = json.loads(self.BLOCK[self.BLOCK.index("{"):])
        for size in (1, 2, 3, 5, 7, 16, len(self.BLOCK)):
            got, closed = self.stream(self.BLOCK, ("title", "body"), size)
            self.assertEqual(got, {"title": block["title"], "body": block["body"]}, "piece size %d" % size)
            self.assertEqual(closed, ["title", "body"])

    def test_fields_are_found_in_whatever_order_the_model_writes_them(self):
        text = '{"body": "B", "title": "T"}'
        got, closed = self.stream(text, ("title", "body"), 1)
        self.assertEqual((got, closed), ({"title": "T", "body": "B"}, ["body", "title"]))


def post(url, payload, accept=None):
    headers = {"content-type": "application/json"}
    if accept:
        headers["accept"] = accept
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    return urllib.request.urlopen(request)


class TestCourse(unittest.TestCase):
    @contextlib.contextmanager
    def serving(self, course):
        """The real handler on a free port, with its terminal lines captured."""
        httpd = server_module.CourseServer(("127.0.0.1", 0), course)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        printed = io.StringIO()
        try:
            with contextlib.redirect_stdout(printed):
                yield "http://127.0.0.1:%d" % httpd.server_address[1], printed
        finally:
            httpd.shutdown()
            httpd.server_close()

    def metrics(self, course):
        with open(course.paths["metrics"], encoding="utf-8") as handle:
            return [json.loads(line) for line in handle]

    def make(self, tmp, provider="mock"):
        course = server_module.Course.__new__(server_module.Course)
        course.config = mock_config(tmp, provider)
        course.paths = course.config["paths"]
        course.client = LLMClient(course.config)
        course.items = items_module.load_items(course.paths["items"])
        course.chunks = retrieval.load_chunks(course.paths["knowledge_base"])
        course.tutor = orchestrator.Orchestrator(course.paths)
        course.ledger = ledger_module.Ledger.open_or_bootstrap(
            course.paths["ledger"], course.paths["objectives"]
        )
        course.session = server_module.Session()
        course.calls = []
        course.chat, course.chat_meta = [], {}
        return course

    def test_intake_sets_gear_and_returns_a_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = self.make(tmp)
            block = course.handle({"type": "intake", "default_gear": 2, "timestamp": "t"})
            self.assertEqual(block["type"], "lesson")
            self.assertEqual(ledger_module.Ledger.load(course.paths["ledger"]).default_gear, 2)

    def test_answer_is_scored_by_lookup_and_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = self.make(tmp)
            block = course.handle({
                "type": "answer", "question_id": "fx-1", "unit": "UA.I.B.K16",
                "selected_option": "A", "timestamp": "t",
            })
            # The mock always claims correct; the vetted key must override it.
            self.assertEqual(block["type"], "feedback")
            self.assertFalse(block["correct"])
            self.assertEqual(block["correct_option"], "B")
            attempts = ledger_module.Ledger.load(course.paths["ledger"]).attempts
            self.assertEqual(attempts[0]["result"], "incorrect")

    def test_question_is_answered_from_the_corpus(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = self.make(tmp)
            block = course.handle({"type": "question", "text": "night anti-collision lighting", "timestamp": "t"})
            self.assertEqual(block["type"], "cited_answer")
            self.assertTrue(block["in_corpus"])

    def test_out_of_corpus_question_is_flagged_not_guessed(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = self.make(tmp)
            course.ledger.current_unit = None  # no unit on screen, so no unit material either
            block = course.handle({"type": "question", "text": "photosynthesis chlorophyll", "timestamp": "t"})
            self.assertFalse(block["in_corpus"])
            self.assertEqual(block["citations"], [])

    def test_every_response_is_written_to_the_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = self.make(tmp)
            course.handle({"type": "intake", "default_gear": 1, "timestamp": "t"})
            course.handle({"type": "question", "text": "controlled airspace", "timestamp": "t"})
            with open(course.paths["responses"], encoding="utf-8") as handle:
                lines = [json.loads(line) for line in handle if line.strip()]
            self.assertEqual([entry["type"] for entry in lines], ["intake", "question"])

    def test_unreachable_provider_returns_an_error_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = self.make(tmp, provider="anthropic")
            block = course.handle({"type": "advance", "unit": "UA.I.B.K16", "timestamp": "t"})
            self.assertEqual(block["type"], "error")
            self.assertIn("TEST_KEY_THAT_IS_NOT_SET", block["message"])

    def test_a_failed_model_call_is_recorded_with_an_error_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = self.make(tmp, provider="anthropic")
            course.handle({"type": "advance", "unit": "UA.I.B.K16", "timestamp": "t"})
            self.assertEqual(len(course.calls), 1)
            self.assertTrue(course.calls[0]["error"])
            self.assertIn("ms", course.calls[0])

    def test_requests_are_timed_and_logged(self):
        """The real handler on a free port: Server-Timing header, server and
        browser records in the metrics file, and a line in the terminal."""
        with tempfile.TemporaryDirectory() as tmp:
            course = self.make(tmp)
            with self.serving(course) as (base, printed):
                reply = post(base + "/api/respond", {"type": "question", "text": "controlled airspace"})
                timing = reply.headers.get("server-timing")
                reply.read()
                urllib.request.urlopen(base + "/api/state").read()
                post(base + "/api/metrics", {"kind": "request", "what": "state", "round_trip_ms": 5,
                                             "server_ms": 1, "draw_ms": 0}).read()

            self.assertRegex(timing, r"^total;dur=[\d.]+, qa;dur=\d+$")
            answer, state, browser = self.metrics(course)
            self.assertEqual((answer["method"], answer["type"]), ("POST", "question"))
            self.assertEqual([c["stage"] for c in answer["calls"]], ["qa"])
            self.assertEqual((state["path"], state["calls"]), ("/api/state", []))
            self.assertEqual((browser["source"], browser["kind"]), ("browser", "request"))
            self.assertIn("[server]  POST question", printed.getvalue())
            self.assertIn("model qa", printed.getvalue())
            self.assertIn("[browser] state", printed.getvalue())

    def test_the_chat_streams_over_http_and_is_logged(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = self.make(tmp)
            with self.serving(course) as (base, printed):
                reply = post(base + "/api/ask", {"type": "question", "text": "night anti-collision lighting",
                                                 "context_unit": "UA.I.B.K16"})
                content_type = reply.headers.get("content-type")
                events = [json.loads(line) for line in reply.read().decode("utf-8").splitlines()]
                history = json.loads(urllib.request.urlopen(base + "/api/chat").read())

            self.assertEqual(content_type, "application/x-ndjson")
            deltas = [e["delta"] for e in events if "delta" in e]
            self.assertGreater(len(deltas), 1)
            self.assertTrue(events[-1]["done"])
            self.assertEqual("".join(deltas), events[-1]["message"]["text"])
            self.assertEqual(events[-1]["meta"]["model"], "mock")
            self.assertEqual([m["role"] for m in history["messages"]], ["student", "tutor"])
            ask = [r for r in self.metrics(course) if r.get("type") == "ask"][0]
            self.assertIsNotNone(ask["first_text_ms"])
            self.assertEqual([c["stage"] for c in ask["calls"]], ["qa"])
            self.assertIn("first text", printed.getvalue())

    def test_respond_streams_when_the_page_asks_and_logs_the_first_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = self.make(tmp)
            with self.serving(course) as (base, printed):
                reply = post(base + "/api/respond", {"type": "intake", "default_gear": 2},
                             accept="application/x-ndjson")
                content_type = reply.headers.get("content-type")
                events = [json.loads(line) for line in reply.read().decode("utf-8").splitlines()]

            self.assertEqual(content_type, "application/x-ndjson")
            self.assertEqual(events[0]["start"]["stage"], "teach")
            self.assertTrue(any("delta" in e for e in events))
            self.assertEqual(events[-1]["block"]["type"], "lesson")
            record = [r for r in self.metrics(course) if r.get("type") == "intake"][0]
            self.assertIsNotNone(record["first_text_ms"])
            self.assertIn("[server]  POST intake", printed.getvalue())

    def test_an_unparseable_reply_is_flagged_in_the_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = self.make(tmp)
            course.client.complete = lambda *args, **kwargs: "I cannot help with that."
            block = course.handle({"type": "advance", "unit": "UA.I.B.K16", "timestamp": "t"})
            self.assertEqual(block["type"], "error")
            self.assertEqual(course.calls[-1]["error"], "unparseable")
            self.assertEqual(course.calls[-1]["reply"], "I cannot help with that.")
            self.assertIn("ERROR unparseable", server_module._metrics_line({
                "source": "server", "method": "POST", "type": "advance", "ms": 1, "bytes": 0,
                "calls": course.calls,
            }))

    def test_a_follow_up_carries_the_earlier_exchange_and_the_unit_on_screen(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = self.make(tmp)
            seen = []
            real = course.client.complete

            def spy(system, user, stage=None, on_text=None):
                seen.append(user)
                return real(system, user, stage=stage, on_text=on_text)

            course.client.complete = spy
            course.ask("night anti-collision lighting", "UA.I.B.K16")
            course.ask("and what about visibility?", "UA.I.B.K16")
            self.assertNotIn("EARLIER IN THIS CONVERSATION", seen[0])
            self.assertIn("STUDENT: night anti-collision lighting", seen[1])
            self.assertIn("TUTOR: Sample answer from the mock provider", seen[1])
            self.assertIn("THE UNIT ON SCREEN", seen[1])
            self.assertIn("UNIT: UA.I.B.K16", seen[1])
            self.assertEqual(len(course.chat), 4)

    def test_the_streamed_text_is_the_answer_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = self.make(tmp)
            events = []
            block = course.ask("night anti-collision lighting", emit=events.append)
            self.assertEqual(events[0]["start"]["status"], "Writing the answer")
            self.assertEqual("".join(e["delta"] for e in events if "delta" in e), block["answer"])

    def test_with_no_material_the_answer_comes_without_a_model_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = self.make(tmp)
            course.ledger.current_unit = None
            course.client.complete = lambda *args, **kwargs: self.fail("the model was called")
            block = course.ask("photosynthesis chlorophyll")
            self.assertFalse(block["in_corpus"])
            self.assertEqual([m["role"] for m in course.chat], ["student", "tutor"])

    def test_the_chat_is_paused_during_a_practice_exam(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = self.make(tmp)
            course.session.mock = {"order": [], "index": 0, "answers": {}}
            block = course.ask("controlled airspace")
            self.assertEqual(block["type"], "error")
            self.assertIn("paused", block["message"])
            self.assertEqual(course.chat, [])


if __name__ == "__main__":
    unittest.main()
