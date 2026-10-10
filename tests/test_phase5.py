"""Phase 5 tests: the practice exam and the readiness gate.

Run from the course folder:  python3 -m unittest discover -s tests -v
"""

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(ROOT, "tests", "fixtures")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import items as items_module      # noqa: E402
import ledger as ledger_module    # noqa: E402
import mockexam                   # noqa: E402
from test_phase3 import make_course, stub_ledger, UNITS  # noqa: E402

MOCK_PATH = os.path.join(FIXTURES, "mock-stub.md")
KEY = {"m-1": "B", "m-2": "A", "m-3": "C", "m-4": "B"}


def exam_course(tmp):
    course = make_course(tmp)
    course.paths["items"] = MOCK_PATH
    course.items = items_module.load_items(MOCK_PATH)
    course.handle({"type": "intake", "default_gear": 1, "timestamp": "t"})
    return course


def sit_exam(course, answer_for):
    """Run a whole attempt; answer_for(item_id) gives the chosen option."""
    block = course.handle({"type": "mock_start", "timestamp": "seed"})
    seen = []
    while block["type"] == "question":
        seen.append(block["question_id"])
        block = course.handle({
            "type": "mock_answer", "question_id": block["question_id"],
            "unit": block["unit"], "selected_option": answer_for(block["question_id"]),
            "timestamp": "t",
        })
    return block, seen


class TestMockItems(unittest.TestCase):
    def test_items_with_stems_form_the_exam_and_bare_keys_do_not(self):
        items = items_module.load_items(MOCK_PATH)
        self.assertEqual(sorted(mockexam.mock_items(items)), ["m-1", "m-2", "m-3", "m-4"])
        bare = items_module.load_items(os.path.join(FIXTURES, "items.md"))
        self.assertEqual(mockexam.mock_items(bare), {})

    def test_attempt_is_shuffled_but_complete_and_reproducible(self):
        items = items_module.load_items(MOCK_PATH)
        a = mockexam.new_attempt(items, seed="x")
        b = mockexam.new_attempt(items, seed="x")
        self.assertEqual(sorted(a["order"]), ["m-1", "m-2", "m-3", "m-4"])
        self.assertEqual(a["order"], b["order"])

    def test_question_block_carries_no_key(self):
        items = items_module.load_items(MOCK_PATH)
        block = mockexam.question_block(items, mockexam.new_attempt(items, seed=1), 480)
        self.assertTrue(block["mock"])
        self.assertNotIn("answer", block)
        self.assertNotIn("rationale", block)
        self.assertEqual(block["total"], 4)
        self.assertEqual([o["id"] for o in block["options"]], ["A", "B", "C"])


class TestScoring(unittest.TestCase):
    def setUp(self):
        self.items = items_module.load_items(MOCK_PATH)

    def attempt(self, answers):
        attempt = mockexam.new_attempt(self.items, seed=1)
        attempt["answers"] = answers
        return attempt

    def test_perfect_score_passes(self):
        result = mockexam.score_attempt(self.items, self.attempt(KEY))
        self.assertEqual((result["score"], result["total"], result["passed"]), (4, 4, True))
        self.assertEqual(result["missed"], [])

    def test_one_miss_on_four_is_below_the_mark(self):
        answers = dict(KEY, **{"m-3": "A"})
        result = mockexam.score_attempt(self.items, self.attempt(answers))
        self.assertEqual(result["score"], 3)
        self.assertFalse(result["passed"])              # 75% < 85%
        self.assertEqual(result["missed"], [{"unit": "UA.I.C.K4", "item": "m-3"}])

    def test_unanswered_counts_as_wrong_and_tasks_are_broken_out(self):
        result = mockexam.score_attempt(self.items, self.attempt({"m-1": "B"}))
        self.assertEqual(result["score"], 1)
        by_task = {t["task"]: t for t in result["by_task"]}
        self.assertEqual(by_task["B"], {"task": "B", "correct": 1, "total": 2})
        self.assertEqual(by_task["C"]["correct"], 0)

    def test_case_insensitive_comparison(self):
        result = mockexam.score_attempt(self.items, self.attempt({k: v.lower() for k, v in KEY.items()}))
        self.assertEqual(result["score"], 4)


