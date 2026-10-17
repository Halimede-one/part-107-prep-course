"""Unit numbers: the chapter.lesson label people use in place of an ACS code.

Run from the course folder:  python3 -m unittest discover -s tests -v
"""

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import ledger as ledger_module      # noqa: E402
import orchestrator                 # noqa: E402
from test_phase3 import stub_paths  # noqa: E402

OBJECTIVES = os.path.join(ROOT, "curriculum", "regulations", "objectives.md")


class TestUnitNumbers(unittest.TestCase):
    def test_the_chapter_is_the_task_and_the_lesson_is_the_k_number(self):
        for code, number in [("UA.I.A.K1", "1.1"), ("UA.I.A.K5", "1.5"), ("UA.I.B.K16", "2.16"),
                             ("UA.I.B.K21a", "2.21a"), ("UA.I.E.K3c", "5.3c"), ("UA.I.F.K7", "6.7")]:
            self.assertEqual(orchestrator.number_of(code), number)

    def test_the_label_puts_the_number_before_the_code(self):
        self.assertEqual(orchestrator.label_of("UA.I.A.K5"), "1.5 (UA.I.A.K5)")

    def test_every_course_unit_has_its_own_number(self):
        units = ledger_module.load_units(OBJECTIVES)
        self.assertEqual(len(units), 77)
        self.assertEqual(len({orchestrator.number_of(u) for u in units}), 77)

    def test_the_mock_debrief_names_missed_units_by_label(self):
        result = {"score": 3, "total": 4, "percent": 75, "pass_mark": 85, "passed": False,
                  "by_task": [], "missed": [{"unit": "UA.I.B.K16"}]}
        ready = {"ready": False, "reasons": [], "passes": 0, "passes_needed": 2}
        with tempfile.TemporaryDirectory() as tmp:
            context = orchestrator.Orchestrator(stub_paths(tmp)).mock_gate_context(result, ready)
        self.assertIn("- 2.16 (UA.I.B.K16): Prior authorization required", context)


if __name__ == "__main__":
    unittest.main()
