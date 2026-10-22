"""Tests for the build tools: the knowledge-base builder and enhancer.

Run from the course folder:  python3 -m unittest discover -s tests -v
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import build_kb          # noqa: E402
import check_companions  # noqa: E402
import check_links       # noqa: E402
import enhance_kb        # noqa: E402
import fetch_sources     # noqa: E402
import retrieval         # noqa: E402

CFR_PAGES = [
    "PART 107\nSubpart B\n§ 107.29 Operation at night.\n(a) No person may operate at night unless:\n"
    "(1) lighting visible for 3 statute miles.\n\n§ 107.31 Visual line of sight.\n(a) The remote pilot must see the aircraft.\n12",
    "§ 107.41 Operation in certain airspace.\nNo person may operate in Class B airspace without authorization.\n13",
]


class TestChunker(unittest.TestCase):
    def test_cfr_sections_are_cut_at_headings_with_pages(self):
        sections = build_kb.split_sections(CFR_PAGES, "cfr")
        ids = [s["section"] for s in sections]
        self.assertEqual(ids, ["front", "107.29", "107.31", "107.41"])
        by_id = {s["section"]: s for s in sections}
        self.assertEqual(by_id["107.41"]["page"], 2)
        self.assertEqual(by_id["107.29"]["title"], "Operation at night")
        self.assertIn("3 statute miles", by_id["107.29"]["text"])

    def test_page_number_lines_are_dropped(self):
        sections = build_kb.split_sections(CFR_PAGES, "cfr")
        for section in sections:
            self.assertNotRegex(section["text"], r"(?m)^\s*1[23]\s*$")

    def test_numbered_and_chapter_presets(self):
        numbered = ["Intro text\n5.1 Registration Requirements\nBody one.\n5.2 Night Operations\nBody two."]
        ids = [s["section"] for s in build_kb.split_sections(numbered, "numbered")]
        self.assertEqual(ids, ["front", "5.1", "5.2"])
        chapters = ["Chapter 1: Applicable Regulations\nBody.\nChapter 2 Airspace\nMore."]
        ids = [s["section"] for s in build_kb.split_sections(chapters, "chapter")]
        self.assertEqual(ids, ["Chapter 1", "Chapter 2"])

    def test_custom_regex_is_accepted(self):
        pages = ["ITEM A Alpha\ntext\nITEM B Beta\ntext"]
        ids = [s["section"] for s in build_kb.split_sections(pages, r"^ITEM (?P<section>[A-Z]) (?P<title>.*)$")]
        self.assertEqual(ids, ["A", "B"])

    def test_long_sections_split_at_paragraphs_and_keep_their_id(self):
        section = {"section": "107.49", "title": "Preflight", "page": 3,
                   "text": "\n\n".join("Paragraph %d " % i + "x" * 100 for i in range(10))}
        parts = build_kb.split_long(section, max_chars=400)
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(p["section"] == "107.49" for p in parts))
        self.assertEqual([p["part"] for p in parts], list(range(1, len(parts) + 1)))
        self.assertTrue(all(len(p["text"]) <= 400 + 110 for p in parts))

    def test_rendered_chunk_carries_citation_metadata_and_parses_back(self):
        source = {"id": "x", "title": "Test Source", "url": "https://example.invalid/p",
                  "heading": "cfr", "section_url": "https://example.invalid/s-{section}"}
        section = {"section": "107.41", "title": "Certain airspace", "page": 2, "text": "Body."}
        text = build_kb.render_chunk(source, section)
        chunk = retrieval.parse_chunk(text, build_kb.chunk_filename("x", section))
        self.assertEqual(chunk["url"], "https://example.invalid/s-107.41")
        self.assertEqual(chunk["section"], "§ 107.41 Certain airspace")
        self.assertEqual(chunk["kind"], "source")
        self.assertEqual(chunk["text"], "Body.")

    def test_page_links_for_pdf_sources(self):
        source = {"id": "ac", "title": "AC", "url": "https://example.invalid/ac.pdf", "heading": "numbered"}
        section = {"section": "5.2", "title": "T", "page": 17, "text": "Body."}
        self.assertEqual(build_kb.section_link(source, section), "https://example.invalid/ac.pdf#page=17")

    def test_front_matter_links_to_the_document_not_a_section(self):
        source = {"id": "x", "title": "X", "url": "https://example.invalid/p", "heading": "cfr",
                  "section_url": "https://example.invalid/s-{section}"}
        front = {"section": "front", "title": "Front matter", "page": 1, "text": "Authority."}
        self.assertEqual(build_kb.section_link(source, front), "https://example.invalid/p")


class TestBuildOptions(unittest.TestCase):
    def test_layout_flag_controls_pdftotext_mode(self):
        calls = []

        def fake_run(argv, **kwargs):
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, "page one\fpage two", "")

        with mock.patch.object(build_kb.subprocess, "run", fake_run):
            self.assertEqual(build_kb.pdf_to_pages("x.pdf"), ["page one", "page two"])
            build_kb.pdf_to_pages("x.pdf", layout=False)
        self.assertIn("-layout", calls[0])
        self.assertNotIn("-layout", calls[1])

    def test_repeated_headings_do_not_overwrite_each_other(self):
        pages = ["Task A. General\nFirst body.", "Task A. Airspace\nSecond body."]
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(build_kb, "pdf_to_pages", return_value=pages):
            pdf = os.path.join(tmp, "s.pdf")
            open(pdf, "w").close()
            source = {"id": "s", "title": "S", "pdf": pdf, "url": "https://example.invalid/s",
                      "heading": r"^(?P<section>Task [A-F])\.\s+(?P<title>.*)$"}
            written = build_kb.build_source(source, tmp)
            self.assertEqual(sorted(w["file"] for w in written), ["s-task-a-2.md", "s-task-a.md"])
            texts = {c["id"]: c["text"] for c in retrieval.load_chunks(tmp)}
            self.assertIn("First body.", texts["s-task-a.md"])
            self.assertIn("Second body.", texts["s-task-a-2.md"])


class TestFetcher(unittest.TestCase):
    HTML = ("<html><head><title>Remote ID | Federal Aviation Administration</title></head><body>"
            "<nav>menu</nav><main><h1>Remote ID</h1><script>track()</script><p>Rule text.</p>"
            "<img src='a.png'></main><footer>foot</footer></body></html>")

    def test_main_content_keeps_the_text_and_drops_site_chrome(self):
        content = fetch_sources.main_content(self.HTML)
        self.assertIn("Rule text.", content)
        for noise in ("menu", "track()", "<img", "foot"):
            self.assertNotIn(noise, content)

    def test_title_line_is_prepended_for_the_heading_regex(self):
        self.assertEqual(fetch_sources.page_title(self.HTML), "Remote ID")
        document = fetch_sources.wrap(fetch_sources.main_content(self.HTML), "Remote ID")
        self.assertIn("TITLE: Remote ID", document)
        self.assertTrue(document.startswith("<!doctype html>"))

    def test_ecfr_urls(self):
        self.assertTrue(fetch_sources.ecfr_url(part="107").endswith("title-14?part=107"))
        self.assertTrue(fetch_sources.ecfr_url(section="91.17").endswith("title-14?part=91&section=91.17"))


class TestLinkCheck(unittest.TestCase):
    def test_a_timeout_while_reading_is_a_failed_link_not_a_crash(self):
        with mock.patch("urllib.request.urlopen", side_effect=TimeoutError("The read operation timed out")):
            self.assertEqual(check_links.probe("https://www.faa.gov/x", 1), (0, "The read operation timed out"))

    def test_a_dropped_connection_on_the_get_retry_is_a_failed_link(self):
        refused = check_links.urllib.error.HTTPError("https://www.faa.gov/x", 405, "Method Not Allowed", {}, None)
        with mock.patch("urllib.request.urlopen", side_effect=[refused, ConnectionResetError()]):
            self.assertEqual(check_links.probe("https://www.faa.gov/x", 1), (0, "ConnectionResetError"))


class TestCompanionCheck(unittest.TestCase):
    def test_numbers_absent_from_the_source_are_listed(self):
        source = "§ 107.51 Operating limitations. The altitude limit is 400 feet; weight 0.55 pounds; 2,000 feet from clouds."
        companion = ("You may climb to 400 feet with a 0.55-pound aircraft and keep 2,000 feet from clouds. "
                     "The tower in the scenario is 600 feet tall. See § 107.41 and part 89 for the rest. 3 items.")
        self.assertEqual(check_companions.extra_numbers(source, companion), ["600"])

    def test_sentence_context(self):
        text = "First sentence. The tower is 600 feet tall. Last one."
        self.assertEqual(check_companions.sentence_with(text, "600"), "The tower is 600 feet tall.")


class TestEnhancer(unittest.TestCase):
    def test_answer_parsing_tolerates_fences_and_prose(self):
        clean = '{"explanation": "e", "illustration": "i", "misreading": "", "skip": false}'
        self.assertEqual(enhance_kb.parse_answer(clean)["explanation"], "e")
        self.assertEqual(enhance_kb.parse_answer("```json\n" + clean + "\n```")["illustration"], "i")
        self.assertEqual(enhance_kb.parse_answer("Here you go:\n" + clean)["explanation"], "e")
        self.assertIsNone(enhance_kb.parse_answer("nothing here"))

    def test_companion_keeps_the_source_citation_and_is_tagged_derived(self):
        chunk = {"id": "x-107-41.md", "source": "S", "section": "§ 107.41 T", "url": "https://example.invalid/s", "page": "2", "text": "..."}
        text = enhance_kb.render(chunk, {"explanation": "Plain.", "illustration": "Scenario.", "misreading": "Trap."})
        parsed = retrieval.parse_chunk(text, enhance_kb.companion_name("x-107-41"))
        self.assertEqual(parsed["kind"], "explanation")
        self.assertEqual(parsed["url"], "https://example.invalid/s")
        self.assertEqual(parsed["derived_from"], "x-107-41.md")
        self.assertIn("Illustration: Scenario.", parsed["text"])
        self.assertIn("Common misreading: Trap.", parsed["text"])


HAVE_PDF_TOOLS = shutil.which("pdftotext") is not None and importlib.util.find_spec("reportlab") is not None


@unittest.skipUnless(HAVE_PDF_TOOLS, "needs pdftotext and reportlab")
class TestEndToEnd(unittest.TestCase):
    def test_pdf_to_chunks_to_retrieval(self):
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas

        with tempfile.TemporaryDirectory() as tmp:
            pdf = os.path.join(tmp, "t.pdf")
            page = canvas.Canvas(pdf, pagesize=letter)
            page.drawString(72, 740, "§ 107.41 Operation in certain airspace.")
            page.drawString(72, 720, "No person may operate in Class B airspace without prior authorization.")
            page.showPage()
            page.save()

            out = os.path.join(tmp, "out")
            os.makedirs(out)
            manifest = os.path.join(tmp, "m.json")
            with open(manifest, "w", encoding="utf-8") as handle:
                json.dump({"output": out, "sources": [{
                    "id": "t", "title": "T", "pdf": pdf, "url": "https://example.invalid/p",
                    "heading": "cfr", "section_url": "https://example.invalid/s-{section}"}]}, handle)
            subprocess.run([sys.executable, os.path.join(ROOT, "tools", "build_kb.py"), "--manifest", manifest],
                           check=True, capture_output=True)

            chunks = retrieval.load_chunks(out)
            hit = retrieval.search(chunks, "prior authorization Class B")[0]
            self.assertEqual(hit["url"], "https://example.invalid/s-107.41")
            self.assertIn("prior authorization", hit["text"])
            self.assertTrue(os.path.exists(os.path.join(out, "index.md")))


if __name__ == "__main__":
    unittest.main()
