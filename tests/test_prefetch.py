"""Prefetch tests: the next model call is written while the student reads.

Run from the course folder:  python3 -m unittest discover -s tests -v
"""

import json
import os
import sys
import tempfile
import threading
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import orchestrator                     # noqa: E402
import server as server_module          # noqa: E402
from llm_client import LLMClient, LLMError  # noqa: E402
from test_phase3 import make_course     # noqa: E402


class Scripted(LLMClient):
    """The mock backend with a distinct question id per call and a record of
    every call. A stage in `hold` pauses halfway until its event is set; a
    stage in `fail_once` raises on its next call."""

    def __init__(self, config):
        super().__init__(config)
        self.calls = []
        self.hold = {}
        self.fail_once = set()
        self._lock = threading.Lock()

    def complete(self, system, user, stage=None, on_text=None, research_dirs=None, on_tool=None):
        with self._lock:
            self.calls.append(stage)
            n = len(self.calls)
            fail = stage in self.fail_once
            self.fail_once.discard(stage)
        self.last_metrics = {"model": "scripted", "output_tokens": 10}
        if fail:
            raise LLMError("scripted failure")
        block = {
            "lesson": {"type": "lesson", "title": "Lesson %d" % n, "body": "Body %d." % n, "citations": []},
            "question": {"type": "question", "question_id": "q%d" % n, "stem": "Stem %d?" % n,
                         "options": [{"id": x, "text": "Option " + x} for x in "ABC"],
                         "answer": "B", "rationale": "Rationale %d" % n},
            "feedback": {"type": "feedback", "message": "Message %d." % n, "citations": []},
        }.get(stage, {"type": "debrief", "body": "Debrief.", "citations": []})
        text = json.dumps(block)
        half = len(text) // 2
        if on_text:
            on_text(text[:half])
        if stage in self.hold:
            self.hold[stage].wait(5)
        if on_text:
            on_text(text[half:])
        return text


def scripted_course(tmp):
    course = make_course(tmp)
    course.client = Scripted(course.config)
    return course


def settle(course):
    """Wait for every prefetch to finish writing."""
    for job in list(course.prefetches.values()):
        job.follow()


def answer(course, question, option):
    return course.handle({"type": "answer", "question_id": question["question_id"],
                          "unit": question["unit"], "selected_option": option, "timestamp": "t"})


def metrics(course):
    path = course.paths["metrics"]
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


