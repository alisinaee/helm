"""Checks for the UX discoverability group (R8.20, R8.21, R8.23, R7.16 step 5b).

Cmd+K has a visible button in the top bar, and the shortcut list is in Settings (helpRows in keys.js). The Mark
button, the m key and the palette command "Mark a bug here" call log.js mark() through topbar.js markBug(), and exist
only on localhost with a CSRF value (never on the phone). Settings choice buttons form a radiogroup (role radio with
aria-checked and a tick on the chosen one, arrow keys move between them). Single-key shortcuts can be turned off in
Settings, and Escape that closes the panel sheet returns focus to the panel toggle. The source checks read the files;
the node check renders the top bar with no window (phone-like) and is skipped when node is missing.
"""

import os
import re
import shutil
import subprocess
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
TOPBAR_JS = os.path.join(WEB, "js", "views", "topbar.js")
PALETTE_JS = os.path.join(WEB, "js", "views", "palette.js")
KEYS_JS = os.path.join(WEB, "js", "keys.js")
SETTINGS_JS = os.path.join(WEB, "js", "views", "settings.js")
ICONS = os.path.join(WEB, "icons.svg")
INLINE = re.compile(r"""\sstyle\s*=|\son[a-z]{3,}\s*=""", re.IGNORECASE)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class TopbarDiscoverSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = read(TOPBAR_JS)

    def test_cmd_k_button_is_always_in_the_top_bar(self):
        self.assertIn('data-action="palette-open"', self.src)
        self.assertIn('aria-label="Command palette (Cmd+K or Ctrl+K)"', self.src)
        self.assertIn("paletteHtml() +", self.src)

    def test_mark_button_is_gated_on_localhost_and_csrf(self):
        self.assertIn('const LOCAL_HOST = /^(localhost|127\\.0\\.0\\.1|\\[::1\\])$/;', self.src)
        self.assertIn("LOCAL_HOST.test(location.hostname) && Boolean(csrfToken())", self.src)
        self.assertIn("function markHtml() {\n  if (!markAllowed() || phoneWidth()) return \"\";", self.src)
        self.assertIn('window.matchMedia("(max-width: 599px)")', self.src)

    def test_mark_button_has_flag_icon_label_and_key_hint(self):
        self.assertIn('data-action="mark-bug"', self.src)
        self.assertIn("/icons.svg#i-flag", self.src)
        self.assertIn("aria-label=\"Mark: ' + MARK_LABEL", self.src)
        self.assertIn("title=\"' + MARK_LABEL", self.src)
        self.assertIn('MARK_LABEL = "I am seeing a bug here"', self.src)
        self.assertIn("(m)", self.src)

    def test_mark_calls_log_mark_and_says_marked(self):
        self.assertIn('import { mark, status as logStatus } from "../log.js";', self.src)
        self.assertIn("mark(MARK_LABEL);", self.src)
        self.assertIn('showToast({ text: "Marked" });', self.src)

    def test_mark_says_when_logging_is_off(self):
        self.assertIn("if (!logStatus().active)", self.src)
        self.assertIn("Logging is off. Turn it on in Settings > Logging.", self.src)

    def test_no_raw_markup_helpers(self):
        self.assertNotIn("innerHTML", self.src)
        self.assertIsNone(INLINE.search(self.src))


class KeysDiscoverSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = read(KEYS_JS)

    def test_m_key_marks_only_when_allowed(self):
        self.assertIn('} else if (key === "m") {\n    if (markAllowed()) markBug();', self.src)

    def test_shell_clicks_handle_mark_and_palette(self):
        self.assertIn('document.addEventListener("click", onShellClick);', self.src)
        self.assertIn('if (action === "mark-bug") {', self.src)
        self.assertIn('} else if (action === "palette-open") {\n    hooks.openPalette();', self.src)

    def test_help_rows_list_cmd_k_and_mark(self):
        rows = self.src[self.src.index("export function helpRows()"):]
        self.assertIn('["Ctrl+K or Cmd+K",', rows)
        self.assertIn('["m", "Mark a bug here', rows)

    def test_single_key_switch_is_stored_and_defaults_on(self):
        self.assertIn('const SINGLE_KEY_SWITCH = "rb.keys.single";', self.src)
        self.assertIn('window.localStorage.getItem(SINGLE_KEY_SWITCH) !== "0"', self.src)
        self.assertIn("export function setSingleKeys(on)", self.src)
        self.assertIn('window.localStorage.setItem(SINGLE_KEY_SWITCH, singleKeysMemo ? "1" : "0")', self.src)

    def test_single_character_keys_are_gated_by_the_switch(self):
        handler = self.src[self.src.index("function onKeydown(event)"):self.src.index("export function helpRows()")]
        gate = handler.index('if (key.length === 1 && !singleKeysOn()) {')
        self.assertLess(handler.index('if (key === "Escape") {'), gate)
        self.assertLess(gate, handler.index('if (key === "?") {'))
        self.assertLess(gate, handler.index("extra.has(key)"))

    def test_modifier_shortcuts_are_not_gated(self):
        self.assertIn('if (isPaletteKey(event)) {', self.src)
        self.assertIn('event.altKey && !event.ctrlKey && !event.metaKey && !isTyping(event.target) && extra.has',
                      self.src)

    def test_escape_returns_focus_to_panel_toggle(self):
        self.assertIn("closePanel();\n      focusPanelToggle();", self.src)
        self.assertIn("function focusPanelToggle()", self.src)
        self.assertIn("document.querySelector('[data-focus=\"panel-toggle\"]')", self.src)
        self.assertIn("btn.focus()", self.src)


class PaletteDiscoverSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = read(PALETTE_JS)

    def test_mark_command_is_listed_only_when_allowed(self):
        self.assertIn('import { markAllowed, markBug } from "./topbar.js";', self.src)
        self.assertIn('if (markAllowed()) out.push(cmd(">mark", "Mark a bug here", () => markBug()));', self.src)


class SettingsChoiceSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = read(SETTINGS_JS)

    def test_choice_rows_are_radios_with_a_tick(self):
        self.assertIn('role="radiogroup" aria-label="\' + esc(name) + \'"', self.src)
        self.assertIn('role="radio" aria-checked="\' + (on ? "true" : "false") +', self.src)
        self.assertIn('tabindex="\' + (on ? "0" : "-1") +', self.src)
        self.assertNotIn("aria-pressed", self.src)
        self.assertIn('(on ? "i-check" : "i-blank")', self.src)
        self.assertIn('<svg class="ico" aria-hidden="true" focusable="false">', self.src)

    def test_arrow_keys_move_and_choose_between_radios(self):
        self.assertIn("function radioArrowKey(event)", self.src)
        for key in ("ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"):
            self.assertIn('"%s"' % key, self.src)
        self.assertIn('el.getAttribute("role") !== "radio"', self.src)
        self.assertIn("event.preventDefault();\n  next.focus();\n  next.click();", self.src)
        self.assertIn('document.addEventListener("keydown", radioArrowKey);', self.src)

    def test_single_key_switch_in_settings(self):
        self.assertIn('import { helpRows, setSingleKeys, singleKeysOn } from "../keys.js";', self.src)
        self.assertIn('choiceHtml("Single-key shortcuts", SINGLE_KEYS_SWITCH, on, "set-single-keys")', self.src)
        self.assertIn('if (action === "set-single-keys") {\n    setSingleKeys(el.getAttribute("data-value") === "on");',
                      self.src)
        self.assertIn("singleKeysHtml() + keysHtml()", self.src)

    def test_settings_lists_the_shortcuts_from_keys(self):
        self.assertIn('import { helpRows, setSingleKeys, singleKeysOn } from "../keys.js";', self.src)
        self.assertIn('<span class="kbd">\' + esc(row[0]) + "</span> "', self.src)
        self.assertIn("keysHtml() +", self.src)

    def test_no_mark_or_inline_code_in_settings(self):
        self.assertNotIn("markBug", self.src)
        self.assertNotIn("innerHTML", self.src)
        self.assertIsNone(INLINE.search(self.src))


class IconSprite(unittest.TestCase):
    def test_flag_check_and_blank_symbols_exist(self):
        text = read(ICONS)
        for sid in ("i-flag", "i-check", "i-blank"):
            self.assertIn('<symbol id="%s"' % sid, text)


class TopbarRenderNode(unittest.TestCase):
    def test_phone_like_render_has_cmd_k_and_no_mark(self):
        node = shutil.which("node")
        if node is None:
            raise unittest.SkipTest("node is not installed; the top bar render check is skipped")
        script = (
            'const top = await import(' + repr(TOPBAR_JS).replace("'", '"') + ');'
            'const html = top.topbarView({route: {name: "all", section: "overview", view: ""},'
            ' ui: {panelOpen: true}, conn: {ok: true}, control: null, theme: "auto", meterRows: null});'
            'console.log(html);'
        )
        proc = subprocess.run([node, "--experimental-default-type=module", "-e", script],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('data-action="palette-open"', proc.stdout)
        self.assertNotIn('data-action="mark-bug"', proc.stdout)


if __name__ == "__main__":
    unittest.main()
