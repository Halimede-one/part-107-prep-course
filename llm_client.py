"""LLM client: provider plumbing only.

Standard library only, so the course stays dependency free. This module knows
how to call a provider and nothing about tutoring; block generation lives in
server.py in Phase 2 and moves to the prompt hierarchy in Phase 3.
"""

import json
import os
import subprocess
import threading
import urllib.error
import urllib.request


class LLMError(Exception):
    """A provider could not be reached or is not configured."""


class LLMClient:
    # Requests run in their own threads, and a chat answer can overlap a lesson,
    # so what the backend reported is kept per thread.
    _local = threading.local()

    def __init__(self, config):
        name = config.get("provider", "anthropic")
        providers = config.get("providers", {})
        if name not in providers:
            raise LLMError(
                "Unknown provider %r. Set \"provider\" in config.json to one of: %s."
                % (name, ", ".join(sorted(providers)))
            )
        self.name = name
        self.settings = providers[name]
        # The model name to show the student: the configured one until a backend
        # reports the model it actually used.
        self.model_name = self.settings.get("model") or name

    @property
    def last_metrics(self):
        """What the backend reported about this thread's last call (model, tokens,
        its own timings), for the server's metrics. Empty when it reports nothing."""
        return getattr(self._local, "metrics", {})

    @last_metrics.setter
    def last_metrics(self, value):
        self._local.metrics = value
        if value.get("model"):
            self.model_name = value["model"]

    @property
    def supports_web_search(self):
        return bool(self.settings.get("supports_web_search", False))

    @property
    def supports_course_search(self):
        """Whether the model can search the course folders itself. Only Claude Code
        runs its own tool loop; the other backends answer from the message alone."""
        return self.name == "claude_code"

    def complete(self, system, user, stage=None, on_text=None, research_dirs=None, on_tool=None):
        """Return the provider's text response.

        `stage` is a hint used only by the mock provider to pick a canned block.
        With `on_text`, the response is streamed: each piece of text is passed to
        it as the model writes it, and the full text is still returned at the end.
        With `research_dirs`, a backend that supports course search lets the model
        read those folders, and search the web if configured, before it answers;
        `on_tool` gets the name of each tool the model starts while streaming.
        """
        self.last_metrics = {}
        if self.name == "mock":
            return _mock_complete(stage, on_text)
        if self.name == "anthropic":
            return self._anthropic(system, user, on_text)
        if self.name == "claude_code":
            return self._claude_code(system, user, on_text, research_dirs, on_tool)
        if self.name == "ollama":
            return self._ollama(system, user, on_text)
        raise LLMError("Provider %r has no adapter." % self.name)

    def _anthropic(self, system, user, on_text=None):
        key_env = self.settings.get("api_key_env", "ANTHROPIC_API_KEY")
        key = os.environ.get(key_env)
        if not key:
            raise LLMError(
                "No API key found. Set %s in your environment, or set "
                "\"provider\" to \"ollama\" in config.json to run locally." % key_env
            )
        body = {
            "model": self.settings.get("model"),
            "max_tokens": 4096,  # room for a drawing (an SVG in the text) as well as the words
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if self.supports_web_search:
            # Server-side web search. The tool type carries its version suffix.
            # Verify against the current API docs at first local run; the flag
            # defaults to off so a format change breaks only this opt-in path.
            body["tools"] = [{
                "type": self.settings.get("web_search_tool_type", "web_search_20250305"),
                "name": "web_search",
                "max_uses": int(self.settings.get("web_search_max_uses", 3)),
            }]
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
        if on_text:
            body["stream"] = True
            return self._anthropic_stream(body, headers, on_text)
        data = self._post_json(self.settings["endpoint"], body, headers)
        self.last_metrics = dict(_usage_metrics(data.get("usage")), model=data.get("model"))
        return _anthropic_text(data)

    def _anthropic_stream(self, body, headers, on_text):
        """The Messages API with server-sent events. Text blocks are joined as
        `_anthropic_text` joins them; usage arrives at the start and the end."""
        texts, usage, model = {}, {}, None
        for event in self._post_stream(self.settings["endpoint"], body, headers):
            kind = event.get("type")
            if kind == "message_start":
                message = event.get("message") or {}
                model = message.get("model")
                usage.update(message.get("usage") or {})
            elif kind == "content_block_delta" and (event.get("delta") or {}).get("type") == "text_delta":
                piece = event["delta"].get("text", "")
                texts.setdefault(event.get("index", 0), []).append(piece)
                on_text(piece)
            elif kind == "message_delta":
                usage.update(event.get("usage") or {})
            elif kind == "error":
                raise LLMError("anthropic stopped with an error: %s" % (event.get("error") or {}).get("message", ""))
        self.last_metrics = dict(_usage_metrics(usage), model=model)
        return "\n".join("".join(texts[index]) for index in sorted(texts)).strip()

    def _ollama(self, system, user, on_text=None):
        body = {
            "model": self.settings.get("model"),
            "stream": bool(on_text),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if on_text:
            # One object per line; the last one carries the counts.
            pieces, data = [], {}
            for data in self._post_stream(self.settings["endpoint"], body, {}):
                if data.get("error"):
                    raise LLMError("ollama stopped with an error: %s" % data["error"])
                piece = (data.get("message") or {}).get("content", "")
                if piece:
                    pieces.append(piece)
                    on_text(piece)
            text = "".join(pieces)
        else:
            data = self._post_json(self.settings["endpoint"], body, {})
            text = (data.get("message") or {}).get("content", "")
        self.last_metrics = {
            "model": data.get("model"),
            "context_tokens": data.get("prompt_eval_count"),
            "output_tokens": data.get("eval_count"),
            "backend_ms": round((data.get("total_duration") or 0) / 1e6),
        }
        return text.strip()

    def _claude_code(self, system, user, on_text=None, research_dirs=None, on_tool=None):
        """Shell out to headless Claude Code, which draws on the signed-in plan.

        The prompt goes in on stdin rather than argv, so a long lesson prompt
        cannot hit the command-line length limit. Tools are disabled unless the
        call names research folders: this spawns an agent on the student's
        machine, and a tutor has no business reading or writing their files. A
        research call (the chat) gets read-only tools over those folders, and web
        search if the config allows it. The system prompt is replaced outright,
        because the Claude Code default is a coding agent.
        """
        command = self.settings.get("command", "claude")
        web = ["WebSearch", "WebFetch"] if research_dirs and self.supports_web_search else []
        tools = ["Read", "Grep", "Glob"] + web if research_dirs else []
        # Only the tools above, none of the user's settings or CLAUDE.md files, no
        # MCP servers (the user's claude.ai connectors and plugins would otherwise
        # load into every call, about 21k tokens of tool definitions), and no
        # session transcript left behind for each tutor turn.
        output = ["stream-json", "--verbose", "--include-partial-messages"] if on_text else ["json"]
        argv = [command, "-p", "--output-format"] + output + [
            "--system-prompt", system, "--tools", ",".join(tools), "--setting-sources", "", "--strict-mcp-config",
            "--no-session-persistence"]
        if research_dirs:
            # Claude Code reads freely in its working directory and the added ones,
            # and dontAsk refuses everything else. Allow rules cannot narrow reads
            # inside the working directory, so it must never be the course root,
            # which holds the practice-exam keys and the student's progress.
            argv += ["--permission-mode", "dontAsk"]
            if research_dirs[1:]:
                argv += ["--add-dir"] + list(research_dirs[1:])
            if web:
                argv += ["--allowedTools"] + web
        if self.settings.get("model"):
            argv += ["--model", self.settings["model"]]
        timeout = self.settings.get("timeout_seconds", 120)
        cwd = research_dirs[0] if research_dirs else None
        # Keep the developer's Claude Code memory out of the tutor's context.
        env = dict(os.environ, CLAUDE_CODE_DISABLE_AUTO_MEMORY="1")

        try:
            if on_text:
                finished = _claude_code_stream(argv, user, on_text, timeout, cwd, env, on_tool)
            else:
                finished = subprocess.run(argv, input=user, capture_output=True, text=True, timeout=timeout,
                                          cwd=cwd, env=env)
        except FileNotFoundError:
            raise LLMError(
                "Could not find the %r command. Install Claude Code and sign in with your "
                "Claude plan, or choose a different provider in config.json." % command
            )
        except subprocess.TimeoutExpired:
            raise LLMError("Claude Code did not respond within the timeout.")

        if finished.returncode != 0:
            detail = (finished.stderr or "").strip()[:400]
            raise LLMError("Claude Code exited with status %d: %s" % (finished.returncode, detail))

        try:
            data = json.loads(finished.stdout)
        except json.JSONDecodeError:
            raise LLMError("Claude Code returned a response that was not JSON.")

        # Claude Code can make small side calls on another model; the main
        # model is the one that wrote the most.
        models = data.get("modelUsage") or {}
        name, usage = max(models.items(), key=lambda kv: kv[1].get("outputTokens", 0), default=(None, {}))
        self.last_metrics = dict(
            _usage_metrics(data.get("usage")),
            model=usage.get("canonicalModel") or name,
            context_window=usage.get("contextWindow"),
            backend_ms=data.get("duration_ms"),
            api_ms=data.get("duration_api_ms"),
        )

        result = data.get("result")
        if not isinstance(result, str):
            raise LLMError(
                "Claude Code returned no result. Check that you are signed in by running "
                "`claude` once in a terminal."
            )
        return result.strip()

    def _post_json(self, url, body, headers):
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=dict(headers, **{"content-type": "application/json"}),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:400]
            raise LLMError("%s returned HTTP %s: %s" % (self.name, error.code, detail))
        except urllib.error.URLError as error:
            raise LLMError(
                "Could not reach %s at %s (%s). Check the endpoint in config.json, "
                "and that the service is running." % (self.name, url, error.reason)
            )
        except json.JSONDecodeError:
            raise LLMError("%s returned a response that was not JSON." % self.name)

    def _post_stream(self, url, body, headers):
        """POST and yield each JSON object the server streams back, from either
        server-sent events (`data: {...}` lines) or one object per line."""
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=dict(headers, **{"content-type": "application/json"}),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                for raw in response:
                    line = raw.decode("utf-8").strip()
                    if line.startswith("data:"):
                        line = line[5:].strip()
                    if line.startswith("{"):
                        yield json.loads(line)
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:400]
            raise LLMError("%s returned HTTP %s: %s" % (self.name, error.code, detail))
        except urllib.error.URLError as error:
            raise LLMError(
                "Could not reach %s at %s (%s). Check the endpoint in config.json, "
                "and that the service is running." % (self.name, url, error.reason)
            )
        except json.JSONDecodeError:
            raise LLMError("%s streamed a line that was not JSON." % self.name)
        except OSError as error:  # a read timeout or a dropped connection mid-stream
            raise LLMError("%s stopped streaming: %s" % (self.name, error))


