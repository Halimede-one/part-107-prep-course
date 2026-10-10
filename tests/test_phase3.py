"""Phase 3 tests: the orchestrator's routing, prompt assembly, and the loop.

Run from the course folder:  python3 -m unittest discover -s tests -v
"""

import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(ROOT, "tests", "fixtures")
sys.path.insert(0, ROOT)

import items as items_module      # noqa: E402
import ledger as ledger_module    # noqa: E402
import orchestrator               # noqa: E402
import retrieval                  # noqa: E402
import server as server_module    # noqa: E402
from llm_client import LLMClient  # noqa: E402

STUB_OBJECTIVES = os.path.join(FIXTURES, "objectives-stub.md")
STUB_CURRICULUM = os.path.join(FIXTURES, "curriculum")
UNITS = ["UA.I.B.K16", "UA.I.B.K21c", "UA.I.C.K4", "UA.I.D.K1"]


def stub_paths(tmp):
    return {
        "objectives": STUB_OBJECTIVES,
        "curriculum": STUB_CURRICULUM,
        "knowledge_base": os.path.join(FIXTURES, "kb"),
        "items": os.path.join(FIXTURES, "items.md"),
        "reference": os.path.join(FIXTURES, "facts-stub.md"),
        "prompts": os.path.join(ROOT, "prompts"),
        "ledger": os.path.join(tmp, "ledger.md"),
        "responses": os.path.join(tmp, "responses.jsonl"),
    }


def stub_ledger(default_gear=1):
    return ledger_module.Ledger.bootstrap(STUB_OBJECTIVES, default_gear=default_gear)


def make_course(tmp):
    """A Course wired to the stub area and the mock provider."""
    paths = stub_paths(tmp)
    config = {
        "provider": "mock",
        "providers": {"mock": {"supports_web_search": False}},
        "paths": paths,
        "area": "Stub",
    }
    course = server_module.Course.__new__(server_module.Course)
    course.config = config
    course.paths = paths
    course.client = LLMClient(config)
    course.items = items_module.load_items(paths["items"])
    course.chunks = retrieval.load_chunks(paths["knowledge_base"])
    course.tutor = orchestrator.Orchestrator(paths)
    course.ledger = ledger_module.Ledger.open_or_bootstrap(paths["ledger"], paths["objectives"])
    course.session = server_module.Session()
    course.calls = []
    course.chat, course.chat_meta = [], {}
    return course


class TestVettedContentLoading(unittest.TestCase):
    def test_objectives_carry_their_text(self):
        objectives = orchestrator.load_objectives(STUB_OBJECTIVES)
        self.assertEqual(len(objectives), 4)
        self.assertIn("visibility", objectives["UA.I.B.K21c"].lower())

    def test_content_sources_are_parsed(self):
        with tempfile.TemporaryDirectory() as tmp:
            tutor = orchestrator.Orchestrator(stub_paths(tmp))
            content = tutor.content("UA.I.B.K16", 2)
            self.assertEqual(content["sources"][0]["source"], "Fixture 107.41")
            self.assertTrue(content["sources"][0]["url"].startswith("https://"))
            self.assertIn("controlled airspace", content["body"])

    def test_gear_three_loads_its_own_scaffolding(self):
        with tempfile.TemporaryDirectory() as tmp:
            tutor = orchestrator.Orchestrator(stub_paths(tmp))
            self.assertIn("Step one", tutor.content("UA.I.B.K16", 3)["body"])
            self.assertIsNone(tutor.content("UA.I.B.K21c", 3))

    def test_facts_are_grouped_by_unit(self):
        with tempfile.TemporaryDirectory() as tmp:
            facts = orchestrator.Orchestrator(stub_paths(tmp)).facts
            self.assertEqual(facts["UA.I.B.K21c"][0]["answer"], "3 statute miles")