class TestPrefetch(unittest.TestCase):
    def test_the_question_after_a_lesson_is_written_alongside_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = scripted_course(tmp)
            lesson = course.handle({"type": "intake", "default_gear": 1, "timestamp": "t"})
            self.assertEqual(lesson["type"], "lesson")
            settle(course)
            self.assertEqual(sorted(course.client.calls), ["lesson", "question"])

            question = course.handle({"type": "advance", "timestamp": "t"})
            self.assertEqual(question["type"], "question")
            self.assertEqual(len(course.client.calls), 2)  # no new model call
            self.assertEqual(course.calls[-1]["prefetched"], "ready")
            # The key still stays on the server.
            self.assertEqual(set(question) & {"answer", "rationale"}, set())
            self.assertEqual(course.session.pending["answer"], "B")
            # A question's feedback depends on the answer, so nothing is guessed now.
            self.assertEqual(course.prefetches, {})
            self.assertIn("prefetched, ready", server_module._metrics_line({
                "source": "server", "method": "POST", "type": "advance", "ms": 1, "bytes": 0,
                "calls": course.calls,
            }))

    def test_a_right_answer_short_of_mastery_prefetches_the_next_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = scripted_course(tmp)
            course.handle({"type": "intake", "default_gear": 1, "timestamp": "t"})
            question = course.handle({"type": "advance", "timestamp": "t"})
            feedback = answer(course, question, "B")
            self.assertTrue(feedback["correct"])
            settle(course)
            before = len(course.client.calls)

            second = course.handle({"type": "advance", "timestamp": "t"})
            self.assertEqual(second["type"], "question")
            self.assertNotEqual(second["question_id"], question["question_id"])
            self.assertEqual(len(course.client.calls), before)
            self.assertEqual(course.calls[-1]["prefetched"], "ready")

    def test_a_wrong_answer_prefetches_the_re_teach_at_the_deeper_gear(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = scripted_course(tmp)
            course.handle({"type": "intake", "default_gear": 1, "timestamp": "t"})
            question = course.handle({"type": "advance", "timestamp": "t"})
            answer(course, question, "A")
            settle(course)
            lessons = course.client.calls.count("lesson")

            course.calls = []
            again = course.handle({"type": "advance", "timestamp": "t"})
            self.assertEqual(again["type"], "lesson")
            self.assertEqual(course.client.calls.count("lesson"), lessons)
            self.assertEqual((course.calls[-1]["stage"], course.calls[-1]["prefetched"]), ("remediate", "ready"))
            self.assertEqual(course.ledger.units[question["unit"]]["current_gear"], 2)

    def test_a_mastered_unit_prefetches_the_next_units_lesson(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = scripted_course(tmp)
            course.handle({"type": "intake", "default_gear": 1, "timestamp": "t"})
            first = course.handle({"type": "advance", "timestamp": "t"})
            answer(course, first, "B")
            second = course.handle({"type": "advance", "timestamp": "t"})
            answer(course, second, "B")
            self.assertEqual(course.ledger.mastery(first["unit"]), "mastered")
            settle(course)
            lessons = course.client.calls.count("lesson")

            course.calls = []
            lesson = course.handle({"type": "advance", "timestamp": "t"})
            self.assertEqual(lesson["type"], "lesson")
            self.assertEqual(course.client.calls.count("lesson"), lessons)
            self.assertEqual((course.calls[-1]["stage"], course.calls[-1]["prefetched"]), ("teach", "ready"))
            self.assertNotEqual(course.ledger.current_unit, first["unit"])

    def test_a_review_answer_prefetches_the_next_review_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = scripted_course(tmp)
            course.handle({"type": "intake", "default_gear": 1, "timestamp": "t"})
            question = course.handle({"type": "advance", "timestamp": "t"})
            # Treat the question on screen as a review check, with one more review waiting.
            course.session.stage = "review_quiz"
            course.session.review_queue = ["UA.I.C.K4"]
            answer(course, question, "B")
            settle(course)
            before = len(course.client.calls)

            review = course.handle({"type": "advance", "timestamp": "t"})
            self.assertEqual((review["type"], review["unit"], review.get("review")), ("question", "UA.I.C.K4", True))
            self.assertEqual(len(course.client.calls), before)
            self.assertEqual(course.calls[-1]["prefetched"], "ready")

    def test_a_unit_picked_from_the_tree_does_not_match_and_the_guess_is_logged(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = scripted_course(tmp)
            course.handle({"type": "intake", "default_gear": 1, "timestamp": "t"})
            settle(course)
            lesson = course.handle({"type": "goto", "unit": "UA.I.B.K21c", "gear": 1, "timestamp": "t"})
            self.assertEqual(lesson["type"], "lesson")
            self.assertEqual(course.session.chosen, "UA.I.B.K21c")
            self.assertEqual(course.client.calls.count("lesson"), 2)  # the picked unit was taught fresh
            unused = [r for r in metrics(course) if r.get("kind") == "prefetch"]
            self.assertEqual([(r["stage"], r["outcome"]) for r in unused], [("quiz", "unused")])
            self.assertIn("prefetch quiz", server_module._metrics_line(unused[0]))
            # The new prefetch is the question on the picked unit, and it is used.
            settle(course)
            question = course.handle({"type": "advance", "timestamp": "t"})
            self.assertEqual(question["unit"], "UA.I.B.K21c")
            self.assertEqual(course.calls[-1]["prefetched"], "ready")

    def test_continue_while_the_prefetch_is_writing_streams_what_is_written_then_the_rest(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = scripted_course(tmp)
            gate = course.client.hold["question"] = threading.Event()
            course.handle({"type": "intake", "default_gear": 1, "timestamp": "t"})
            events, result = [], {}

            def press_continue():
                result["block"] = course.handle({"type": "advance", "timestamp": "t"}, emit=events.append)
                result["calls"] = list(course.calls)

            worker = threading.Thread(target=press_continue)
            worker.start()
            deadline = time.time() + 2
            while not any("delta" in e for e in events) and time.time() < deadline:
                time.sleep(0.01)
            self.assertTrue(any("delta" in e for e in events), "the text written so far arrives at once")
            self.assertTrue(worker.is_alive(), "the request waits for the rest")
            gate.set()
            worker.join(5)

            block = result["block"]
            self.assertEqual("".join(e["delta"] for e in events if e.get("field") == "stem"), block["stem"])
            self.assertEqual(course.client.calls.count("question"), 1)
            self.assertEqual(result["calls"][-1]["prefetched"], "joined")

    def test_a_failed_prefetch_is_made_again_from_a_clean_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = scripted_course(tmp)
            course.client.fail_once.add("question")
            course.handle({"type": "intake", "default_gear": 1, "timestamp": "t"})
            settle(course)
            events = []
            question = course.handle({"type": "advance", "timestamp": "t"}, emit=events.append)
            self.assertEqual(question["type"], "question")
            self.assertEqual(course.client.calls.count("question"), 2)
            self.assertEqual(len([e for e in events if "start" in e]), 1)  # failed before it wrote anything
            self.assertEqual([r["outcome"] for r in metrics(course) if r.get("kind") == "prefetch"], ["failed"])

    def test_the_first_visit_at_foundational_keeps_its_prefetched_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = scripted_course(tmp)
            unit = "UA.I.B.K21c"  # no Foundational file yet
            course.handle({"type": "goto", "unit": unit, "gear": 3, "timestamp": "t"})
            settle(course)
            self.assertTrue(os.path.isfile(orchestrator.lesson_path(course.paths["curriculum"], unit, 3)))
            question = course.handle({"type": "advance", "timestamp": "t"})
            self.assertEqual(question["type"], "question")
            self.assertEqual(course.calls[-1]["prefetched"], "ready")
            self.assertEqual(course.client.calls.count("question"), 1)
            # This session keeps the Guided lesson; the next one gets the draft.
            self.assertEqual(course.content(unit, 3)["form"], "derived")
            course.handle({"type": "intake", "default_gear": 1, "timestamp": "t"})
            self.assertEqual(course.content(unit, 3)["form"], "draft")

    def test_a_re_teach_at_foundational_keeps_its_prefetched_question_after_the_background_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = scripted_course(tmp)
            unit = "UA.I.B.K21c"
            course.handle({"type": "goto", "unit": unit, "gear": 2, "timestamp": "t"})
            question = course.handle({"type": "advance", "timestamp": "t"})
            answer(course, question, "A")                               # a miss: Foundational next
            course.handle({"type": "advance", "timestamp": "t"})        # the re-teach, with a draft in the background
            server_module.wait_for_drafts()
            settle(course)
            self.assertTrue(os.path.isfile(orchestrator.lesson_path(course.paths["curriculum"], unit, 3)))
            questions = course.client.calls.count("question")
            again = course.handle({"type": "advance", "timestamp": "t"})
            self.assertEqual((again["type"], again["gear"]), ("question", 3))
            self.assertEqual(course.calls[-1]["prefetched"], "ready")
            self.assertEqual(course.client.calls.count("question"), questions)

    def test_nothing_is_guessed_at_a_task_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = scripted_course(tmp)
            course.ledger.last_task = "B"
            course.session.next_action = ("advance", None)
            for unit in ("UA.I.B.K16",):
                course.ledger.record_attempt(unit, "x1", 1, True, "t")
                course.ledger.record_attempt(unit, "x2", 1, True, "t")
            self.assertEqual(course.call_after_answer(False)["stage"], "teach")  # the next unit, still in task B
            course.ledger.record_attempt("UA.I.B.K21c", "y1", 1, True, "t")
            course.ledger.record_attempt("UA.I.B.K21c", "y2", 1, True, "t")
            self.assertIsNone(course.call_after_answer(False))  # task B done: reviews and unparking come first


if __name__ == "__main__":
    unittest.main()
