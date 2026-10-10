"""The three-panel layout: the dividers in ui/panels.js, on the course page's
own markup and styles, and the tree in the progress panel drawn at the
panel's width by ui/app.js.

Serves the course folder on a free port, loads tests/fixtures/panels.html in
headless Chrome at a set window size, and reads the result the page writes.
Skips when Chrome is not installed.

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
class TestPanels(unittest.TestCase):
    def page(self, query, size):
        """What the fixture writes into its #result, loaded with `query` in a window of `size` (w,h)."""
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as profile:
                url = "http://127.0.0.1:%d/tests/fixtures/panels.html?%s" % (httpd.server_address[1], query)
                dom = subprocess.run(
                    [CHROME, "--headless", "--disable-gpu", "--user-data-dir=" + profile,
                     "--window-size=" + size, "--dump-dom", url],
                    capture_output=True, text=True, timeout=60,
                ).stdout
        finally:
            httpd.shutdown()
            httpd.server_close()
        result = re.search(r'<pre id="result">(.*?)</pre>', dom, re.S)
        self.assertIsNotNone(result, "Chrome returned no page")
        return html.unescape(result.group(1))

    def test_the_dividers_resize_the_side_panels_within_limits(self):
        self.assertEqual(self.page("", "1600,1000"), "PASS")

    def test_widths_from_an_earlier_visit_come_back(self):
        self.assertEqual(self.page("stored", "1600,1000"), "PASS")

    def test_a_narrow_window_stacks_the_panels(self):
        self.assertEqual(self.page("narrow", "800,1000"), "PASS")


if __name__ == "__main__":
    unittest.main()
