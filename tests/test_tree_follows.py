"""The course tree keeps up with the lesson: ui/app.js redraws the tree when
the tutor starts to write, not when the lesson is finished.

Serves the course folder on a free port, loads tests/fixtures/tree_follows.html
in headless Chrome, and reads the result the page writes. A fake server keeps
the lesson stream open, so the tree must move while the tutor writes. Skips
when Chrome is not installed.

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
class TestTreeFollows(unittest.TestCase):
    def page(self, query):
        """What the fixture writes into its #result, loaded with `query`."""
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as profile:
                url = "http://127.0.0.1:%d/tests/fixtures/tree_follows.html?%s" % (httpd.server_address[1], query)
                # The checks run on a timer, so give the page virtual time.
                dom = subprocess.run(
                    [CHROME, "--headless", "--disable-gpu", "--user-data-dir=" + profile,
                     "--window-size=1600,1000", "--virtual-time-budget=5000", "--dump-dom", url],
                    capture_output=True, text=True, timeout=60,
                ).stdout
        finally:
            httpd.shutdown()
            httpd.server_close()
        result = re.search(r'<pre id="result">(.*?)</pre>', dom, re.S)
        self.assertIsNotNone(result, "Chrome returned no page")
        return html.unescape(result.group(1))

    def test_a_track_switch_moves_the_dot_when_the_tutor_starts(self):
        self.assertEqual(self.page(""), "PASS")

    def test_a_new_unit_is_current_when_the_tutor_starts(self):
        self.assertEqual(self.page("unit"), "PASS")


if __name__ == "__main__":
    unittest.main()
