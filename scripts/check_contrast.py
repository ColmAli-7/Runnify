"""Check the colour pairs the design uses against WCAG 2.2 contrast minimums.

Reads the colour tokens from ``runnify/static/css/ui/tokens.css``, where each
token holds its light and dark value as ``light-dark(#light, #dark)``, and checks
every text-on-background and graphic-on-background pair the stylesheets use, in
both themes. Text needs 4.5:1 (AA); form-control borders, focus rings, chart
lines and other meaningful graphics need 3:1.

Usage::

    uv run python scripts/check_contrast.py

Exits with status 1 if any pair falls short.
"""

import re
import sys
from pathlib import Path

TOKENS = Path(__file__).resolve().parent.parent / "runnify" / "static" / "css" / "ui" / "tokens.css"

TEXT = 4.5
GRAPHIC = 3.0
THEMES = ("light", "dark")

# (foreground, background, minimum, where it is used)
PAIRS = [
    # text on the page and on cards
    ("text", "bg", TEXT, "body text on the page"),
    ("text", "surface", TEXT, "body text on cards"),
    ("text", "surface-2", TEXT, "hovered rows"),
    ("text", "surface-3", TEXT, "text on grey controls"),
    ("text-2", "bg", TEXT, "secondary text on the page"),
    ("text-2", "surface", TEXT, "secondary text on cards"),
    ("text-2", "surface-2", TEXT, "secondary text on hovered rows"),
    ("text-2", "surface-3", TEXT, "tags, segmented labels, rank badges"),
    ("text-3", "bg", TEXT, "meta text on the page"),
    ("text-3", "surface", TEXT, "meta text, chart labels, column heads"),
    ("text-3", "surface-2", TEXT, "meta text on hovered rows and gap rows"),
    ("text", "thumb", TEXT, "the selected option of a segmented control"),
    ("text-inverse", "surface-inverse", TEXT, "primary buttons, the current page"),
    # volt: faster
    ("on-accent", "accent", TEXT, "lift badges and the best rank"),
    ("text", "accent-soft", TEXT, "the best row"),
    ("text-2", "accent-soft", TEXT, "artist names in the best row"),
    ("accent-ink", "surface", TEXT, "lift findings on cards"),
    ("accent-ink", "bg", TEXT, "lift findings on the page"),
    # coral: slower, and errors
    ("drag", "surface", TEXT, "drag figures and errors on cards"),
    ("drag", "bg", TEXT, "field errors on the page"),
    ("drag", "drag-soft", TEXT, "drag badges, failed tags"),
    ("text", "drag-soft", TEXT, "error notices"),
    # status and metrics
    ("ok", "surface", TEXT, "connected and done text"),
    ("ok", "ok-soft", TEXT, "connected tags"),
    ("text", "ok-soft", TEXT, "success notices"),
    ("pace", "surface", TEXT, "pace figures and links"),
    ("heart", "surface", TEXT, "heart-rate findings"),
    # graphics
    ("field", "surface", GRAPHIC, "form control borders on cards"),
    ("field", "bg", GRAPHIC, "form control borders on the page"),
    ("focus", "surface", GRAPHIC, "focus rings on cards"),
    ("focus", "bg", GRAPHIC, "focus rings on the page"),
    ("pace", "surface", GRAPHIC, "the pace line"),
    ("heart", "surface", GRAPHIC, "the heart-rate line"),
    ("accent-strong", "surface", GRAPHIC, "lift bars and meters"),
    ("drag", "surface", GRAPHIC, "drag bars and meters"),
    ("ok", "surface", GRAPHIC, "finished steps"),
    ("text-3", "surface", GRAPHIC, "muted bars"),
]

HEX = r"#[0-9a-fA-F]{6}"


def tokens(css):
    """``{theme: {name: '#rrggbb'}}`` from the first ``:root`` block.

    A token written ``light-dark(#light, #dark)`` takes each value in its theme;
    a plain ``#rrggbb`` is the same in both. Other values (shadows, rgb() washes)
    are not text or graphic colours and are skipped.
    """
    root = css[css.index(":root") :]
    root = root[: root.index("}")]
    themes = {theme: {} for theme in THEMES}
    for name, light, dark in re.findall(
        rf"--([a-z0-9-]+):\s*light-dark\(\s*({HEX})\s*,\s*({HEX})\s*\)", root
    ):
        themes["light"][name] = light.lower()
        themes["dark"][name] = dark.lower()
    for name, value in re.findall(rf"--([a-z0-9-]+):\s*({HEX})\s*;", root):
        for theme in THEMES:
            themes[theme][name] = value.lower()
    return themes


def luminance(hex_colour):
    """WCAG relative luminance of ``#rrggbb``."""
    channels = [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(first, second):
    lighter, darker = sorted((luminance(first), luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def main():
    themes = tokens(TOKENS.read_text(encoding="utf-8"))
    failures = 0
    for theme in THEMES:
        colours = themes[theme]
        print(f"{theme} theme")
        for foreground, background, minimum, use in PAIRS:
            ratio = contrast(colours[foreground], colours[background])
            ok = ratio >= minimum
            failures += not ok
            mark = "ok  " if ok else "FAIL"
            print(
                f"  {mark} {ratio:5.2f}:1 (needs {minimum}:1)  {foreground} on {background}: {use}"
            )
    total = len(PAIRS) * len(THEMES)
    print(f"\n{total - failures} of {total} pairs pass.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
