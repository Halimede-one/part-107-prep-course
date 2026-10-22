"""The instructor workspace on the server: reading, revising, and saving lesson files.

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
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import orchestrator                  # noqa: E402
import server as server_module       # noqa: E402
import status                        # noqa: E402
from test_phase3 import make_course  # noqa: E402

UNIT = "UA.I.B.K21c"
STATUS = ("# Content status\n\n| Unit | Gear 1 | Gear 2 | Gear 3 | Reference facts | Status | Notes |\n"
          "|---|---|---|---|---|---|---|\n| %s | | drafted | | drafted | vetted | |\n" % UNIT)


def instructor_course(tmp):
    course = make_course(tmp)
    course.instructor = True
    with open(os.path.join(course.paths["curriculum"], "STATUS.md"), "w", encoding="utf-8") as handle:
        handle.write(STATUS)
    return course


def files_in(folder):
    return sorted(os.path.relpath(os.path.join(d, f), folder) for d, _, names in os.walk(folder) for f in names)


@contextlib.contextmanager
def serving(course):
    """The real handler on a free port, with its terminal lines captured."""
    httpd = server_module.CourseServer(("127.0.0.1", 0), course)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            yield "http://127.0.0.1:%d" % httpd.server_address[1]
    finally:
        httpd.shutdown()
        httpd.server_close()


def request(url, payload=None):
    """(status, body text) for a GET, or a POST when there is a payload."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"content-type": "application/json"},
                                 method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req) as reply:
            return reply.status, reply.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8")


