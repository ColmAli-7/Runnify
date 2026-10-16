---
name: Runnify
description: "Every run replayed with its soundtrack: quiet cards in light and dark, big tabular numbers, and colour that always means faster, slower, pace or heart rate."
colors:
  bg: "#f3f4f6"
  bg-dark: "#0a0b0d"
  surface: "#ffffff"
  surface-dark: "#141619"
  surface-2: "#f7f8f9"
  surface-2-dark: "#1b1e22"
  surface-3: "#eceef1"
  surface-3-dark: "#24282d"
  surface-inverse: "#0e1013"
  surface-inverse-dark: "#f2f4f6"
  line: "#e3e6ea"
  line-dark: "#262a2f"
  line-strong: "#cfd4da"
  line-strong-dark: "#353a40"
  field: "#7b828b"
  field-dark: "#80878f"
  text: "#0e1013"
  text-dark: "#f2f4f6"
  text-2: "#474e57"
  text-2-dark: "#b3b9c0"
  text-3: "#646c76"
  text-3-dark: "#8d949c"
  accent: "#d4ff3a"
  on-accent: "#0b0d02"
  accent-ink: "#4a6a00"
  accent-ink-dark: "#d4ff3a"
  accent-strong: "#6f9a00"
  accent-strong-dark: "#d4ff3a"
  accent-soft: "#f6ffd4"
  accent-soft-dark: "#2f371e"
  drag: "#c8331f"
  drag-dark: "#ff6a5c"
  drag-soft: "#faebe9"
  drag-soft-dark: "#3a2324"
  pace: "#0a63d1"
  pace-dark: "#5aa8ff"
  heart: "#c8204f"
  heart-dark: "#ff5d8b"
  ok: "#16733f"
  ok-dark: "#47d98a"
typography:
  display:
    fontFamily: "Geist, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "clamp(2.75rem, 1.15rem + 4.6vw, 4.875rem)"
    fontWeight: 750
    lineHeight: 0.98
    letterSpacing: "-0.05em"
  section-title:
    fontSize: "clamp(2.25rem, 1.55rem + 2.4vw, 3.5rem)"
    fontWeight: 700
    lineHeight: 1.05
    letterSpacing: "-0.04em"
  page-title:
    fontSize: "clamp(1.75rem, 1.45rem + 1vw, 2.25rem)"
    fontWeight: 700
    lineHeight: 1.1
    letterSpacing: "-0.035em"
  card-title:
    fontSize: "1.125rem"
    fontWeight: 650
    letterSpacing: "-0.02em"
  stat:
    fontSize: "clamp(1.5rem, 1.3rem + 0.6vw, 1.875rem)"
    fontWeight: 650
    letterSpacing: "-0.035em"
    fontFeature: '"tnum"'
  body:
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.55
  ui:
    fontSize: "0.9375rem"
    fontWeight: 500
  meta:
    fontSize: "0.8125rem"
    fontWeight: 500
rounded:
  badge: "6px"
  control: "10px"
  field: "12px"
  tile: "14px"
  card: "20px"
  screen: "28px"
spacing:
  s-1: "4px"
  s-2: "8px"
  s-3: "12px"
  s-4: "16px"
  s-5: "24px"
  s-6: "32px"
  s-7: "48px"
  s-8: "64px"
  s-9: "96px"
  s-10: "128px"
  gutter: "clamp(16px, 4vw, 40px)"
  card-pad: "clamp(16px, 2.4vw, 24px)"
components:
  button:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    height: "44px"
    padding: "0 20px"
  button-primary:
    backgroundColor: "{colors.surface-inverse}"
    textColor: "{colors.surface}"
  lift-up:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.on-accent}"
    rounded: "{rounded.badge}"
  lift-down:
    backgroundColor: "{colors.drag-soft}"
    textColor: "{colors.drag}"
    rounded: "{rounded.badge}"
  card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.card}"
  input:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.field}"
    height: "48px"
---

<!-- Recorded from the built code on 16 October 2026, after the redesign described in docs/redesign/. Where a screenshot and the code differ, the code wins. -->

# Design system: Runnify

## Overview

**Creative North Star: "Replay"**

