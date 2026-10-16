"""Foundational for every unit: the file each gear uses, tutor drafts, and STATUS.md.

Run from the course folder:  python3 -m unittest discover -s tests -v
"""

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import orchestrator                  # noqa: E402
import server as server_module       # noqa: E402
import status                        # noqa: E402
from test_phase3 import make_course  # noqa: E402

UNIT = "UA.I.B.K21c"  # a stub unit with a Guided lesson and no other file


def write(course, unit, gear, text):
    with open(orchestrator.lesson_path(course.paths["curriculum"], unit, gear), "w", encoding="utf-8") as handle:
        handle.write(text)


def read(course, unit, gear):
    with open(orchestrator.lesson_path(course.paths["curriculum"], unit, gear), encoding="utf-8") as handle:
        return handle.read()


DRAFT = ("---\nsource: Fixture 107.51 | https://example.invalid/fixture/107-51\nversion: 1\n"
         "draft: written by the tutor on 2026-10-16 from the Guided lesson; no instructor has reviewed it\n---\n"
         "Objective: minimum visibility.\n\nStep 1, the draft's own picture.\n")


class TestWhichFileEachGearUses(unittest.TestCase):
    def test_without_files_fast_track_and_foundational_are_built_from_guided(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = make_course(tmp)
            for gear in (1, 3):
                content = course.tutor.content(UNIT, gear)
                self.assertEqual((content["form"], content["gear"]), ("derived", gear))
                message = course.tutor.teach_context(UNIT, gear, content)
                self.assertIn("no %s version is written for this unit" % orchestrator.GEAR_NAMES[gear], message)
            self.assertEqual(course.tutor.content(UNIT, 2)["form"], "written")
            self.assertEqual(course.gears_for(UNIT), [1, 2, 3])

    def test_a_unit_file_wins_for_fast_track_and_foundational(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = make_course(tmp)
            write(course, UNIT, 1, "---\nsource: S | https://example.invalid/s\nversion: 2\n---\nThe short form.\n")
            content = course.tutor.content(UNIT, 1)
            self.assertEqual((content["form"], content["body"], content["version"]), ("written", "The short form.", 2))
            self.assertNotIn("no Fast-track version", course.tutor.teach_context(UNIT, 1, content))

    def test_a_draft_comes_with_the_guided_lesson_as_ground_truth(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = make_course(tmp)
            write(course, UNIT, 3, DRAFT)
            content = course.tutor.content(UNIT, 3)
            self.assertEqual(content["form"], "draft")
            message = course.tutor.teach_context(UNIT, 3, content)
            self.assertIn("FOUNDATIONAL DRAFT", message)
            self.assertIn("Step 1, the draft's own picture.", message)
            self.assertIn("THE GUIDED LESSON", message)
            self.assertIn(course.tutor.content(UNIT, 2)["body"], message)

    def test_the_version_and_the_draft_mark_never_reach_the_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = make_course(tmp)
            write(course, UNIT, 3, DRAFT)
            message = course.tutor.teach_context(UNIT, 3, course.tutor.content(UNIT, 3))
            self.assertNotIn("version: 1", message)
            self.assertNotIn("on 2026-10-16", message)  # the header's draft line, not the label

    def test_the_state_reports_each_gears_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = make_course(tmp)
            write(course, UNIT, 3, DRAFT)
            unit = next(u for u in course.state()["units"] if u["id"] == UNIT)
            self.assertEqual(unit["available_gears"], [1, 2, 3])
            self.assertIsNone(unit["gear_files"]["1"])
            self.assertEqual(unit["gear_files"]["2"], {"version": None, "draft": False})
            self.assertEqual(unit["gear_files"]["3"], {"version": 1, "draft": True})


class TestDrafts(unittest.TestCase):
    def test_a_lesson_picked_at_foundational_is_saved_as_the_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = make_course(tmp)
            course.handle({"type": "intake", "default_gear": 1, "timestamp": "t"})
            lesson = course.handle({"type": "goto", "unit": UNIT, "gear": 3, "timestamp": "t"})
            saved = orchestrator.parse_content(read(course, UNIT, 3))
            self.assertEqual(saved["version"], 1)
            self.assertIn("written by the tutor", saved["draft"])
            self.assertEqual([s["url"] for s in saved["sources"]], [c["url"] for c in lesson["citations"]])
            self.assertTrue(saved["body"].startswith("Objective: "))
            self.assertIn(lesson["body"], saved["body"])
            self.assertEqual(course.tutor.content(UNIT, 3)["form"], "draft")

    def test_an_existing_file_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = make_course(tmp)
            write(course, UNIT, 3, DRAFT)
            course.save_draft(UNIT, {"type": "lesson", "body": "Another lesson.", "citations": []})
            self.assertEqual(read(course, UNIT, 3), DRAFT)

    def test_a_re_teach_at_foundational_writes_a_general_draft_in_the_background(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = make_course(tmp)
            course.handle({"type": "goto", "unit": UNIT, "gear": 2, "timestamp": "t"})
            question = course.handle({"type": "advance", "timestamp": "t"})
            course.handle({"type": "answer", "question_id": question["question_id"], "unit": UNIT,
                           "selected_option": "A", "timestamp": "t"})
            again = course.handle({"type": "advance", "timestamp": "t"})
            self.assertEqual((again["type"], course.ledger.units[UNIT]["current_gear"]), ("lesson", 3))
            server_module.wait_for_drafts()
            saved = orchestrator.parse_content(read(course, UNIT, 3))
            self.assertEqual(saved["version"], 1)
            self.assertTrue(saved["draft"])

    def test_a_miss_at_guided_goes_to_foundational_then_two_misses_set_the_unit_aside(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = make_course(tmp)
            course.handle({"type": "goto", "unit": UNIT, "gear": 2, "timestamp": "t"})
            gears = []
            for index in range(3):
                question = course.handle({"type": "advance", "timestamp": "t"})
                if question["type"] == "lesson":  # the re-teach comes first
                    question = course.handle({"type": "advance", "timestamp": "t"})
                gears.append(course.ledger.units[UNIT]["current_gear"])
                course.handle({"type": "answer", "question_id": "m%d" % index, "unit": UNIT,
                               "selected_option": "A", "timestamp": "t"})
            server_module.wait_for_drafts()
            self.assertEqual(gears, [2, 3, 3])
            self.assertTrue(course.ledger.units[UNIT]["parked"])


class TestStatusRow(unittest.TestCase):
    TABLE = ("# Content status\n\n| Unit | Gear 1 | Gear 2 | Gear 3 | Reference facts | Status | Notes |\n"
             "|---|---|---|---|---|---|---|\n| UA.I.A.K1 | | drafted | | drafted | draft | First note. |\n\n"
             "Text after the table.\n")

    def test_one_cell_the_status_and_a_dated_note_change_and_nothing_else(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "STATUS.md")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(self.TABLE)
            status.record(path, "UA.I.A.K1", 3, "v2 vetted", status="vetted", note="Added a diagram | and a step.")
            row = status.row(path, "UA.I.A.K1")
            self.assertEqual((row["gear 3"], row["status"], row["gear 2"]), ("v2 vetted", "vetted", "drafted"))
            self.assertTrue(row["notes"].startswith("First note. 20"))
            self.assertIn("Added a diagram / and a step.", row["notes"])
            with open(path, encoding="utf-8") as handle:
                self.assertTrue(handle.read().endswith("Text after the table.\n"))

    def test_a_unit_without_a_row_gets_one_at_the_end_of_the_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "STATUS.md")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(self.TABLE)
            status.record(path, "UA.I.B.K1", 3, "tutor draft v1")
            self.assertEqual(status.row(path, "UA.I.B.K1")["gear 3"], "tutor draft v1")
            with open(path, encoding="utf-8") as handle:
                lines = handle.read().splitlines()
            self.assertEqual(lines.index("Text after the table.") - 2, lines.index(
                next(line for line in lines if line.startswith("| UA.I.B.K1"))))

    def test_a_missing_file_is_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "STATUS.md")
            status.record(path, "UA.I.A.K1", 3, "tutor draft v1")
            self.assertFalse(os.path.exists(path))


if __name__ == "__main__":
    unittest.main()