class TestInstructorMode(unittest.TestCase):
    def test_without_the_flag_the_workspace_does_not_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = instructor_course(tmp)
            course.instructor = False
            before = files_in(course.paths["curriculum"])
            with serving(course) as base:
                self.assertEqual(request(base + "/api/author?unit=%s&gear=2" % UNIT)[0], 404)
                self.assertEqual(request(base + "/api/author/save", {"unit": UNIT, "gear": 2, "text": "x"})[0], 404)
                self.assertEqual(request(base + "/api/author/ask", {"unit": UNIT, "gear": 2, "request": "x"})[0], 404)
                self.assertEqual(request(base + "/api/author/questions?unit=%s" % UNIT)[0], 404)
                self.assertEqual(request(base + "/api/author/questions", {"unit": UNIT, "items": []})[0], 404)
                self.assertFalse(json.loads(request(base + "/api/state")[1])["instructor"])
            self.assertEqual(files_in(course.paths["curriculum"]), before)
            self.assertFalse(os.path.exists(course.paths["questions"]))

    def test_with_the_flag_the_workspace_reads_a_lesson_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = instructor_course(tmp)
            with serving(course) as base:
                code, body = request(base + "/api/author?unit=%s&gear=3" % UNIT)
                self.assertTrue(json.loads(request(base + "/api/state")[1])["instructor"])
            self.assertEqual(code, 200)
            info = json.loads(body)
            self.assertEqual((info["unit"], info["gear"], info["text"]), (UNIT, 3, ""))  # no Foundational file yet
            self.assertIn("source:", info["guided"])
            self.assertIsNone(info["files"]["3"])
            self.assertEqual(info["status"]["status"], "vetted")

    def test_only_real_units_and_gears_are_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = instructor_course(tmp)
            before = files_in(course.paths["curriculum"])
            with serving(course) as base:
                for unit, gear in (("UA.I.Z.K99", 2), (UNIT, 4), ("../../config", 2), (UNIT, "x")):
                    self.assertEqual(request(base + "/api/author/save",
                                             {"unit": unit, "gear": gear, "text": "x"})[0], 400, (unit, gear))
                self.assertEqual(request(base + "/api/author?unit=..%2F..%2Fconfig&gear=2")[0], 400)
            self.assertEqual(files_in(course.paths["curriculum"]), before)

    def test_only_real_units_are_accepted_for_questions(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = instructor_course(tmp)
            with serving(course) as base:
                self.assertEqual(request(base + "/api/author/questions?unit=..%2F..%2Fconfig")[0], 400)
                for payload in ({"unit": "../../config", "items": []}, {"unit": ["x"], "items": []},
                                {"unit": UNIT, "items": "x"}, {"unit": UNIT}):
                    self.assertEqual(request(base + "/api/author/questions", payload)[0], 400, payload)
            self.assertFalse(os.path.exists(course.paths["questions"]))

    def test_read_and_save_the_questions_over_http(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = instructor_course(tmp)
            question = {"stem": "How far must you see?", "a": "1 statute mile", "b": "3 statute miles",
                        "c": "5 statute miles", "answer": "b", "rationale": "107.51 sets 3 statute miles.",
                        "source": "Fixture 107.51", "url": "https://example.invalid/fixture/107-51"}
            with serving(course) as base:
                empty = json.loads(request(base + "/api/author/questions?unit=%s" % UNIT)[1])
                code, body = request(base + "/api/author/questions",
                                     {"unit": UNIT, "guidance": "  Make sure they know it is flight visibility.\n",
                                      "items": [question]})
                again = json.loads(request(base + "/api/author/questions?unit=%s" % UNIT)[1])
            self.assertEqual((empty["guidance"], empty["items"]), ("", []))
            # The lesson and the fact cite the same source, so it is offered once.
            self.assertEqual(empty["sources"], [{"source": "Fixture 107.51", "url": "https://example.invalid/fixture/107-51"}])
            saved = json.loads(body)
            self.assertEqual((code, saved["saved"]), (200, True))
            self.assertEqual(again["guidance"], "Make sure they know it is flight visibility.")
            self.assertEqual(again["items"], [dict(question, item=UNIT + "-i1", unit=UNIT, answer="B")])
            self.assertEqual(saved["items"], again["items"])

    def test_a_save_posted_from_another_site_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = instructor_course(tmp)
            lesson = orchestrator.lesson_path(course.paths["curriculum"], UNIT, 2)
            text = course.author_file(UNIT, 2)["text"].replace("Stub teaching content", "Edited teaching content")

            def save(base, origin):
                # text/plain, as a cross-site form or fetch would send it without a preflight
                headers = {"content-type": "text/plain"}
                if origin:
                    headers["origin"] = origin
                req = urllib.request.Request(base + "/api/author/save", headers=headers, method="POST",
                                             data=json.dumps({"unit": UNIT, "gear": 2, "text": text}).encode("utf-8"))
                try:
                    with urllib.request.urlopen(req) as reply:
                        return reply.status
                except urllib.error.HTTPError as error:
                    return error.code

            with serving(course) as base:
                with open(lesson, encoding="utf-8") as handle:
                    before = handle.read()
                self.assertEqual(save(base, "http://evil.example"), 403)
                self.assertEqual(save(base, "http://localhost:1"), 403)
                with open(lesson, encoding="utf-8") as handle:
                    self.assertEqual(handle.read(), before)
                self.assertEqual(save(base, base), 200)  # the course's own page
                self.assertEqual(save(base, None), 200)  # curl, the tools, and the tests send no origin
            self.assertEqual(course.tutor.content(UNIT, 2)["version"], 3)


class TestSaving(unittest.TestCase):
    def test_a_save_raises_the_version_and_the_next_lesson_uses_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = instructor_course(tmp)
            text = course.author_file(UNIT, 2)["text"].replace("Stub teaching content", "Edited teaching content")
            result = course.author_save(UNIT, 2, text, note="Clearer opening.", vetted=True)
            self.assertEqual((result["saved"], result["version"], result["warnings"]), (True, 2, []))
            content = course.tutor.content(UNIT, 2)
            self.assertEqual(content["version"], 2)
            self.assertIn("Edited teaching content", course.tutor.teach_context(UNIT, 2, content))
            row = status.row(os.path.join(course.paths["curriculum"], "STATUS.md"), UNIT)
            self.assertEqual((row["gear 2"], row["status"]), ("v2 vetted", "vetted"))
            self.assertIn("Clearer opening.", row["notes"])

    def test_a_save_not_yet_vetted_marks_the_unit_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = instructor_course(tmp)
            course.author_save(UNIT, 1, "---\nsource: S | https://example.invalid/s\n---\nShort form.\n", vetted=False)
            row = status.row(os.path.join(course.paths["curriculum"], "STATUS.md"), UNIT)
            self.assertEqual((row["gear 1"], row["status"]), ("v1 edited", "draft"))
            self.assertEqual(course.tutor.content(UNIT, 1)["form"], "written")

    def test_saving_a_tutor_draft_removes_the_draft_mark(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = instructor_course(tmp)
            course.save_draft(UNIT, {"type": "lesson", "body": "Step 1.",
                                     "citations": [{"source": "S", "url": "https://example.invalid/s"}]})
            self.assertEqual(course.tutor.content(UNIT, 3)["form"], "draft")
            info = course.author_file(UNIT, 3)
            self.assertNotIn("draft:", info["text"])  # the course keeps the mark, not the editor
            course.author_save(UNIT, 3, info["text"].replace("Step 1.", "Step 1, reviewed."), vetted=False)
            content = course.tutor.content(UNIT, 3)
            self.assertEqual((content["form"], content["version"]), ("written", 2))

    def test_a_drawing_becomes_an_image_file_and_a_markdown_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = instructor_course(tmp)
            text = ("---\nsource: S | https://example.invalid/s\n---\nThe picture:\n\n"
                    "```svg Altitude above the tower\n<svg viewBox='0 0 10 10' width='10' height='10'>"
                    "<rect width='10' height='10'/></svg>\n```\n\nAfter it.\n")
            result = course.author_save(UNIT, 3, text)
            self.assertEqual(result["images"], ["images/%s-1.svg" % UNIT])
            saved = course.tutor.content(UNIT, 3)["body"]
            self.assertIn("![Altitude above the tower](images/%s-1.svg)" % UNIT, saved)
            self.assertNotIn("<svg", saved)
            with open(os.path.join(course.paths["curriculum"], "images", "%s-1.svg" % UNIT), encoding="utf-8") as handle:
                self.assertIn('xmlns="http://www.w3.org/2000/svg"', handle.read())
            # A second drawing gets the next number.
            course.author_save(UNIT, 1, text)
            self.assertIn("images/%s-2.svg" % UNIT, course.tutor.content(UNIT, 1)["body"])

    def test_a_drawing_that_could_run_code_is_refused_and_nothing_is_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = instructor_course(tmp)
            before = files_in(course.paths["curriculum"])
            for svg in ("<svg><script>alert(1)</script></svg>", "<svg><rect onload='x()'/></svg>",
                        "<svg><a href='https://example.com'><text>x</text></a></svg>"):
                result = course.author_save(UNIT, 3, "Body.\n\n```svg Bad\n%s\n```\n" % svg)
                self.assertIn("error", result, svg)
            self.assertEqual(files_in(course.paths["curriculum"]), before)

    def test_a_file_without_a_source_line_is_saved_with_a_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = instructor_course(tmp)
            result = course.author_save(UNIT, 1, "Just a body.\n")
            self.assertTrue(result["saved"])
            self.assertTrue(any("no source line" in w for w in result["warnings"]))


class TestAssistant(unittest.TestCase):
    def test_the_message_carries_the_request_the_editor_and_the_ground_truth(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = instructor_course(tmp)
            seen = []
            real = course.client.complete

            def spy(system, user, stage=None, **kwargs):
                seen.append((system, user))
                return real(system, user, stage=stage, **kwargs)

            course.client.complete = spy
            editor = "---\nsource: S | https://example.invalid/s\n---\nMy unsaved Foundational steps.\n"
            history = [{"role": "instructor", "text": "Add a step."}, {"role": "assistant", "text": "Added step 2."}]
            course.author_ask(UNIT, 3, editor, "Add a diagram of the visibility.", history=history)
            system, message = seen[-1]
            self.assertIn("help an instructor edit a lesson", system)
            self.assertIn("INSTRUCTOR REQUEST: Add a diagram of the visibility.", message)
            self.assertIn("My unsaved Foundational steps.", message)
            self.assertIn("THE GUIDED LESSON", message)
            self.assertIn("VETTED FACTS", message)
            self.assertIn("INSTRUCTOR: Add a step.", message)
            self.assertIn("ASSISTANT: Added step 2.", message)

    def test_the_note_and_the_text_stream_and_the_end_carries_a_diff(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = instructor_course(tmp)
            events = []
            final = course.author_ask(UNIT, 2, course.author_file(UNIT, 2)["text"], "Add a diagram.", emit=events.append)
            self.assertEqual((events[0]["start"]["stage"], events[0]["start"]["status"]), ("author", "Revising the lesson"))
            streamed = {f: "".join(e["delta"] for e in events if e.get("field") == f) for f in ("note", "file")}
            self.assertEqual(streamed["note"], final["note"])
            self.assertEqual(streamed["file"].rstrip("\n"), final["text"].rstrip("\n"))
            self.assertTrue(any(line.startswith("+```svg") for line in final["diff"]))
            self.assertTrue(any(line.startswith("-") and not line.startswith("---") for line in final["diff"]))

    def test_ask_and_save_over_http(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = instructor_course(tmp)
            with serving(course) as base:
                code, body = request(base + "/api/author/ask", {"unit": UNIT, "gear": 3, "text": "", "request": "First version."})
                final = json.loads(body.strip().splitlines()[-1])
                code2, saved = request(base + "/api/author/save",
                                       {"unit": UNIT, "gear": 3, "text": final["text"], "note": "First.", "vetted": False})
            self.assertEqual((code, code2), (200, 200))
            self.assertTrue(final["done"])
            saved = json.loads(saved)
            self.assertEqual((saved["version"], saved["images"]), (1, ["images/%s-1.svg" % UNIT]))
            self.assertEqual(saved["file"]["files"]["3"], {"version": 1, "draft": False})


FILE = ("---\nsource: S | https://example.invalid/s\n---\nStep 1, the picture.\n\n"
        "Worked example. A pilot flies at 200 feet.\n\nMemory handle.\n")


class TestEdits(unittest.TestCase):
    def test_a_span_a_single_from_and_an_insertion(self):
        out = server_module.apply_edits(FILE, [
            {"from": "Step 1", "to": "picture.", "text": "Step 1, the new picture."},
            {"from": "Memory handle.", "text": "Memory handle: ask first."},
            {"after": "at 200 feet.", "text": "\n\n```svg A diagram\n<svg></svg>\n```"},
        ])
        self.assertEqual(out, FILE.replace("Step 1, the picture.", "Step 1, the new picture.")
                                  .replace("Memory handle.", "Memory handle: ask first.")
                                  .replace("at 200 feet.", "at 200 feet.\n\n```svg A diagram\n<svg></svg>\n```"))

    def test_changes_that_do_not_fit_are_refused(self):
        for edits in (
            [{"from": "Nowhere", "text": "x"}],                       # not in the file
            [{"from": "e", "text": "x"}],                             # more than once
            [{"from": "Memory", "to": "Step 1", "text": "x"}],        # the end before the start
            [{"from": "Step 1", "to": "feet.", "text": "x"}, {"from": "Worked example", "text": "y"}],  # overlap
            [{"from": "Step 1"}],                                     # no new text
            [{"text": "x"}],                                          # no place
        ):
            with self.assertRaises(ValueError, msg=edits):
                server_module.apply_edits(FILE, edits)


def scripted(course, replies):
    """Answer the model calls with `replies` in turn, streamed in one piece. Returns the messages sent."""
    sent = []

    def complete(system, user, stage=None, on_text=None, research_dirs=None, on_tool=None):
        sent.append(user)
        reply = json.dumps(replies[len(sent) - 1])
        if on_text:
            on_text(reply)
        return reply

    course.client.complete = complete
    return sent


class TestAssistantEdits(unittest.TestCase):
    def test_changes_are_applied_to_the_editor_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = instructor_course(tmp)
            sent = scripted(course, [{"type": "revision", "note": "Added a diagram.", "edits": [
                {"after": "at 200 feet.", "text": "\n\n```svg Altitude\n<svg viewBox='0 0 1 1'></svg>\n```"}]}])
            events = []
            final = course.author_ask(UNIT, 3, FILE, "Add a diagram.", emit=events.append)
            self.assertEqual(len(sent), 1)
            self.assertIn("at 200 feet.\n\n```svg Altitude", final["text"])
            self.assertTrue(final["text"].startswith("---\nsource: S"))
            self.assertEqual([line[0] for line in final["diff"][2:] if line[:1] in "+-"], ["+", "+", "+", "+"])
            self.assertEqual("".join(e["delta"] for e in events if e.get("field") == "note"), "Added a diagram.")
            self.assertFalse([e for e in events if e.get("field") == "file"])  # changes do not stream as a file

    def test_changes_that_do_not_fit_lead_to_one_request_for_the_whole_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = instructor_course(tmp)
            whole = FILE.replace("Memory handle.", "Memory handle: ask first.")
            sent = scripted(course, [
                {"type": "revision", "note": "Changed it.", "edits": [{"from": "Not in the file", "text": "x"}]},
                {"type": "revision", "note": "Changed it, whole file.", "file": whole},
            ])
            events = []
            final = course.author_ask(UNIT, 3, FILE, "Change the handle.", emit=events.append)
            self.assertEqual(len(sent), 2)
            self.assertIn("YOUR CHANGES DID NOT FIT THE FILE", sent[1])
            self.assertIn("'Not in the file' is not in the file", sent[1])
            self.assertEqual((final["text"], final["note"]), (whole, "Changed it, whole file."))
            self.assertEqual(len([e for e in events if "start" in e]), 2)  # the page starts the reply afresh

    def test_a_whole_file_reply_still_works(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = instructor_course(tmp)
            scripted(course, [{"type": "revision", "note": "A first version.", "file": FILE}])
            final = course.author_ask(UNIT, 1, "", "Write a first version.")
            self.assertEqual(final["text"], FILE)


if __name__ == "__main__":
    unittest.main()
