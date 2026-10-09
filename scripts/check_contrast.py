"""Check the colour pairs the design uses against WCAG 2.2 contrast minimums.

Reads the colour tokens from ``runnify/static/css/ui/tokens.css`` and checks
every text-on-background pair the stylesheets use. Text needs 4.5:1 (AA);
form-control borders and other meaningful graphics need 3:1.

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

# (foreground, background, minimum, where it is used)
PAIRS = [
    ("ink", "paper", TEXT, "body text"),
    ("ink-2", "paper", TEXT, "secondary text"),
    ("ink-3", "paper", TEXT, "meta text, chart labels"),
    ("ink", "board", TEXT, "text on the noticeboard"),
    ("ink-2", "board", TEXT, "secondary text on the board, flat lifts"),
    ("ink-3", "board", TEXT, "meta text on the board"),
    ("ink", "highlight", TEXT, "the best row, lifts"),
    ("ink-2", "highlight", TEXT, "artist names in the best ranked song"),
    ("ink-3", "highlight", TEXT, "artist names in a results table's best row"),
    ("ink", "highlight-soft", TEXT, "hovered rows and links"),
    ("pen", "paper", TEXT, "drags, errors"),
    ("pen", "pen-soft", TEXT, "icons and figures on error grounds"),
    ("go", "paper", TEXT, "connected, done"),
    ("go", "go-soft", TEXT, "success notices"),
    ("paper", "ink", TEXT, "primary buttons, the selected tab"),
    ("on-ink", "ink", TEXT, "text on the ink bands"),
    ("on-ink-2", "ink", TEXT, "secondary text on the ink bands"),
    ("highlight", "ink", TEXT, "lifts on the ink bands"),
    ("pen-on-ink", "ink", TEXT, "drags on the ink bands"),
    ("field", "paper", GRAPHIC, "form control borders"),
    ("pen", "paper", GRAPHIC, "invalid field borders"),
]


def tokens(css):
    """``--name: #rrggbb`` declarations from the first ``:root`` block."""
    root = css[css.index(":root") :]
    root = root[: root.index("}")]
    return {
        name: value.lower()
        for name, value in re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})", root)
    }


def luminance(hex_colour):
    """WCAG relative luminance of ``#rrggbb``."""
    channels = [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(first, second):
    lighter, darker = sorted((luminance(first), luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def main():
    colours = tokens(TOKENS.read_text(encoding="utf-8"))
    failures = 0
    for foreground, background, minimum, use in PAIRS:
        ratio = contrast(colours[foreground], colours[background])
        ok = ratio >= minimum
        failures += not ok
        mark = "ok  " if ok else "FAIL"
        print(f"{mark} {ratio:5.2f}:1 (needs {minimum}:1)  {foreground} on {background}: {use}")
    print(f"\n{len(PAIRS) - failures} of {len(PAIRS)} pairs pass.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