def _claude_code_stream(argv, user, on_text, timeout, cwd=None, env=None, on_tool=None):
    """Run Claude Code with streamed output and pass each piece of text on, and
    the name of each tool the model starts to `on_tool`.

    Returns the run as `subprocess.run` would, with the final result event as
    its output, so the caller checks and reads both modes the same way.
    """
    expired = []
    result = ""
    with subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, cwd=cwd, env=env) as process:

        def expire():
            expired.append(True)
            process.kill()

        timer = threading.Timer(timeout, expire)
        timer.start()
        try:
            process.stdin.write(user)
            process.stdin.close()
            for line in process.stdout:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                inner = event.get("event") or {}
                delta = inner.get("delta") or {}
                block = inner.get("content_block") or {}
                if inner.get("type") == "content_block_delta" and delta.get("type") == "text_delta":
                    on_text(delta.get("text", ""))
                elif inner.get("type") == "content_block_start" and block.get("type") == "tool_use" and on_tool:
                    on_tool(block.get("name", ""))
                elif event.get("type") == "result":
                    result = line
            process.wait()
        finally:
            timer.cancel()
        errors = process.stderr.read()
    if expired:
        raise subprocess.TimeoutExpired(argv, timeout)
    return subprocess.CompletedProcess(argv, process.returncode, result, errors)


