"""Check the colour tokens in web/css/tokens.css against WCAG contrast for the 6 looks.

Looks = 3 palettes x 2 modes: classic, obsidian and black (data-theme), each in dark and light (data-mode).
Text pairs need 4.5:1; graphics (control borders, focus ring, meter fills) need 3:1.

The cascade is modelled as the CSS applies it: :root is the base (classic dark); :root[data-mode="light"] is the
classic light set; :root[data-theme="X"] is palette X; :root[data-theme="X"][data-mode="light"] is palette X in light.
Specificity order is base < mode < palette < palette+mode, ties keep file order. The no-JS fallback
(:root:not([data-mode]) under prefers-color-scheme) is not a look and is not checked. Exit 0 when every pair of
every look passes, 1 otherwise. Stdlib only.
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


PALETTES = ("classic", "obsidian", "black")
MODES = ("dark", "light")
LOOKS = [(p, m) for p in PALETTES for m in MODES]
THEME_ATTR = re.compile(r'data-theme="([a-z]+)"')


def layer_of(selector):
    """(rank, palette, light) for a selector, or None for the no-JS fallback and anything unknown.

    rank: 0 base (:root), 1 mode (data-mode="light"), 2 palette, 3 palette in light. Higher rank wins.
    """
    if ":not([data-mode])" in selector:
        return None
    theme = THEME_ATTR.search(selector)
    light = 'data-mode="light"' in selector
    if theme is None:
        return (1, None, True) if light else (0, None, False)
    return (3 if light else 2), theme.group(1), light


def parse_blocks(text):
    """Return the ordered list of (rank, palette, light, values) for every token block in the file."""
    layers = []
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    for selector, body in BLOCK.findall(text):
        sel = " ".join(selector.split())
        values = {name: value.strip() for name, value in DECL.findall(body)}
        if not values:
            continue
        info = layer_of(sel)
        if info is None:
            continue
        rank, palette, light = info
        layers.append((rank, palette, light, values))
    return layers


def resolve(layers, palette, mode):
    """The token values one look sees: the layers that apply to it, lowest rank first, file order within a rank."""
    chosen = [layer for layer in layers
              if (layer[1] is None or layer[1] == palette) and (not layer[2] or mode == "light")]
    out = {}
    for layer in sorted(chosen, key=lambda layer: layer[0]):
        out.update(layer[3])
    return out


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
    """Print every ratio for the 6 looks and return the exit code."""
    with open(TOKENS, encoding="utf-8") as fh:
        layers = parse_blocks(fh.read())
    failures = []
    for palette, mode in LOOKS:
        theme = "%s %s" % (palette, mode)
        values = resolve(layers, palette, mode)
        failures += check(values, theme)
        worst = min(ratio(values[fg], values[bg]) for fg, bg, _, _ in pairs() if fg in values and bg in values)
        print("%s: %d pairs checked, lowest %.2f:1" % (theme, len(pairs()), worst))
    for line in failures:
        print("FAIL " + line)
    print("contrast: " + ("ok" if not failures else str(len(failures)) + " failure(s)"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
