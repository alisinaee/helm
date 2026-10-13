"""Static accessibility checks on the browser sources (stdlib only, no browser, no node).

The views are JavaScript template strings, so these checks read the source text. Every <button> and other
interactive element written by a view or by index.html needs an accessible name: visible text, aria-label or
aria-labelledby. A disclosure button (one with aria-expanded) also needs aria-controls, and the id it names must be
produced in the same file. Interactive elements are never a <div> or <span> with an on*= handler. Images have alt,
form fields have a label, the page has html lang and exactly one h1, status chips and badges contain text (so colour
is not the only carrier), the stylesheet has a prefers-reduced-motion block that stops animation and transitions,
and focus-visible styles exist.

The id check resolves names in the same file: a const such as bodyId = "sec-" + id + "-body" is expanded, so the
aria-controls value and the id attribute that both use it compare equal. Limits: a name that is only a computed
expression counts as present, and a button whose only content is an icon with no text is not caught when the icon
is written as a JavaScript expression. The checks are a gate, not a proof.
"""

import os
import re
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
INDEX = os.path.join(WEB, "index.html")
CSS_DIR = os.path.join(WEB, "css")
JS_DIR = os.path.join(WEB, "js")

BUTTON_OPEN = re.compile(r"<button\b([^>]*)>", re.DOTALL)
LINK_OPEN = re.compile(r"<a\b([^>]*)>", re.DOTALL)
SELECT_OPEN = re.compile(r"<(select|input|textarea)\b([^>]*)>", re.DOTALL)
IMG_OPEN = re.compile(r"<img\b([^>]*)>", re.DOTALL)
CHIP_OPEN = re.compile(r"<span\b[^>]*class=\"[^\"]*\b(?:chip|badge)", re.DOTALL)
HANDLER_IN_TAG = re.compile(r"<[a-zA-Z][^>]*\son[a-z]{3,}\s*=\s*\\?[\"']", re.DOTALL)
ARIA_NAME = re.compile(r"\baria-(?:label|labelledby)\s*=")
ARIA_HIDDEN_SPAN = re.compile(r"<(span|i|em)\b[^>]*aria-hidden=[\"'\\]+true[^>]*>.*?</\1>", re.DOTALL)
TAG = re.compile(r"<[^>]*>", re.DOTALL)
CONTROLS_REF = re.compile(r"aria-controls=\\?\"")
ID_ATTR = re.compile(r"(?<![\w-])id=\\?\"")
DECL = re.compile(r"\b(?:const|let)\s+([A-Za-z_]\w*)\s*=\s*([^;]+);")
IDENT = re.compile(r"[A-Za-z_]\w*")
REDUCED = re.compile(r"@media\s*\(\s*prefers-reduced-motion\s*:\s*reduce\s*\)\s*\{")


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def js_sources():
    """Every JavaScript file under web/js, sorted, as (relative path, text)."""
    found = []
    for dirpath, dirnames, filenames in os.walk(JS_DIR):
        dirnames.sort()
        for name in sorted(filenames):
            if name.endswith(".js"):
                full = os.path.join(dirpath, name)
                found.append((os.path.relpath(full, REPO), read(full)))
    return found


def css_sources():
    found = []
    for name in sorted(os.listdir(CSS_DIR)):
        if name.endswith(".css"):
            found.append((os.path.join("web", "css", name), read(os.path.join(CSS_DIR, name))))
    return found


def has_text(inner):
    """True when the element content has a letter or digit once hidden icons and tags are removed."""
    visible = ARIA_HIDDEN_SPAN.sub(" ", inner)
    visible = TAG.sub(" ", visible)
    return re.search(r"[^\W_]", visible) is not None


def closing(src, start, tag):
    """The source text from start up to the next closing tag, or None when there is none."""
    end = src.find("</" + tag + ">", start)
    if end < 0:
        return None
    return src[start:end]


def canon(expr, defs, depth=0):
    """A comparable form of an id expression: quotes, plus signs, esc() and spaces removed, names expanded."""
    text = re.sub(r"esc\(|[()\s'\"+\\]", "", expr)
    if depth > 6:
        return text
    out = []
    pos = 0
    for match in IDENT.finditer(text):
        out.append(text[pos:match.start()])
        name = match.group(0)
        if name in defs and defs[name] != expr:
            out.append(canon(defs[name], defs, depth + 1))
        else:
            out.append(name)
        pos = match.end()
    out.append(text[pos:])
    return "".join(out)


def ids_defined(src):
    """Canonical forms of every id attribute value in one file."""
    defs = {name: rhs for name, rhs in DECL.findall(src)}
    found = set()
    for match in ID_ATTR.finditer(src):
        raw = src[match.end():match.end() + 300]
        raw = raw[:raw.find("\"")] if "\"" in raw else raw
        found.add(canon(raw, defs))
    return found, defs


def controls_refs(src, defs):
    """Canonical forms of every aria-controls value in one file, with the position of each."""
    refs = []
    for match in CONTROLS_REF.finditer(src):
        raw = src[match.end():match.end() + 300]
        raw = raw[:raw.find("\"")] if "\"" in raw else raw
        line = src.count("\n", 0, match.start()) + 1
        refs.append((canon(raw, defs), line))
    return refs


def line_of(src, pos):
    return src.count("\n", 0, pos) + 1