class TestReadiness(unittest.TestCase):
    def mastered_ledger(self):
        led = stub_ledger()
        for index, unit in enumerate(UNITS):
            led.record_attempt(unit, "a%d" % index, 1, True, "t")
            led.record_attempt(unit, "b%d" % index, 1, True, "t")
        return led

    def test_not_ready_until_units_mastered_and_two_passes(self):
        led = stub_ledger()
        r = mockexam.readiness(led, [])
        self.assertFalse(r["ready"])
        self.assertIn("4 units not yet mastered", r["reasons"])
        self.assertIn("0 of 2 passing practice exams", r["reasons"])

    def test_parked_units_block_readiness_separately(self):
        led = self.mastered_ledger()
        led.park("UA.I.D.K1")
        led.attempts = [a for a in led.attempts if a["unit"] != "UA.I.D.K1"]
        r = mockexam.readiness(led, [{"passed": True, "percent": 100}] * 2)
        self.assertFalse(r["ready"])
        self.assertEqual(r["reasons"], ["1 unit set aside after repeated misses"])

    def test_ready_when_everything_is_met(self):
        led = self.mastered_ledger()
        attempts = [{"passed": True, "percent": 90}, {"passed": False, "percent": 70}, {"passed": True, "percent": 95}]
        r = mockexam.readiness(led, attempts)
        self.assertTrue(r["ready"])
        self.assertEqual(r["passes"], 2)
        self.assertEqual(r["best_percent"], 95)


class TestExamFlow(unittest.TestCase):
    def test_full_attempt_scores_records_and_debriefs(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = exam_course(tmp)
            result, seen = sit_exam(course, lambda item: KEY[item])
            self.assertEqual(result["type"], "mock_result")
            self.assertEqual(len(seen), 4)
            self.assertEqual((result["score"], result["passed"]), (4, True))
            self.assertIn("Sample debrief", result["debrief"])
            self.assertEqual(len(course.ledger.mock_attempts), 1)
            # The ledger round-trips the attempt.
            again = ledger_module.Ledger.load(course.paths["ledger"])
            self.assertEqual(again.mock_attempts[0]["score"], 4)
            self.assertTrue(again.mock_attempts[0]["passed"])

    def test_streaming_shows_the_score_first_and_exam_questions_arrive_whole(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = exam_course(tmp)
            events = []
            block = course.handle({"type": "mock_start", "timestamp": "s"}, emit=events.append)
            self.assertEqual(events, [])  # no model call, so nothing streams
            course.handle({"type": "mock_answer", "question_id": block["question_id"], "unit": block["unit"],
                           "selected_option": KEY[block["question_id"]], "timestamp": "t"}, emit=events.append)
            self.assertEqual(events, [])
            result = course.handle({"type": "mock_submit", "timestamp": "t"}, emit=events.append)
            start = events[0]["start"]
            self.assertEqual((start["stage"], start["block"]["score"]), ("mock_gate", result["score"]))
            self.assertNotIn("debrief", start["block"])
            self.assertEqual("".join(e["delta"] for e in events if "delta" in e), result["debrief"])

    def test_exam_questions_never_carry_the_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = exam_course(tmp)
            block = course.handle({"type": "mock_start", "timestamp": "s"})
            self.assertEqual(set(block) & {"answer", "rationale"}, set())
            self.assertTrue(block["mock"])

    def test_early_submit_scores_the_unanswered_as_wrong(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = exam_course(tmp)
            block = course.handle({"type": "mock_start", "timestamp": "s"})
            course.handle({"type": "mock_answer", "question_id": block["question_id"],
                           "unit": block["unit"], "selected_option": KEY[block["question_id"]], "timestamp": "t"})
            result = course.handle({"type": "mock_submit", "timestamp": "t"})
            self.assertEqual(result["type"], "mock_result")
            self.assertEqual(result["score"], 1)
            self.assertFalse(result["passed"])

    def test_the_course_resumes_where_it_was_after_the_exam(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = exam_course(tmp)
            self.assertEqual(course.session.stage, "teach")
            sit_exam(course, lambda item: KEY[item])
            self.assertEqual(course.session.stage, "teach")
            self.assertIsNone(course.session.mock)
            block = course.handle({"type": "advance", "timestamp": "t"})
            self.assertEqual(block["type"], "question")      # the lesson's quiz, as before

    def test_two_passes_show_in_state_and_readiness_still_waits_for_mastery(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = exam_course(tmp)
            sit_exam(course, lambda item: KEY[item])
            sit_exam(course, lambda item: KEY[item])
            state = course.state()
            self.assertEqual(state["readiness"]["passes"], 2)
            self.assertFalse(state["readiness"]["ready"])
            self.assertTrue(state["mock_available"])
            self.assertFalse(state["mock_in_progress"])

    def test_no_items_means_no_exam_not_a_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = make_course(tmp)
            course.handle({"type": "intake", "default_gear": 1, "timestamp": "t"})
            block = course.handle({"type": "mock_start", "timestamp": "s"})
            self.assertEqual(block["type"], "error")
            self.assertFalse(course.state()["mock_available"])


if __name__ == "__main__":
    unittest.main()
