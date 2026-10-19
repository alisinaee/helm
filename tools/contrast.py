"""Check the colour tokens in web/css/tokens.css against WCAG contrast for the dark, light and obsidian themes.

Text pairs need 4.5:1; graphics (control borders, focus ring, meter fills) need 3:1. The dark theme is the
:root default. The light theme is the set of overrides under prefers-color-scheme and data-theme="light", laid over
the dark values; the obsidian block overrides the dark ones. Exit 0 when every pair passes, 1 otherwise. Stdlib only.
"""

import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKENS = os.path.join(REPO, "web", "css", "tokens.css")
TEXT_MIN = 4.5
GRAPHIC_MIN = 3.0
SURFACES = ("surface-0", "surface-1", "surface-2")
TEXT_ROLES = ("text-1", "text-2", "text-3", "accent", "success", "warning", "danger", "info", "defer",
              "m-haiku", "m-sonnet", "m-opus", "m-cursor", "m-agy")
GRAPHIC_ROLES = ("line", "focus")
METER_FILLS = ("accent", "success", "warning", "danger")
BLOCK = re.compile(r"([^{}]+)\{([^{}]*)\}")
DECL = re.compile(r"--([a-z0-9-]+)\s*:\s*([^;]+);")
HEX = re.compile(r"^#([0-9a-fA-F]{6})$")


def parse_blocks(text):
    """Return (dark, light, obsidian): the dark default, the light overrides and the obsidian overrides, each resolved."""
    dark, light, obsidian = {}, {}, {}
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    for selector, body in BLOCK.findall(text):
        sel = " ".join(selector.split())
        values = {name: value.strip() for name, value in DECL.findall(body)}
        if not values:
            continue
        if 'data-theme="obsidian"' in sel:
            obsidian.update(values)
        elif 'data-theme="light"' in sel or ':not([data-theme="dark"])' in sel:
            light.update(values)
        else:
            dark.update(values)
    resolved_light = dict(dark)
    resolved_light.update(light)
    resolved_obsidian = dict(dark)
    resolved_obsidian.update(obsidian)
    return dark, resolved_light, resolved_obsidian


def luminance(hex_value):
    """WCAG relative luminance of a #rrggbb colour."""
    match = HEX.match(hex_value)
    if match is None:
        raise ValueError("not a 6-digit hex colour: %r" % hex_value)
    channels = []
    for i in range(0, 6, 2):
        c = int(match.group(1)[i:i + 2], 16) / 255.0
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(fg, bg):
    """Contrast ratio between two #rrggbb colours, from 1 to 21."""
    lighter, darker = sorted((luminance(fg), luminance(bg)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def pairs():
    """The (foreground, background, minimum, label) checks for each theme."""
    out = []
    for role in TEXT_ROLES:
        for surface in SURFACES:
            out.append((role, surface, TEXT_MIN, "text"))
    out.append(("on-accent", "accent", TEXT_MIN, "text"))
    for role in GRAPHIC_ROLES:
        for surface in SURFACES:
            out.append((role, surface, GRAPHIC_MIN, "graphic"))
    for fill in METER_FILLS:
        out.append((fill, "track", GRAPHIC_MIN, "meter"))
    return out


def check(values, theme):
    """Failures for one theme as strings. Missing or non-hex tokens are failures too."""
    failures = []
    for fg, bg, minimum, kind in pairs():
        for name in (fg, bg):
            if name not in values:
                failures.append("%s: token --%s is not defined" % (theme, name))
        if fg not in values or bg not in values:
            continue
        try:
            found = ratio(values[fg], values[bg])
        except ValueError as exc:
            failures.append("%s: %s" % (theme, exc))
            continue
        if found + 1e-9 < minimum:
            failures.append("%s: %s --%s on --%s is %.2f:1, needs %.1f:1"
                            % (theme, kind, fg, bg, found, minimum))
    return failures


def main():
    """Print every ratio and return the exit code."""
    with open(TOKENS, encoding="utf-8") as fh:
        dark, light, obsidian = parse_blocks(fh.read())
    failures = check(dark, "dark") + check(light, "light") + check(obsidian, "obsidian")
    for theme, values in (("dark", dark), ("light", light), ("obsidian", obsidian)):
        worst = min(ratio(values[fg], values[bg]) for fg, bg, _, _ in pairs() if fg in values and bg in values)
        print("%s: %d pairs checked, lowest %.2f:1" % (theme, len(pairs()), worst))
    for line in failures:
        print("FAIL " + line)
    print("contrast: " + ("ok" if not failures else str(len(failures)) + " failure(s)"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
