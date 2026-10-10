"""Tests for tools/check_integrity.py and tools/package.py.

Run from the course folder:  python3 -m unittest discover -s tests -v
"""

import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import check_integrity   # noqa: E402
import package           # noqa: E402

GOOD_CONTENT = """---
source: Fixture 107.41 | https://example.invalid/fixture/107-41
---
Fixture teaching content with enough words in the body to pass the length check
that the integrity script applies to every content file it finds in the folder.
"""

GOOD_KB = """---
source: Fixture Source
section: § 107.41 Fixture
url: https://example.invalid/fixture
kind: source
---
Fixture chunk text.
"""


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


class Fixture:
    """A small, complete course layout: two units in one task, all checks green."""

    def __init__(self, tmp):
        self.tmp = tmp
        write(os.path.join(tmp, "objectives.md"),
              "| Code | Knowledge element |\n|---|---|\n| UA.I.B.K16 | Airspace. |\n| UA.I.B.K21 | Limits. |\n| UA.I.B.K21c | c. Visibility. |\n")
        write(os.path.join(tmp, "curriculum", "UA.I.B.K16.md"), GOOD_CONTENT)
        write(os.path.join(tmp, "curriculum", "UA.I.B.K21c.md"), GOOD_CONTENT)   # K21 is a grouping parent
        write(os.path.join(tmp, "facts.md"),
              "| Unit | Fact | Answer | Source | Link |\n|---|---|---|---|---|\n"
              "| UA.I.B.K16 | Controlled airspace needs | prior authorization | F | https://example.invalid/f |\n"
              "| UA.I.B.K21c | Minimum visibility | 3 statute miles | F | https://example.invalid/f |\n")
        write(os.path.join(tmp, "mock.md"),
              "| Item | Unit | Stem | A | B | C | Answer | Rationale | Source | Link |\n|---|---|---|---|---|---|---|---|---|---|\n"
              "| m-1 | UA.I.B.K16 | Stem? | x | y | z | B | Why. | F | https://example.invalid/f |\n"
              "| m-2 | UA.I.B.K21c | Stem? | x | y | z | A | Why. | F | https://example.invalid/f |\n")
        write(os.path.join(tmp, "kb", "src-107-41.md"), GOOD_KB)
        for name in check_integrity.STAGE_PROMPTS:
            write(os.path.join(tmp, "prompts", name + ".md"), "# stage\n")
        self.config = os.path.join(tmp, "config.json")
        self.write_config()

    def write_config(self):
        with open(self.config, "w", encoding="utf-8") as handle:
            json.dump({"paths": {
                "objectives": os.path.join(self.tmp, "objectives.md"),
                "curriculum": os.path.join(self.tmp, "curriculum"),
                "reference": os.path.join(self.tmp, "facts.md"),
                "items": os.path.join(self.tmp, "mock.md"),
                "knowledge_base": os.path.join(self.tmp, "kb"),
                "prompts": os.path.join(self.tmp, "prompts"),
            }}, handle)

    def run(self, allow_incomplete=False):
        return check_integrity.run(self.config, allow_incomplete)


class TestIntegrity(unittest.TestCase):
    def test_a_complete_course_passes_with_no_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Fixture(tmp).run()
            self.assertEqual(report.errors, [])
            self.assertTrue(any("3 of 3 units have gear-2 content (1 covered by sub-elements)" in n for n in report.notes))

    def test_a_missing_unit_is_an_error_or_a_warning_by_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(tmp)
            os.remove(os.path.join(tmp, "curriculum", "UA.I.B.K16.md"))
            strict = fixture.run()
            self.assertTrue(any("no gear-2 content for 1 unit: UA.I.B.K16" in e for e in strict.errors))
            lenient = fixture.run(allow_incomplete=True)
            self.assertEqual([e for e in lenient.errors if "coverage" in e], [])
            self.assertTrue(any("UA.I.B.K16" in w for w in lenient.warnings))

    def test_a_content_file_without_a_source_link_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(tmp)
            write(os.path.join(tmp, "curriculum", "UA.I.B.K16.md"), GOOD_CONTENT.replace("| https://example.invalid/fixture/107-41", ""))
            self.assertTrue(any("has no http link" in e for e in fixture.run().errors))

    def test_a_content_file_for_an_unknown_unit_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(tmp)
            write(os.path.join(tmp, "curriculum", "UA.I.Z.K9.md"), GOOD_CONTENT)
            self.assertTrue(any("does not match a tracked unit" in e for e in fixture.run().errors))

    def test_a_broken_mock_item_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(tmp)
            write(os.path.join(tmp, "mock.md"),
                  "| Item | Unit | Stem | A | B | C | Answer | Rationale | Source | Link |\n|---|---|---|---|---|---|---|---|---|---|\n"
                  "| m-1 | UA.I.B.K16 | Stem? | x | x | z | D |  | F | not-a-link |\n")
            errors = fixture.run().errors
            self.assertTrue(any("answer must be A, B, or C" in e for e in errors))
            self.assertTrue(any("not three distinct texts" in e for e in errors))
            self.assertTrue(any("no rationale" in e for e in errors))
            self.assertTrue(any("link is not an http link" in e for e in errors))

    def test_a_fact_for_an_unknown_unit_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(tmp)
            with open(os.path.join(tmp, "facts.md"), "a", encoding="utf-8") as handle:
                handle.write("| UA.I.Q.K1 | Nope | x | F | https://example.invalid/f |\n")
            self.assertTrue(any("unknown unit" in e for e in fixture.run().errors))

    def test_an_orphan_explanation_chunk_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(tmp)
            write(os.path.join(tmp, "kb", "src-107-41.explained.md"),
                  GOOD_KB.replace("kind: source", "kind: explanation\nderived_from: missing.md"))
            self.assertTrue(any("derived_from 'missing.md' is not a chunk" in e for e in fixture.run().errors))

    def test_a_missing_prompt_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(tmp)
            os.remove(os.path.join(tmp, "prompts", "mock_gate.md"))
            self.assertIn("prompts: missing mock_gate.md", fixture.run().errors)


class TestPackaging(unittest.TestCase):
    def test_exclusions(self):
        self.assertTrue(package.wanted("server.py"))
        self.assertTrue(package.wanted(os.path.join("ui", "app.js")))
        self.assertTrue(package.wanted(os.path.join("knowledge-base", "regulations", "x.md")))
        self.assertFalse(package.wanted(os.path.join("progress", "student-ledger.md")))
        self.assertFalse(package.wanted(os.path.join("knowledge-base", "pdfs", "14cfr107.pdf")))
        self.assertFalse(package.wanted(os.path.join("tests", "test_phase2.py")))
        self.assertFalse(package.wanted(os.path.join("tools", "__pycache__", "x.pyc")))
        self.assertFalse(package.wanted(os.path.join("dist", "old.zip")))


if __name__ == "__main__":
    unittest.main()