class TestRouting(unittest.TestCase):
    def test_current_unit_is_the_first_unmastered(self):
        led = stub_ledger()
        self.assertEqual(orchestrator.current_unit(led), "UA.I.B.K16")
        led.record_attempt("UA.I.B.K16", "a", 1, True, "t1")
        led.record_attempt("UA.I.B.K16", "b", 1, True, "t2")
        self.assertEqual(orchestrator.current_unit(led), "UA.I.B.K21c")

    def test_all_mastered_returns_none(self):
        led = stub_ledger()
        for index, unit in enumerate(UNITS):
            led.record_attempt(unit, "a%d" % index, 1, True, "t")
            led.record_attempt(unit, "b%d" % index, 1, True, "t")
        self.assertIsNone(orchestrator.current_unit(led))

    def test_correct_but_not_mastered_asks_again(self):
        led = stub_ledger()
        led.record_attempt("UA.I.B.K16", "a", 1, True, "t")
        self.assertEqual(orchestrator.decide_after_answer(led, "UA.I.B.K16", [1, 2, 3], True), ("quiz", 1))

    def test_mastery_advances(self):
        led = stub_ledger()
        led.record_attempt("UA.I.B.K16", "a", 1, True, "t")
        led.record_attempt("UA.I.B.K16", "b", 1, True, "t")
        self.assertEqual(orchestrator.decide_after_answer(led, "UA.I.B.K16", [1, 2, 3], True)[0], "advance")

    def test_a_miss_downshifts_one_gear(self):
        led = stub_ledger()
        led.record_attempt("UA.I.B.K16", "a", 1, False, "t")
        self.assertEqual(orchestrator.decide_after_answer(led, "UA.I.B.K16", [1, 2, 3], False), ("remediate", 2))

    def test_downshift_stops_at_the_deepest_available_gear(self):
        led = stub_ledger()
        led.record_attempt("UA.I.B.K21c", "a", 2, False, "t")
        self.assertEqual(orchestrator.decide_after_answer(led, "UA.I.B.K21c", [1, 2], False), ("remediate", 2))

    def test_terminal_gear_parks_after_repeated_misses(self):
        led = stub_ledger()
        led.record_attempt("UA.I.B.K21c", "a", 2, False, "t")
        led.record_attempt("UA.I.B.K21c", "b", 2, False, "t")
        self.assertEqual(orchestrator.decide_after_answer(led, "UA.I.B.K21c", [1, 2], False), ("park", 2))

    def test_a_correct_answer_resets_the_terminal_count(self):
        led = stub_ledger()
        led.record_attempt("UA.I.B.K21c", "a", 2, False, "t")
        led.record_attempt("UA.I.B.K21c", "b", 2, True, "t")
        led.record_attempt("UA.I.B.K21c", "c", 2, False, "t")
        self.assertEqual(orchestrator.terminal_cycles(led, "UA.I.B.K21c", 2), 1)