class ButtonNames(unittest.TestCase):
    def test_every_button_has_an_accessible_name(self):
        problems = []
        count = 0
        for path, src in js_sources() + [(os.path.relpath(INDEX, REPO), read(INDEX))]:
            for match in BUTTON_OPEN.finditer(src):
                count += 1
                inner = closing(src, match.end(), "button")
                if ARIA_NAME.search(match.group(1)):
                    continue
                if inner is None or not has_text(inner):
                    problems.append("%s:%d button has no text, aria-label or aria-labelledby"
                                    % (path, line_of(src, match.start())))
        self.assertGreater(count, 5, "too few buttons found; the parser is probably wrong")
        self.assertEqual(problems, [])

    def test_links_and_form_fields_have_names(self):
        problems = []
        for path, src in js_sources() + [(os.path.relpath(INDEX, REPO), read(INDEX))]:
            for match in LINK_OPEN.finditer(src):
                inner = closing(src, match.end(), "a")
                if inner is not None and not ARIA_NAME.search(match.group(1)) and not has_text(inner):
                    problems.append("%s:%d link has no text" % (path, line_of(src, match.start())))
            for match in SELECT_OPEN.finditer(src):
                if ARIA_NAME.search(match.group(2)):
                    continue
                before = src[max(0, match.start() - 200):match.start()]
                after = src[match.end():match.end() + 400]
                labelled = "<label" in before and "</label>" in after
                if not labelled:
                    problems.append("%s:%d form field has no label" % (path, line_of(src, match.start())))
        self.assertEqual(problems, [])

    def test_no_clickable_div_or_span(self):
        problems = []
        for path, src in js_sources() + [(os.path.relpath(INDEX, REPO), read(INDEX))]:
            for match in HANDLER_IN_TAG.finditer(src):
                problems.append("%s:%d inline on*= handler (use data-action and delegation)"
                                % (path, line_of(src, match.start())))
        self.assertEqual(problems, [])


class Disclosure(unittest.TestCase):
    def test_disclosure_buttons_have_expanded_and_controls(self):
        problems = []
        seen = 0
        for path, src in js_sources():
            for match in BUTTON_OPEN.finditer(src):
                attrs = match.group(1)
                if "aria-expanded" not in attrs:
                    continue
                seen += 1
                if "aria-controls" not in attrs:
                    problems.append("%s:%d disclosure button has no aria-controls"
                                    % (path, line_of(src, match.start())))
        self.assertGreater(seen, 2, "too few disclosure buttons found")
        self.assertEqual(problems, [])

    def test_aria_controls_names_an_id_in_the_same_file(self):
        problems = []
        total = 0
        for path, src in js_sources():
            ids, defs = ids_defined(src)
            for ref, line in controls_refs(src, defs):
                total += 1
                if ref not in ids:
                    problems.append("%s:%d aria-controls points at no id in this file" % (path, line))
        self.assertGreater(total, 2, "too few aria-controls found")
        self.assertEqual(problems, [])


class Images(unittest.TestCase):
    def test_images_have_alt(self):
        problems = []
        for path, src in js_sources() + [(os.path.relpath(INDEX, REPO), read(INDEX))]:
            for match in IMG_OPEN.finditer(src):
                if not re.search(r"\balt\s*=", match.group(1)):
                    problems.append("%s:%d image has no alt" % (path, line_of(src, match.start())))
        self.assertEqual(problems, [])


class Document(unittest.TestCase):
    def test_html_has_lang(self):
        self.assertRegex(read(INDEX), r"<html\b[^>]*\blang=\"[A-Za-z][A-Za-z-]*\"")

    def test_exactly_one_h1(self):
        sources = [read(INDEX)] + [src for _path, src in js_sources()]
        count = sum(len(re.findall(r"<h1\b", src)) for src in sources)
        self.assertEqual(count, 1, "the page must have exactly one h1 (found %d)" % count)

    def test_status_chips_and_badges_contain_text(self):
        problems = []
        seen = 0
        for path, src in js_sources():
            for match in CHIP_OPEN.finditer(src):
                seen += 1
                inner = closing(src, match.end(), "span")
                if inner is None or not has_text(inner):
                    problems.append("%s:%d status chip or badge has no text (colour alone must not carry it)"
                                    % (path, line_of(src, match.start())))
        self.assertGreater(seen, 0, "no status chips found; the parser is probably wrong")
        self.assertEqual(problems, [])


class Stylesheet(unittest.TestCase):
    def _reduced_blocks(self):
        blocks = []
        for path, css in css_sources():
            for match in REDUCED.finditer(css):
                depth = 1
                pos = match.end()
                while pos < len(css) and depth:
                    if css[pos] == "{":
                        depth += 1
                    elif css[pos] == "}":
                        depth -= 1
                    pos += 1
                blocks.append(css[match.end():pos - 1])
        return blocks

    def test_reduced_motion_block_disables_animation_and_transition(self):
        blocks = self._reduced_blocks()
        self.assertTrue(blocks, "no @media (prefers-reduced-motion: reduce) block in web/css")
        joined = "\n".join(blocks)
        self.assertRegex(joined, r"animation\s*:\s*none")
        self.assertRegex(joined, r"transition\s*:\s*none")

    def test_focus_visible_style_exists(self):
        combined = "\n".join(css for _path, css in css_sources())
        self.assertIn(":focus-visible", combined)