Every run is replayed with its soundtrack. A run's pace is a line; its songs are
blocks in a lane beneath it, each lit by what it did to the runner's pace. The
interface around that stays quiet: grey pages with raised cards in a light and a
dark theme, big tabular numbers with small grey units, and short sentences that
say what the numbers mean. Colour is never decoration: volt means faster, coral
means slower, blue is pace, rose is heart rate and green is connected or done.

The standard is Apple Health, Strava and Garmin Connect (see
[docs/redesign/competitor-audit.md](docs/redesign/competitor-audit.md)): Apple's
calm detail pages and one-sentence highlights, Strava's synchronised charts and
summary under the stats, Garmin's dashed average lines and honesty about the
evidence behind a score.

**Key characteristics**

- A grey page (#F3F4F6, or #0A0B0D in dark) with cards that lift on a soft shadow
  in light and a lighter surface in dark.
- One typeface, Geist, with tabular figures for every number.
- Volt (#D4FF3A) only ever means faster. Selected and current states are solid ink.
- No capsules: controls are rounded rectangles.
- Product screens on the landing page are dark in both themes.
- The landing page tells one moving story; the app moves only when the runner does.
- Every page works without scripts, under a strict Content-Security-Policy.

## Colors

Each token holds a light and a dark value, written once with `light-dark()` in
`runnify/static/css/ui/tokens.css`. The theme follows the system unless the
runner chooses Light or Dark. All 74 text and graphic pairs (37 per theme) pass
WCAG 2.2 AA in `scripts/check_contrast.py`.

### Surfaces and text

- **Page** (#F3F4F6 / #0A0B0D): the ground every card sits on.
- **Card** (#FFFFFF / #141619): cards, panels, fields, menus.
- **Surface 2** (#F7F8F9 / #1B1E22): hovered rows, gap rows, inset notes.
- **Surface 3** (#ECEEF1 / #24282D): segmented tracks, rank badges, tags, meter tracks.
- **Ink** (#0E1013 / #F2F4F6): text, primary buttons, the current page, selected
  options. Its inverse (white or near-black) sits on it.
- **Secondary text** (#474E57 / #B3B9C0) and **meta text** (#646C76 / #8D949C):
  ledes and labels; units, axis labels and evidence.
- **Hairline** (#E3E6EA / #262A2F) and **strong line** (#CFD4DA / #353A40):
  dividers and bar outlines, never meaning on their own.
- **Field border** (#7B828B / #80878F): form controls, at least 3:1.

### Meaning

- **Volt** (#D4FF3A): lift badges, the best row's rank, the best song's band and
  lane block, the playlist cover bars, the wordmark's stroke. Text on it is
  near-black (#0B0D02). Where volt marks must stand on white (bars, meters), it
  darkens to #6F9A00; volt text on white uses #4A6A00. The best row is washed in
  #F6FFD4 (#2F371E in dark).
- **Coral** (#C8331F / #FF6A5C): drag figures and badges, the slowest song,
  errors and failed states, washed in #FAEBE9 / #3A2324.
- **Blue** (#0A63D1 / #5AA8FF): the pace line, focus rings, information notices,
  and a faint wash for the five minutes either side of a song.
- **Rose** (#C8204F / #FF5D8B): the heart-rate line and heart findings.
- **Green** (#16733F / #47D98A): connected and done tags, finished steps,
  privacy promises.

### Named rules

**The Volt Rule.** Volt means faster: a lift, the best song, the stretch that
worked. It never marks a selected control, a link or a decoration.

**The Never Alone Rule.** Colour is never the only signal. A lift carries an up
arrow and a plus sign, a drag a down arrow and a true minus sign, and both read
"faster" or "slower" to assistive technology.

**The Two Themes Rule.** A new colour is written with `light-dark()` and added to
the contrast check in both themes before it ships.

## Typography

**Font:** Geist (SIL Open Font License, self-hosted, one variable file, weights
100 to 900). The platform monospace appears only for codes and secrets.

**Character:** headlines and big numbers are heavy and tightly tracked; labels are
small, grey and in sentence case (no uppercase eyebrows); every number uses
tabular figures so paces and lifts line up.

### Hierarchy

- **Display** (750, 2.75rem to 4.875rem, -0.05em): the landing headline, two lines
  on wide screens.
- **Section title** (700, 2.25rem to 3.5rem, -0.04em): landing sections.
- **Page title** (700, 1.75rem to 2.25rem, -0.035em): app pages.
- **Card title** (650, 1.125rem, -0.02em): with an icon in the card's colour.
- **Stat** (650, 1.5rem to 1.875rem, tabular): distance, time, pace, heart rate,
  with the unit at 0.9375rem in meta text.
- **Body** (400, 1rem, 1.55) up to 66 characters a line; **UI text** (500 to 600,
  0.9375rem); **meta** (500, 0.8125rem).

### Named rules

**The One Format Rule.** A number reads the same everywhere: pace 4:52, durations
48:12 or 1:02:45, distances 10.02, lifts as whole s/km with a sign and a
non-breaking space (+9 s/km, −5 s/km with a true minus sign, ±0 s/km). Formats
live in `runnify/filters.py`.

**The Sentence Rule.** Labels and buttons are sentence case. Copy is plain and
specific, and there are no em dashes.

## Layout

Content sits in a centred column up to 1200px with a 16px to 40px gutter. The app
uses a 12-column grid for the dashboard (the latest run beside three highlights,
the weeks beside the songs) and two columns for Insights, Friends, Playlists and
Connections from 960px or 1024px. Cards sit 24px apart.

- **Breakpoints:** 480px (segmented controls go two by two, the session picker
  three to a row), 560px, 760px (four stats across), 900px (the app navigation
  moves from the phone tab bar to pills in the header), 960px, 1024px (wide
  layouts and the story's sticky steps), 1200px (the three-column bento).
- **Headers:** a sticky 64px bar with a glass backing layer. On the landing page
  it stays clear until the page moves under it.
- **Phone tab bar:** fixed to the bottom with the safe area, five tabs, the
  current tab's icon on an ink tile.
- **Landing sections** alternate the page grey and white, 72px to 128px apart.

## Elevation and depth

- **Light:** cards lift on `0 1px 2px` plus a soft tinted shadow; menus and the
  sign-in card on a deeper one.
- **Dark:** cards sit on a lighter surface with a hairline; shadows are near-black.
- **Glass:** only the header and the phone tab bar, on a backing layer so the bar
  never traps fixed elements. Under reduced transparency they turn solid.
- **Product screens:** the landing page's replay, story screens, run tile and
  closing panel set `color-scheme: dark`, so they are dark in both themes.

## Shapes

| Element | Corner |
|---|---|
| Tags, lift badges, rank badges | 6px |
| Buttons, navigation links, segmented options, the theme switch | 10px (9px inside a 12px track) |
| Fields and segmented tracks | 12px |
| Tiles inside cards, notices | 14px |
| Cards | 20px |
| Landing tiles, screens, the replay card | 28px |
| Thin bars, meters, progress | rounded ends |
| Avatars, step numbers, the progress ring | circles |

### Named rules

**The No Capsule Rule.** No pill-shaped buttons or controls. Rounded ends belong
only to thin bars.

Icons come from one sprite (`static/img/icons.svg`): a 24-unit grid, a 1.8px
stroke with round caps and joins, in the current text colour. No emoji or text
characters as icons, and no Garmin or Spotify logos.

## Components

Jinja macros and plain CSS in cascade layers (reset, base, layout, components,
pages, utilities). No inline styles, scripts or handlers; behaviour attaches from
modules through `data-*` attributes.

- **Buttons:** primary is solid ink with inverse text; the default is a card
  surface with a strong outline; quiet has no border; danger turns coral. 44px
  tall (36px small, 52px large). Pressed, they scale to 0.98; a trailing arrow
  leans 2px on hover.
- **Fields:** a label above, an optional hint, a 48px field with a 12px corner, a
  blue focus ring, a coral error with an icon tied by `aria-describedby`.
  Checkboxes are native, tinted ink. Selects carry a chevron that follows the theme.
- **Cards:** a title with an icon, a meta line, a body; tables and lists run
  flush to the card's edges.
- **Stats:** a grid of label, big tabular value and unit, split by hairlines.
- **Results tables:** a round rank badge, the song with its artist under it, when
  it came on, the heart-rate change, and the lift badge. The best row is washed
  in volt and its rank badge is solid volt. A song's name, here, in ranked lists
  and in highlights, links to the song's page.
- **Ranked lists:** rank badge, name and detail, a thin bar of its size against
  the strongest, the figure and its evidence (runs).
- **Highlights:** a kicker in the finding's colour with an icon, one sentence
  with the key word in bold, the figure and unit, and the evidence.
- **Lift badges:** volt with an up arrow, coral wash with a down arrow, grey for
  under 1 s/km.
- **Segmented controls:** a grey track with a raised thumb; two by two below 480px.
- **Theme switch:** Auto, Light and Dark, with the current one pressed.
- **Notices:** a card with an icon, washed green for success and coral for errors.
- **Steps:** numbered circles that turn green with a tick when done; the
  dashboard adds a progress ring.
- **Account menu:** a native disclosure that closes on Escape, an outside click
  or focus leaving.
- **Charts:** see below.

### Charts

- **Run chart:** a 2px line in blue (pace, faster higher) or rose (heart rate)
  with a gradient fill, a dashed moving-average line with its value, light
  gridlines, a band per song (alternate songs in grey, the best in volt, the
  biggest drag in coral, the minutes either side of a song in a faint blue).
- **Song lane:** one rounded block per song under the pace chart, named when its
  block is wide enough.
- **Scrubbing:** a guide across both charts and the lane, dots on the lines, and a
  floating readout; the pointer, a finger or the arrow keys move it.
- **Bars:** rounded; this week stronger; lifts in volt and coral.
- **Matched runs:** on each song's page, a dot per measured play at its run's date
  and lift (volt above a zero line, coral below, grey under 1 s/km) and a 2px ink
  trend line, the way Strava draws matched activities.
- Geometry is computed on the server in percentages, so charts need no scripts
  and no inline styles, and every chart is `role="img"` with a written summary.

## Motion

**The Show Something Rule.** Every movement shows something the product does.
Nothing fades in on scroll, and nothing moves under reduced motion.

- **Landing page:** the headline's words rise once; the sample run replays (a
  playhead, the line drawing, songs lighting and playing in turn, distance and
  time counting) over nine seconds and pauses off screen; the four story steps
  draw the pace line, sweep the songs into place, open the minutes either side of
  the best song while its lift counts up, and strike the best ranked song with
  volt; the session picker grows its bars; the closing panel draws the run's
  pace line. See [docs/redesign/plan.md](docs/redesign/plan.md#motion) for timings.
- **App:** state changes only: 120ms colour, 200ms presses and menus, notices drop
  in, the menu scales from its corner, the run chart's scrub follows the pointer
  exactly.
- **Theme changes** pause transitions for the instant the theme flips.
- Only transforms, opacity, SVG clip rectangles and `clip-path` animate.

## Do's and Don'ts

### Do

- **Do** write every colour with `light-dark()` and add new pairs to the contrast check.
- **Do** use volt only for faster, coral only for slower or errors, blue for pace
  and focus, rose for heart rate, green for done.
- **Do** put the evidence (runs, plays) beside every lift.
- **Do** lead a page with a sentence when the numbers need one, worked out from
  the numbers, never generated.
- **Do** keep controls as 10px rounded rectangles and cards at 20px.
- **Do** set every number in tabular figures and the shared formats.
- **Do** mark demonstration data as sample data, computed by the real engine.
- **Do** make every page work without scripts and keep templates free of inline code.

### Don't

- **Don't** use pill-shaped buttons or controls.
- **Don't** fade content in on scroll, or add motion that doesn't show something.
- **Don't** use volt for selection, links or decoration.
- **Don't** use purple gradients, glass on content, emoji icons or a second typeface.
- **Don't** invent reviews, users, metrics or press; there are none.
- **Don't** use Garmin or Spotify logos or brand colours; their names only
  describe the integrations.
- **Don't** load fonts, scripts or styles from third parties.
- **Don't** use em dashes.
