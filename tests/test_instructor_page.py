"""The instructor workspace in the page: ui/instructor.js over the course page's markup.

Serves the course folder on a free port, loads tests/fixtures/instructor.html in
headless Chrome, and reads the result the page writes. Skips when Chrome is not
installed.

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
class TestInstructorPage(unittest.TestCase):
    def test_open_ask_apply_save_and_try_a_lesson(self):
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as profile:
                url = "http://127.0.0.1:%d/tests/fixtures/instructor.html" % httpd.server_address[1]
                # The page steps through its checks on timers, so give it virtual time.
                dom = subprocess.run(
                    [CHROME, "--headless", "--disable-gpu", "--user-data-dir=" + profile,
                     "--virtual-time-budget=10000", "--dump-dom", url],
                    capture_output=True, text=True, timeout=60,
                ).stdout
        finally:
            httpd.shutdown()
            httpd.server_close()
        result = re.search(r'<pre id="result">(.*?)</pre>', dom, re.S)
        self.assertIsNotNone(result, "Chrome returned no page")
        self.assertEqual(html.unescape(result.group(1)), "PASS")


if __name__ == "__main__":
    unittest.main()