def _usage_metrics(usage):
    """Token counts from an Anthropic usage object, as the Messages API and
    Claude Code both report them. Context is everything the model read."""
    usage = usage or {}
    cached = usage.get("cache_read_input_tokens") or 0
    written = usage.get("cache_creation_input_tokens") or 0
    return {
        "context_tokens": (usage.get("input_tokens") or 0) + cached + written,
        "cached_tokens": cached,
        "output_tokens": usage.get("output_tokens") or 0,
    }


def _anthropic_text(data):
    """Join the text blocks of a Messages API response.

    When web search ran there may be several text blocks, with prose before
    the search and the JSON block after it. The server's block parser accepts
    prose around the JSON, so the adapter only joins; the tutor puts the links
    it used into the block's own citations, as the qa prompt requires.
    """
    return "\n".join(
        block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
    ).strip()


# Canned blocks for the mock provider. Test scaffolding, not course content.
_MOCK = {
    "lesson": {
        "type": "lesson",
        "unit": "UA.I.B.K16",
        "gear": 2,
        "title": "Prior authorization in controlled airspace",
        "body": "Sample lesson from the mock provider. Phase 2 tests the plumbing; "
                "real lessons arrive with the prompt hierarchy in Phase 3.",
        "citations": [{"source": "Mock source", "url": "https://www.ecfr.gov/current/title-14/part-107"}],
    },
    "question": {
        "type": "question",
        "unit": "UA.I.B.K16",
        "gear": 2,
        "question_id": "mock-q1",
        "stem": "Sample question from the mock provider. Which option is keyed correct?",
        "answer": "B",
        "rationale": "Server-only fields: the shell never receives these.",
        "options": [
            {"id": "A", "text": "Option A"},
            {"id": "B", "text": "Option B, the keyed answer in the fixture"},
            {"id": "C", "text": "Option C"},
        ],
    },
    "feedback": {
        "type": "feedback",
        "unit": "UA.I.B.K16",
        "gear": 2,
        "question_id": "mock-q1",
        "correct": True,
        "correct_option": "B",
        "message": "Sample feedback from the mock provider.",
        "citations": [{"source": "Mock source", "url": "https://www.ecfr.gov/current/title-14/part-107"}],
    },
    "enhance": {
        "explanation": "Sample explanation from the mock provider.",
        "illustration": "Sample scenario from the mock provider.",
        "misreading": "",
        "skip": False,
    },
    "debrief": {
        "type": "debrief",
        "body": "Sample debrief from the mock provider.",
        "citations": [],
    },
    "qa": {
        "type": "cited_answer",
        "question": "",
        "answer": "Sample answer from the mock provider, grounded in the retrieved chunk.",
        "in_corpus": True,
        "citations": [{"source": "Mock source", "url": "https://www.ecfr.gov/current/title-14/part-107"}],
    },
    "revision": {
        "type": "revision",
        "note": "Sample revision from the mock provider, with a diagram.",
        "text": "---\nsource: Mock source | https://www.ecfr.gov/current/title-14/part-107\n---\n"
                "Sample revised lesson from the mock provider.\n\n"
                "```svg A sample box\n<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 120 40' width='120' "
                "height='40'><rect x='1' y='1' width='118' height='38' fill='none' stroke='black'/>"
                "<text x='10' y='25'>Sample</text></svg>\n```\n",
    },
}


def _mock_complete(stage, on_text=None):
    text = json.dumps(_MOCK.get(stage or "lesson", _MOCK["lesson"]))
    if on_text:
        for start in range(0, len(text), 16):
            on_text(text[start:start + 16])
    return text


def load_config(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)
