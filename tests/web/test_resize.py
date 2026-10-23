"""Static checks for drag-resize of the left nav and right panel (R10.3)."""

import os
import unittest

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "web")


def read(*p):
    with open(os.path.join(WEB, *p), encoding="utf-8") as f:
        return f.read()


class ResizeTest(unittest.TestCase):
    def test_wired(self):
        self.assertIn('href="/css/resize.css"', read("index.html"))
        app = read("js", "app.js")
        self.assertIn('from "./resize.js"', app)
        self.assertEqual(app.count("initResize()"), 1)

    def test_js_contract(self):
        js = read("js", "resize.js")
        for s in ("setPointerCapture", "requestAnimationFrame", 'role", "separator"', "aria-orientation",
            "aria-valuenow",
                  "ArrowLeft", "ArrowRight", "dblclick", "localStorage", "--w-nav", "--w-side", "STEP = 16", "min: 56",
                  "min: 280", "720"):
            self.assertIn(s, js)
        self.assertIn("try {", js)

    def test_css(self):
        css = read("css", "resize.css")
        self.assertIn("col-resize", css)
        self.assertIn("width:6px", css)
        self.assertLess(len(css.splitlines()), 15)


if __name__ == "__main__":
    unittest.main()
