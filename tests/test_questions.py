"""Check questions: the log of questions asked, the course's checks on a
question, and the instructor's guidance and questions.

Run from the course folder:  python3 -m unittest discover -s tests -v
"""

import copy
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import items as items_module         # noqa: E402
from llm_client import _MOCK         # noqa: E402
from test_instructor import scripted  # noqa: E402
from test_phase3 import make_course  # noqa: E402

UNIT = "UA.I.B.K16"
INTAKE = {"type": "intake", "default_gear": 1, "timestamp": "t"}
ADVANCE = {"type": "advance", "timestamp": "t"}
VISIBILITY = [{"fact": "Minimum flight visibility", "answer": "3 statute miles", "source": "S", "link": "L"}]


def sound(**changes):
    """The mock provider's question, which passes every check, with `changes`."""
    return dict(copy.deepcopy(_MOCK["question"]), **changes)


def options(b_text, a_text="Option A", c_text="Option C"):
    return [{"id": "A", "text": a_text}, {"id": "B", "text": b_text}, {"id": "C", "text": c_text}]


QUESTION = {"stem": "Where is prior authorization needed?", "a": "In Class G airspace",
            "b": "In controlled airspace", "c": "Nowhere below 400 feet", "answer": "B",
            "rationale": "Controlled airspace needs it; Class G does not.", "source": "Fixture 107.41",
            "url": "https://example.invalid/fixture/107-41"}


def write_questions(course, questions, guidance=""):
    """The instructor's file for UNIT, with `questions` numbered from 1."""
    numbered = [dict(q, item="%s-i%d" % (UNIT, n), unit=UNIT) for n, q in enumerate(questions, 1)]
    os.makedirs(course.paths["questions"], exist_ok=True)
    with open(course.questions_path(UNIT), "w", encoding="utf-8") as handle:
        handle.write(items_module.questions_text(UNIT, guidance, numbered, len(numbered)))


def counting(course):
    """Record the stage of every model call, prefetches included."""
    stages, complete = [], course.client.complete

    def count(system, user, stage=None, **options):
        stages.append(stage)
        return complete(system, user, stage=stage, **options)

    course.client.complete = count
    return stages


def answer(question, option):
    return {"type": "answer", "question_id": question["question_id"], "unit": question["unit"],
            "selected_option": option, "timestamp": "t"}


