"""Markdown in the page: ui/markdown.js over ui/marked.min.js, and the chat's
drawing dialog in ui/app.js.

Serves the course folder on a free port, loads a page from tests/fixtures in
headless Chrome, and reads the result the page writes. Skips when Chrome is
not installed.

Run from the course folder:  python3 -m unittest discover -s tests -v
"""

import functools
import html
import http.server
import os
import re
import shutil
import subprocess
import tempfile
import threading
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROME = next(filter(None, map(shutil.which, ("google-chrome", "chromium", "chromium-browser"))), None)


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass


@unittest.skipIf(CHROME is None, "Chrome is not installed")
class TestMarkdown(unittest.TestCase):
    def page(self, name):
        """What the fixture page `name` writes into its #result."""
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as profile:
                url = "http://127.0.0.1:%d/tests/fixtures/%s" % (httpd.server_address[1], name)
                dom = subprocess.run(
                    [CHROME, "--headless", "--disable-gpu", "--user-data-dir=" + profile, "--dump-dom", url],
                    capture_output=True, text=True, timeout=60,
                ).stdout
        finally:
            httpd.shutdown()
            httpd.server_close()
        result = re.search(r'<pre id="result">(.*?)</pre>', dom, re.S)
        self.assertIsNotNone(result, "Chrome returned no page")
        return html.unescape(result.group(1))

    def test_the_page_renders_markdown_and_never_runs_code(self):
        self.assertEqual(self.page("markdown.html"), "PASS")

    def test_a_chat_drawing_opens_large_on_a_click(self):
        self.assertEqual(self.page("chat_drawing.html"), "PASS")


if __name__ == "__main__":
    unittest.main()