class TestPromptAssembly(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.tutor = orchestrator.Orchestrator(stub_paths(self.tmp))

    def test_system_prompt_combines_global_rules_and_stage(self):
        system = self.tutor.system("quiz")
        self.assertIn("Absolute rules", system)
        self.assertIn("Stage: quiz", system)

    def test_teach_context_carries_unit_objective_gear_and_sources(self):
        content = self.tutor.content("UA.I.B.K16", 2)
        context = self.tutor.teach_context("UA.I.B.K16", 2, content)
        self.assertIn("UNIT: UA.I.B.K16", context)
        self.assertIn("GEAR: 2 (Guided)", context)
        self.assertIn("prior authorization", context.lower())
        self.assertIn("https://example.invalid/fixture/107-41", context)

    def test_quiz_context_supplies_the_ground_truth_and_avoids_repeats(self):
        content = self.tutor.content("UA.I.B.K21c", 1)
        context = self.tutor.quiz_context("UA.I.B.K21c", 1, content, ["k21c-a1"])
        self.assertIn("VETTED FACTS", context)
        self.assertIn("3 statute miles", context)
        self.assertIn("k21c-a1", context)

    def test_remediate_context_reports_the_misconception_and_returning_state(self):
        content = self.tutor.content("UA.I.B.K16", 3)
        context = self.tutor.remediate_context("UA.I.B.K16", 3, content, "they chose A", returning=True)
        self.assertIn("GEAR: 3 (Foundational)", context)
        self.assertIn("they chose A", context)
        self.assertIn("set aside earlier", context)

    def test_qa_context_reports_an_empty_corpus_honestly(self):
        context = self.tutor.qa_context("what is photosynthesis", [], can_search=False)
        self.assertIn("none", context)
        self.assertIn("WEB SEARCH AVAILABLE: no", context)


class TestLoop(unittest.TestCase):
    """A dry run of the whole loop over the three-unit stub."""

    def test_intake_then_teach_then_quiz(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = make_course(tmp)
            lesson = course.handle({"type": "intake", "default_gear": 1, "timestamp": "t"})
            self.assertEqual(lesson["type"], "lesson")
            question = course.handle({"type": "advance", "timestamp": "t"})
            self.assertEqual(question["type"], "question")

    def test_the_answer_key_never_reaches_the_client(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = make_course(tmp)
            course.handle({"type": "intake", "default_gear": 1, "timestamp": "t"})
            question = course.handle({"type": "advance", "timestamp": "t"})
            self.assertNotIn("answer", question)
            self.assertNotIn("rationale", question)
            self.assertEqual(course.session.pending["answer"], "B")

    def test_a_wrong_answer_downshifts_that_unit_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = make_course(tmp)
            course.handle({"type": "intake", "default_gear": 1, "timestamp": "t"})
            course.handle({"type": "advance", "timestamp": "t"})
            feedback = course.handle({
                "type": "answer", "question_id": "mock-q1", "unit": "UA.I.B.K16",
                "selected_option": "A", "timestamp": "t",
            })
            self.assertFalse(feedback["correct"])
            self.assertEqual(feedback["correct_option"], "B")

            course.handle({"type": "advance", "timestamp": "t"})
            state = course.state()
            k16 = next(u for u in state["units"] if u["id"] == "UA.I.B.K16")
            other = next(u for u in state["units"] if u["id"] == "UA.I.B.K21c")
            self.assertEqual(k16["current_gear"], 2)
            self.assertEqual(k16["gears_taken"], [1, 2])
            self.assertEqual(other["current_gear"], 1)

    def test_two_correct_answers_advance_to_the_next_unit(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = make_course(tmp)
            course.handle({"type": "intake", "default_gear": 1, "timestamp": "t"})
            for index in range(2):
                course.handle({"type": "advance", "timestamp": "t"})
                course.handle({
                    "type": "answer", "question_id": "q%d" % index, "unit": "UA.I.B.K16",
                    "selected_option": "B", "timestamp": "t",
                })
            course.handle({"type": "advance", "timestamp": "t"})
            self.assertEqual(orchestrator.current_unit(course.ledger), "UA.I.B.K21c")

    def test_repeated_misses_at_the_deepest_gear_park_the_unit_and_move_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = make_course(tmp)
            course.handle({"type": "intake", "default_gear": 3, "timestamp": "t"})
            for index in range(2):
                course.handle({"type": "advance", "timestamp": "t"})
                course.handle({
                    "type": "answer", "question_id": "q%d" % index, "unit": "UA.I.B.K16",
                    "selected_option": "A", "timestamp": "t",
                })
            k16 = next(u for u in course.state()["units"] if u["id"] == "UA.I.B.K16")
            self.assertTrue(k16["parked"])
            self.assertTrue(k16["needs_attention"])
            # The course moves on to the next unit rather than cycling forever.
            block = course.handle({"type": "advance", "timestamp": "t"})
            self.assertEqual(block["type"], "lesson")
            self.assertEqual(orchestrator.current_unit(course.ledger), "UA.I.B.K21c")

    def test_it_refuses_to_teach_a_unit_with_no_vetted_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = make_course(tmp)
            # Master the two units that have content, so the unauthored one is current.
            for unit in ("UA.I.B.K16", "UA.I.B.K21c"):
                course.ledger.record_attempt(unit, "a", 1, True, "t")
                course.ledger.record_attempt(unit, "b", 1, True, "t")
            live = os.path.join(STUB_CURRICULUM, "UA.I.C.K4.md")
            hidden = live + ".hidden"
            os.rename(live, hidden)
            try:
                block = course.teach()
            finally:
                os.rename(hidden, live)
            self.assertEqual(block["type"], "error")
            self.assertIn("no vetted content", block["message"].lower())

    def test_streaming_a_lesson_a_question_and_feedback(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = make_course(tmp)
            events = []

            def streamed(field):
                return "".join(e["delta"] for e in events if e.get("field") == field)

            lesson = course.handle({"type": "intake", "default_gear": 1, "timestamp": "t"}, emit=events.append)
            start = events[0]["start"]
            self.assertEqual((start["stage"], start["status"], start["model"]), ("teach", "Writing your lesson", "mock"))
            self.assertEqual((start["block"]["unit"], start["block"]["gear"]), (course.ledger.current_unit, 1))
            self.assertEqual((streamed("title"), streamed("body")), (lesson["title"], lesson["body"]))

            # The question streams its stem only: the key and the rationale stay on the server.
            events.clear()
            question = course.handle({"type": "advance", "timestamp": "t"}, emit=events.append)
            self.assertEqual({e["field"] for e in events if "delta" in e}, {"stem"})
            self.assertEqual(streamed("stem"), question["stem"])
            self.assertIn({"status": "Writing the answer options"}, events)
            sent = json.dumps(events)
            self.assertNotIn(course.session.pending["rationale"], sent)
            self.assertNotIn('"answer"', sent)

            # Right or wrong is known before the tutor explains, so it leads.
            events.clear()
            feedback = course.handle({
                "type": "answer", "question_id": question["question_id"], "unit": question["unit"],
                "selected_option": "A", "timestamp": "t",
            }, emit=events.append)
            self.assertEqual(events[0]["start"]["block"]["correct"], False)
            self.assertEqual(events[0]["start"]["block"]["correct_option"], "B")
            self.assertEqual(streamed("message"), feedback["message"])

    def test_free_form_questions_still_work_mid_loop(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = make_course(tmp)
            course.handle({"type": "intake", "default_gear": 1, "timestamp": "t"})
            answer = course.handle({
                "type": "question", "text": "night anti-collision lighting", "timestamp": "t",
            })
            self.assertEqual(answer["type"], "cited_answer")
            self.assertTrue(answer["in_corpus"])

    def test_completing_the_area_does_not_declare_exam_readiness(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = make_course(tmp)
            for index, unit in enumerate(UNITS):
                course.ledger.record_attempt(unit, "a%d" % index, 1, True, "t")
                course.ledger.record_attempt(unit, "b%d" % index, 1, True, "t")
            block = course.teach()
            self.assertIn("mastered", block["title"].lower())
            self.assertIn("readiness", block["body"].lower() + block["title"].lower())


if __name__ == "__main__":
    unittest.main()


def master(course, unit, prefix):
    """Drive two correct answers through the live loop for the current unit."""
    for index in range(2):
        block = course.handle({"type": "advance", "timestamp": "t"})
        assert block["type"] == "question", (unit, block)
        course.handle({
            "type": "answer", "question_id": "%s-%d" % (prefix, index), "unit": unit,
            "selected_option": "B", "timestamp": "t",
        })
        if index == 0:
            assert orchestrator.current_unit(course.ledger) == unit


class TestBoundariesAndReview(unittest.TestCase):
    """The stub area is B.K16, B.K21c, C.K4, D.K1: boundaries at B->C, C->D, D->END."""

    def start(self, tmp, gear=1):
        course = make_course(tmp)
        course.handle({"type": "intake", "default_gear": gear, "timestamp": "t"})
        return course

    def test_no_review_fires_while_nothing_from_another_task_is_mastered(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = self.start(tmp)
            master(course, "UA.I.B.K16", "a")
            course.handle({"type": "advance", "timestamp": "t"})      # teach K21c
            master(course, "UA.I.B.K21c", "b")
            block = course.handle({"type": "advance", "timestamp": "t"})
            # B->C boundary: the only mastered units are in B, so no review, straight to C.
            self.assertEqual(block["type"], "lesson")
            self.assertEqual(orchestrator.current_unit(course.ledger), "UA.I.C.K4")
            self.assertEqual(course.ledger.last_task, "C")

    def test_review_fires_at_the_next_boundary_and_a_pass_keeps_mastery(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = self.start(tmp)
            master(course, "UA.I.B.K16", "a")
            course.handle({"type": "advance", "timestamp": "t"})
            master(course, "UA.I.B.K21c", "b")
            course.handle({"type": "advance", "timestamp": "t"})      # teach C.K4
            master(course, "UA.I.C.K4", "c")
            block = course.handle({"type": "advance", "timestamp": "t"})
            # C->D boundary: K16 and K21c are mastered and outside C, so review fires.
            self.assertEqual(block["type"], "question")
            self.assertTrue(block.get("review"))
            self.assertEqual(block["unit"], "UA.I.B.K16")   # least recently attempted first
            self.assertEqual(course.ledger.last_task, "D")

            course.handle({"type": "answer", "question_id": "r1", "unit": "UA.I.B.K16",
                           "selected_option": "B", "timestamp": "t"})
            self.assertEqual(course.ledger.mastery("UA.I.B.K16"), "mastered")
            block = course.handle({"type": "advance", "timestamp": "t"})
            self.assertTrue(block.get("review"))
            self.assertEqual(block["unit"], "UA.I.B.K21c")

    def test_a_review_miss_demotes_to_gear_two_and_returns_the_unit(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = self.start(tmp)
            master(course, "UA.I.B.K16", "a")
            course.handle({"type": "advance", "timestamp": "t"})
            master(course, "UA.I.B.K21c", "b")
            course.handle({"type": "advance", "timestamp": "t"})
            master(course, "UA.I.C.K4", "c")
            course.handle({"type": "advance", "timestamp": "t"})      # review K16
            feedback = course.handle({"type": "answer", "question_id": "r1", "unit": "UA.I.B.K16",
                                      "selected_option": "A", "timestamp": "t"})
            self.assertFalse(feedback["correct"])
            self.assertEqual(course.ledger.mastery("UA.I.B.K16"), "learning")
            self.assertEqual(course.ledger.units["UA.I.B.K16"]["current_gear"], 2)

            course.handle({"type": "advance", "timestamp": "t"})      # review K21c
            course.handle({"type": "answer", "question_id": "r2", "unit": "UA.I.B.K21c",
                           "selected_option": "B", "timestamp": "t"})
            block = course.handle({"type": "advance", "timestamp": "t"})
            # Queue drained; the demoted unit is current again and is re-taught, not D.K1.
            self.assertEqual(block["type"], "lesson")
            self.assertEqual(orchestrator.current_unit(course.ledger), "UA.I.B.K16")
            # The backward move must not fire another boundary.
            self.assertEqual(course.ledger.last_task, "D")

    def test_parked_units_return_at_the_next_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = self.start(tmp, gear=3)
            for index in range(2):                                   # park K16 at gear 3
                course.handle({"type": "advance", "timestamp": "t"})
                course.handle({"type": "answer", "question_id": "p%d" % index, "unit": "UA.I.B.K16",
                               "selected_option": "A", "timestamp": "t"})
            self.assertTrue(course.ledger.units["UA.I.B.K16"]["parked"])
            course.handle({"type": "advance", "timestamp": "t"})      # teach K21c
            master(course, "UA.I.B.K21c", "b")
            block = course.handle({"type": "advance", "timestamp": "t"})
            # B->C boundary unparks K16; it is current again, taught with the returning framing.
            self.assertEqual(block["type"], "lesson")
            self.assertFalse(course.ledger.units["UA.I.B.K16"]["parked"])
            self.assertEqual(orchestrator.current_unit(course.ledger), "UA.I.B.K16")
            self.assertEqual(course.ledger.last_task, "C")

    def test_end_of_area_with_parked_units_offers_retry_and_without_them_points_to_the_mock(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = self.start(tmp)
            for unit in UNITS:
                course.ledger.record_attempt(unit, unit + "a", 1, True, "t")
                course.ledger.record_attempt(unit, unit + "b", 1, True, "t")
            course.ledger.park("UA.I.D.K1")
            course.ledger.attempts = [a for a in course.ledger.attempts if a["unit"] != "UA.I.D.K1"]
            course.ledger.last_task = "END"
            course.session.stage = None                               # between units
            block = course.handle({"type": "advance", "timestamp": "t"})
            self.assertIn("set aside", block["title"])
            self.assertIn("UA.I.D.K1", block["body"])
            # Continue from the done screen retries the parked unit.
            block = course.handle({"type": "advance", "timestamp": "t"})
            self.assertEqual(block["type"], "lesson")
            self.assertFalse(course.ledger.units["UA.I.D.K1"]["parked"])

            course.ledger.record_attempt("UA.I.D.K1", "x", 3, True, "t")
            course.ledger.record_attempt("UA.I.D.K1", "y", 3, True, "t")
            block = course.handle({"type": "advance", "timestamp": "t"})
            self.assertIn("practice exam", block["body"].lower())

    def test_ledger_round_trips_park_and_last_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "l.md")
            led = stub_ledger()
            led.park("UA.I.B.K21c")
            led.last_task = "C"
            led.save(path)
            again = ledger_module.Ledger.load(path)
            self.assertTrue(again.units["UA.I.B.K21c"]["parked"])
            self.assertEqual(again.last_task, "C")
            self.assertEqual(again.parked_units(), ["UA.I.B.K21c"])