def logged(course):
    with open(course.paths["questions_log"], encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


class TestQuestionChecks(unittest.TestCase):
    def test_a_sound_question_has_no_problems(self):
        self.assertEqual(items_module.question_problems(sound()), [])

    def test_three_distinct_options_a_key_among_them_a_stem_and_a_rationale_are_required(self):
        for block, problem in (
            (sound(type="lesson"), "not a question block"),
            (sound(stem=" "), "the stem is empty"),
            (sound(options=options("Option B")[:2]), "exactly three options"),
            (sound(options=options("Option B") + [{"id": "D", "text": "Option D"}]), "exactly three options"),
            (sound(options=[{"id": "A", "text": "x"}, {"id": "C", "text": "y"}, {"id": "B", "text": "z"}]),
             "exactly three options"),
            (sound(options="A, B, C"), "exactly three options"),
            (sound(options=options("")), "an option has no text"),
            (sound(options=options("Option B", c_text="option a.")), "two options say the same thing"),
            (sound(answer="D"), "the answer must be A, B or C"),
            (sound(answer=None), "the answer must be A, B or C"),
            (sound(rationale=""), "the rationale is empty"),
        ):
            problems = items_module.question_problems(block)
            self.assertEqual(len(problems), 1, block)
            self.assertIn(problem, problems[0])

    def test_the_keyed_option_must_state_the_named_fact(self):
        check = items_module.question_problems
        self.assertEqual(check(sound(options=options("At least 3 statute miles."), fact="F1"), VISIBILITY), [])
        # Words, not characters: 13 does not contain 3.
        self.assertIn("does not state the answer of F1, which is: 3 statute miles",
                      check(sound(options=options("13 statute miles"), fact="F1"), VISIBILITY)[0])
        self.assertIn("F9 is not one of the vetted facts", check(sound(fact="F9"), VISIBILITY)[0])
        self.assertIn("F1 is not one of the vetted facts", check(sound(fact="F1"))[0])
        pilot = [{"fact": "Who designates a visual observer", "answer": "the remote pilot in command"}]
        self.assertEqual(check(sound(options=options("Remote pilot in command"), fact="F1"), pilot), [])

    def test_without_a_named_fact_only_the_form_is_checked(self):
        self.assertEqual(items_module.question_problems(sound(options=options("13 statute miles")), VISIBILITY), [])


class TestQuestionsAsked(unittest.TestCase):
    def test_each_question_served_gets_its_own_id_from_the_course(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = make_course(tmp)
            course.handle(INTAKE)
            first = course.handle(ADVANCE)
            course.handle(answer(first, "B"))
            second = course.handle(ADVANCE)
            # The mock provider calls every question "mock-q1".
            self.assertEqual([first["question_id"], second["question_id"]], [UNIT + "-q1", UNIT + "-q2"])

    def test_questions_asked_survive_a_new_session_and_a_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = make_course(tmp)
            course.handle(INTAKE)
            course.handle(ADVANCE)
            record = logged(course)[0]
            self.assertEqual((record["question_id"], record["origin"], record["answer"]), (UNIT + "-q1", "tutor", "B"))

            course.handle(INTAKE)  # a page load starts a new session
            self.assertIn("ALREADY ASKED (ask something different):\n- Sample question from the mock provider.",
                          course.quiz_call(UNIT)["context"])

            restarted = make_course(tmp)
            restarted.handle(INTAKE)
            self.assertEqual(restarted.handle(ADVANCE)["question_id"], UNIT + "-q2")

    def test_two_right_answers_master_a_unit_though_the_model_repeats_its_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = make_course(tmp)
            course.handle(INTAKE)
            for _ in range(2):
                course.handle(answer(course.handle(ADVANCE), "B"))
            self.assertEqual(course.ledger.mastery(UNIT), "mastered")

    def test_a_question_that_fails_the_checks_is_written_once_more_with_the_problems(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = make_course(tmp)
            sent = scripted(course, [sound(answer="D"), sound()])
            question = course.quiz(UNIT)
            self.assertEqual(len(sent), 2)
            self.assertNotIn("DID NOT PASS", sent[0])
            self.assertTrue(sent[1].startswith(sent[0]))
            self.assertIn("YOUR QUESTION DID NOT PASS THE COURSE'S CHECKS: the answer must be A, B or C.", sent[1])
            self.assertEqual(course.calls[0]["error"], "failed checks")
            self.assertEqual((question["type"], question["question_id"]), ("question", UNIT + "-q1"))
            self.assertEqual(len(logged(course)), 1)

    def test_a_question_that_fails_twice_is_an_error_and_is_not_logged(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = make_course(tmp)
            scripted(course, [sound(answer="D"), sound(stem="")])
            block = course.quiz(UNIT)
            self.assertEqual(block["type"], "error")
            self.assertIn("did not pass the course's checks: the stem is empty", block["message"])
            self.assertIsNone(course.session.pending)
            self.assertEqual(course.asked(UNIT), [])

    def test_a_failed_review_question_is_asked_again_on_continue(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = make_course(tmp)
            scripted(course, [sound(answer="D"), sound(answer="D"), sound()])
            course.session.review_queue = ["UA.I.B.K21c"]
            self.assertEqual(course.quiz(UNIT, review=True)["type"], "error")
            question = course.handle(ADVANCE)
            self.assertEqual((question["type"], question["unit"], question.get("review")), ("question", UNIT, True))
            self.assertEqual(course.session.review_queue, ["UA.I.B.K21c"])


class TestInstructorQuestions(unittest.TestCase):
    def test_instructor_questions_come_first_in_file_order_then_the_tutor_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = make_course(tmp)
            write_questions(course, [QUESTION, dict(QUESTION, stem="A second question?", answer="A")])
            stages = counting(course)
            course.handle(INTAKE)
            first = course.handle(ADVANCE)
            course.handle(answer(first, "C"))   # wrong: the unit is taught again
            course.handle(ADVANCE)
            second = course.handle(ADVANCE)
            self.assertNotIn("question", stages)
            course.handle(answer(second, "A"))  # right, not yet mastered: another question
            third = course.handle(ADVANCE)
            self.assertEqual([first["question_id"], second["question_id"], third["question_id"]],
                             [UNIT + "-i1", UNIT + "-i2", UNIT + "-q3"])
            self.assertEqual((first["stem"], second["stem"]), ("Where is prior authorization needed?",
                                                               "A second question?"))
            self.assertIn("question", stages)
            self.assertEqual([q["origin"] for q in logged(course)], ["instructor", "instructor", "tutor"])

    def test_an_instructor_question_is_scored_on_its_key_and_recorded_under_its_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = make_course(tmp)
            write_questions(course, [dict(QUESTION, answer="C")])
            course.handle(INTAKE)
            question = course.handle(ADVANCE)
            self.assertNotIn("answer", question)
            self.assertNotIn("rationale", question)
            self.assertEqual([o["text"] for o in question["options"]],
                             ["In Class G airspace", "In controlled airspace", "Nowhere below 400 feet"])
            feedback = course.handle(answer(question, "C"))
            self.assertEqual((feedback["correct"], feedback["correct_option"]), (True, "C"))
            self.assertEqual(course.ledger.attempts[-1]["item"], UNIT + "-i1")
            self.assertEqual(course.ledger.attempts[-1]["result"], "correct")

    def test_nothing_is_prefetched_while_an_instructor_question_is_due(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = make_course(tmp)
            course.handle(INTAKE)
            self.assertEqual([stage for stage, _ in course.prefetches], ["quiz"])
        with tempfile.TemporaryDirectory() as tmp:
            course = make_course(tmp)
            write_questions(course, [QUESTION])
            course.handle(INTAKE)
            self.assertEqual(course.prefetches, {})

    def test_the_guidance_goes_into_the_quiz_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = make_course(tmp)
            write_questions(course, [], guidance="Make sure the student understands X.\n\n- And Y.")
            self.assertIn("INSTRUCTOR GUIDANCE (what this unit's questions must make sure the student understands; "
                          "it never overrides the vetted facts):\nMake sure the student understands X.\n\n- And Y.",
                          course.quiz_call(UNIT)["context"])
            self.assertNotIn("INSTRUCTOR GUIDANCE", course.quiz_call("UA.I.B.K21c")["context"])

    def test_saved_questions_read_back_with_multi_line_guidance(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = make_course(tmp)
            write_questions(course, [QUESTION, dict(QUESTION, stem="Second?")], guidance="First line.\n\nSecond line.")
            found = items_module.load_questions(course.questions_path(UNIT))
            self.assertEqual(found["guidance"], "First line.\n\nSecond line.")
            self.assertEqual(found["last"], 2)
            self.assertEqual(found["items"][0], dict(QUESTION, item=UNIT + "-i1", unit=UNIT))
            self.assertEqual([i["stem"] for i in found["items"]], ["Where is prior authorization needed?", "Second?"])

    def test_a_missing_questions_file_reads_as_empty(self):
        self.assertEqual(items_module.load_questions("/nonexistent/UA.I.B.K16.md"),
                         {"guidance": "", "items": [], "last": 0})

    def test_a_save_assigns_new_ids_and_never_reuses_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = make_course(tmp)
            saved = course.author_questions_save(UNIT, "", [QUESTION, dict(QUESTION, stem="Second?")])
            self.assertTrue(saved["saved"])
            self.assertEqual([i["item"] for i in saved["items"]], [UNIT + "-i1", UNIT + "-i2"])
            # Delete the second; a question added later does not take its id.
            course.author_questions_save(UNIT, "", saved["items"][:1])
            saved = course.author_questions_save(UNIT, "", saved["items"][:1] + [dict(QUESTION, stem="Third?")])
            self.assertEqual([i["item"] for i in saved["items"]], [UNIT + "-i1", UNIT + "-i3"])
            # An id the file does not hold is not taken from the page.
            saved = course.author_questions_save(UNIT, "", [dict(QUESTION, item="m-a1")])
            self.assertEqual([i["item"] for i in saved["items"]], [UNIT + "-i4"])

    def test_a_save_with_a_problem_writes_nothing_and_names_the_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = make_course(tmp)
            course.author_questions_save(UNIT, "Keep this.", [QUESTION])
            with open(course.questions_path(UNIT), encoding="utf-8") as handle:
                before = handle.read()
            refused = course.author_questions_save(UNIT, "Line one.\n## Not a heading", [
                dict(QUESTION, stem="Is A | B allowed?"),
                dict(QUESTION, c="in controlled  airspace"),
                dict(QUESTION, answer="D"),
                dict(QUESTION, url="example.invalid/107-41", source=""),
                QUESTION,
            ])
            self.assertEqual(refused["error"], "Nothing was saved. Fix these first.")
            self.assertEqual(refused["problems"], [
                "Guidance: a line cannot start with ## because it would end the guidance.",
                "Question 1: the | character cannot be used",
                "Question 2: two options say the same thing",
                "Question 3: the answer must be A, B or C",
                "Question 4: there is no source",
                "Question 4: the link is not an http link",
            ])
            with open(course.questions_path(UNIT), encoding="utf-8") as handle:
                self.assertEqual(handle.read(), before)

    def test_instructor_questions_never_join_the_practice_exam(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = make_course(tmp)
            write_questions(course, [QUESTION])
            course.handle(INTAKE)
            course.handle(ADVANCE)
            self.assertNotIn(UNIT + "-i1", course.items)


if __name__ == "__main__":
    unittest.main()
