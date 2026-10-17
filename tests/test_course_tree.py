"""The course tree in ui/course-tree.js: the marker on the lane the student is
on now.

Serves the course folder on a free port, loads tests/fixtures/course_tree.html
in headless Chrome, and reads the result the page writes. Skips when Chrome is
not installed.

Run from the course folder:  python3 -m unittest discover -s tests -v
"""

import functools
import html
import http.server
import re
import subprocess
import tempfile
import threading
import unittest

from test_markdown import CHROME, ROOT, Quiet


@unittest.skipIf(CHROME is None, "Chrome is not installed")
class TestCourseTree(unittest.TestCase):
    def page(self):
        """What the fixture writes into its #result."""
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as profile:
                url = "http://127.0.0.1:%d/tests/fixtures/course_tree.html" % httpd.server_address[1]
                dom = subprocess.run(
                    [CHROME, "--headless", "--disable-gpu", "--user-data-dir=" + profile,
                     "--window-size=1600,1000", "--dump-dom", url],
                    capture_output=True, text=True, timeout=60,
                ).stdout
        finally:
            httpd.shutdown()
            httpd.server_close()
        result = re.search(r'<pre id="result">(.*?)</pre>', dom, re.S)
        self.assertIsNotNone(result, "Chrome returned no page")
        return html.unescape(result.group(1))

    def test_the_current_lane_has_a_large_dot_with_a_pulsing_halo(self):
        self.assertEqual(self.page(), "PASS")


if __name__ == "__main__":
    unittest.main()
