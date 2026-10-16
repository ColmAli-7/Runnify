# The switch to "Replay": plan and record

How Runnify moved from "The Official Results Sheet" to a design that stands
next to Apple Health, Strava and Garmin Connect, October 2026. The research
behind it is in [competitor-audit.md](competitor-audit.md); the system itself
is recorded in [DESIGN.md](../../DESIGN.md).

## Contents

- [Summary](#summary)
- [Design read](#design-read)
- [Principles](#principles)
- [The system](#the-system)
- [What changed, page by page](#what-changed-page-by-page)
- [Motion](#motion)
- [Accessibility, privacy and content checklist](#accessibility-privacy-and-content-checklist)
- [Checks run](#checks-run)
- [What comes next](#what-comes-next)

## Summary

**Before**: white paper and black ink, 2px rules and square corners, highlighter
yellow and red pen, light only, a tilted results sheet on the landing page.

**After**: every run replayed with its soundtrack. Quiet grey pages with raised
cards in a light and a dark theme, big tabular numbers, colour that always means
something, charts with soft fills, a song lane and a scrubbing readout, findings
written as sentences, and a landing page whose hero is a sample run playing back
song by song.

**Kept**: the name, the Geist typeface, the scoring method and its honesty about
evidence, server-drawn charts, the strict Content-Security-Policy, pages that
work without scripts, and plain copy without em dashes.

## Design read

Reading this as a redesign (overhaul) of a consumer running-analytics product,
landing page and signed-in app, for runners who use Garmin and Spotify, in the
premium, data-first language of Apple Health, Strava and Garmin Connect, built
on native CSS tokens with light and dark themes, Geist with tabular figures,
server-drawn SVG charts and GSAP for the landing page's one moving story.

| Surface | Variance | Motion | Density | Why |
|---|---|---|---|---|
| Landing page | 7 | 6 | 4 | A product with one clear mechanism to show: asymmetric hero, one replay, one scroll story |
| Signed-in app | 4 | 3 | 6 | Read often, at a glance: calm layouts, state changes only, dense but legible numbers |

## Principles

1. **Data first, chrome last.** Big numbers and charts; frames, rules and labels
   stay quiet.
2. **Colour always means something.** Volt is faster, coral is slower, blue is
   pace and focus, rose is heart rate, green is connected or done. Selected and
   current states are solid ink, never a colour.
3. **Say it in a sentence.** Every run and the Insights page lead with what the
   numbers mean, in plain words, worked out from the numbers (never generated).
4. **Show the evidence.** Runs and plays sit beside every lift; songs rank only
   after two runs.
5. **One moving story.** The landing page shows the product doing its job; the
   app moves only when the runner does something.
6. **Both themes from the start,** each checked for contrast.

## The system

### Theming

- Every colour token holds its light and dark value with `light-dark()` in
  `static/css/ui/tokens.css`. Browsers without `light-dark()` get the light theme.
- The theme follows the system. **Auto, Light and Dark** sit in the account menu
  and the public footer. A choice is kept in `localStorage` as `runnify-theme`
  (listed in the cookie policy); Auto removes it.
- `static/js/theme.js` runs in `<head>` before the page paints, so a dark page
  never flashes light. Transitions pause for the instant the theme flips, so no
  colour sticks on the old theme.
- Product screens on the landing page (the replay, the story screens, the run
  tile and the closing panel) are dark in both themes, like a phone held up to
  the page.

### Colour roles

| Role | Light | Dark | Used for |
|---|---|---|---|
| Page | #F3F4F6 | #0A0B0D | The ground every card sits on |
| Card | #FFFFFF | #141619 | Cards, panels, fields |
| Raised grey | #ECEEF1 | #24282D | Segmented tracks, rank badges, tags |
| Text | #0E1013 | #F2F4F6 | Body text, numbers |
| Secondary text | #474E57 | #B3B9C0 | Ledes, labels |
| Meta text | #646C76 | #8D949C | Units, axis labels, evidence |
| Volt | #D4FF3A | #D4FF3A | Lift badges, the best row, the best song, the wordmark's stroke |
| Volt for marks on white | #6F9A00 | #D4FF3A | Lift bars and meters that must hold 3:1 |
| Coral | #C8331F | #FF6A5C | Drags, errors |
| Blue | #0A63D1 | #5AA8FF | The pace line, focus rings, information |
| Rose | #C8204F | #FF5D8B | Heart rate |
| Green | #16733F | #47D98A | Connected, done, privacy promises |

All 74 text and graphic pairs (37 in each theme) pass WCAG 2.2 AA in
`scripts/check_contrast.py`, and a rendered scan of every page found no text
below AA in either theme.

### Type

Geist only, with tabular figures for every number.

| Role | Size | Weight |
|---|---|---|
| Landing headline | 2.75rem to 4.875rem | 750, -0.05em |
| Section title | 2.25rem to 3.5rem | 700 |
| Page title | 1.75rem to 2.25rem | 700 |
| Card title | 1.125rem | 650 |
| Big stat | 1.5rem to 1.875rem | 650, tabular |
| Body | 1rem | 400 |
| UI text | 0.9375rem | 500 to 600 |
| Labels and meta | 0.8125rem | 500, sentence case |

### Shape and depth

- **No capsules.** Buttons, navigation, segmented controls and the theme switch
  are rounded rectangles with 10px corners (9px inside a 12px track); fields
  12px; tags, lift badges and rank badges 6px; cards 20px; landing tiles and
  screens 28px. Only thin bars and meters keep rounded ends.
- Light cards lift on a soft, tinted shadow; dark cards on a lighter surface and
  a hairline. Glass (a blurred backing layer) is used only for the header and the
  phone tab bar.

### Charts

- **Run charts**: a 2px line in the metric's colour with a soft gradient fill, a
  dashed moving-average line with its value, a band per song (the best in volt,
  the biggest drag in coral) and a **song lane** underneath, one block per song,
  named when wide enough.
- **Scrubbing** (`static/js/pages/run.js`): pointer, finger or arrow keys move a
  guide across pace, the lane and heart rate together, with dots on both lines
  and a floating readout of the time, pace, heart rate, song and lift.
- **Bars**: rounded, this week drawn stronger; lifts as volt and coral bars.
- Geometry is still computed on the server in percentages
  (`runnify/services/charts.py`), so charts appear without scripts and need no
  inline styles.

### Icons and the favicon

- The icon sprite is redrawn with round caps and joins at 1.8px, with new icons
  for trends, replay, headphones, the gauge, skips and the theme switch.
- The favicon is a song lane read as levels: four bars on a near-black tile, the
  tallest in volt. `scripts/build_icons.py` draws it with the standard library,
  as a rounded favicon and as full-square app icons inside the maskable safe zone.

## What changed, page by page

| Page | Before | After |
|---|---|---|
| Landing | A tilted results sheet, a results ticker, an accordion, stacking method sheets | A run replay in the hero; a four-step story that draws itself; a bento of real sample results; a session picker that switches sample playlists without scripts; a set-up timeline; privacy promises; questions; a closing panel over the run's pace line |
| Dashboard | Setup steps, a latest-run sheet, power songs, weeks | A greeting; set-up progress as a ring; the latest run with a pace chart over its song lane; three highlights; twelve weeks with this week stronger; power and drag songs |
| Runs | One table | The same table under month headings, like a training log |
| A run | Stats, a black trace, a table | Stats with a sentence naming the fastest and slowest songs; pace and heart-rate charts with fills, average lines and the song lane; scrubbing with a readout; the song results |
| Insights | Ranked lists in sheets | Highlights in sentences first, then ranked lists with size bars, "where songs work hardest" with a 1x marker, and the method |
| Playlists | Session radio cards, a list | Session cards that tick and light their shape; saved playlists with covers drawn from their session |
| Friends | A ranked table | Rank badges and distance bars against the leader |
| Connections, import, settings, sign-in, legal, errors | Ruled sheets | Cards, rounded fields, a raised sign-in card, a rounded dropzone, rounded legal tables |

## Motion

The rule: **every movement shows something the product does.** Nothing fades in
as you scroll, and nothing moves under `prefers-reduced-motion`.

### Landing page (`static/js/pages/home.js`, GSAP and ScrollTrigger, vendored)

| Moment | What moves | Timing | Why |
|---|---|---|---|
| Headline | Words rise once from behind a clip | 1.05s each, 50ms apart, expo out | Draws the eye to the promise |
| Run replay | A playhead walks the pace line; the line draws behind it; each song lights up in the lane and plays in "Now playing" with its lift; distance and time count up | 9s, linear, starts 0.7s after load, pauses off screen, Replay button | Shows the product's one mechanism in a glance |
| Replay end | Settles on the fastest song; the "Now playing" row nudges | 0.5s | Lands the result |
| Story 1 | The pace line draws left to right | 1.8s, power2 in-out, on reaching the step | "Your pace, second by second" |
| Story 2 | Song bands and the lane sweep in from the start of the run | 1.6s | "Each one lands on the exact seconds" |
| Story 3 | The five minutes either side open out from the best song; its lift counts up from zero | 1.2s and 1.1s | "Compared with the minutes around it" |
| Story 4 | The best ranked song is struck with volt | 0.75s | "Ranked, with the evidence" |
| Session picker | The picked session's bars grow from the baseline (CSS only) | 0.6s, 30ms apart | Shows the session's shape |
| Closing panel | The sample run's pace line draws behind the words | 2.4s | A last look at the product's material |

Details:

- Only transform, opacity of the headline container, SVG clip rectangles and
  `clip-path` are animated; nothing animates layout.
- Story steps hold their words and picture on wide screens with CSS
  `position: sticky`, so nothing is pinned by script.
- If GSAP is missing the page is simply shown; if the page script never arrives,
  a CSS fallback reveals the headline after 2.5s.
- Without scripts, or with reduced motion, every chart is drawn complete and the
  replay card shows the finished run.

### App

- State changes only: 120ms for colour, 200ms for presses and menus, buttons
  scale to 0.98 when pressed, the account menu scales in from its corner,
  notices drop in when a page loads with one.
- The run page's scrubbing follows the pointer exactly, with no easing.
- No entrances, no scroll effects, no chart animations.

## Accessibility, privacy and content checklist

| Item | Status | Where |
|---|---|---|
| Colour contrast | 74 token pairs pass AA in both themes; a rendered scan of every page found nothing below AA in light or dark | `scripts/check_contrast.py`, run in CI |
| Alt text on images | The site has no raster images; every chart is `role="img"` with a written summary; decorative SVG is hidden from assistive technology | `templates/macros/charts.html` |
| Privacy policy page | Present | `/privacy` |
| Terms page | Present | `/terms` |
| Cookie policy | Present, now listing the stored appearance choice | `/cookies` |
| Cookie consent | Not needed: two strictly necessary cookies and one setting stored only at the runner's request; the policy explains why | `/cookies` |
| Third-party embeds | None: every page, font and script is served by Runnify; the only outside links are Spotify's privacy page and the Irish Data Protection Commission | templates |
| Tracking | None: no analytics, ads or third-party scripts; the Content-Security-Policy allows only the site itself | `runnify/security/headers.py` |
| Form consent | Sign-up asks separately for the terms and for processing heart-rate data | `templates/auth/register.html` |
| Only necessary data | Name, email and password at sign-up; only songs that played during runs are kept | `PRODUCT.md`, the privacy policy |
| Clear button labels | Every control has a visible label or an accessible name; icon-only buttons are named | checked on every page |
| Keyboard-friendly forms | Labels above fields, errors tied with `aria-describedby`, visible focus rings, Enter submits; checked by signing in with the keyboard | `templates/macros/ui.html` |
| Keyboard everywhere | Native disclosures for menus and questions; radios for the session picker; the run chart scrubs with the arrow keys | |
| No purple gradients | None; the only gradients are faint volt washes on dark product screens | |
| No pill buttons | None; controls are rounded rectangles | `static/css/ui/components.css` |
| No vague hero text | "Find the songs that make you run faster." with a 20-word explanation | landing page |
| No fake reviews or metrics | None; all demonstration data is labelled sample data, computed by the real engine from simulated runs | `runnify/content/sample.py` |
| No fade-in on scroll | Removed; see Motion | `static/js/pages/home.js` |
| No emoji icons | None; one SVG sprite | `static/img/icons.svg` |
| No "made with AI" tag | None | |
| No em dashes | None in the app or the docs | checked by search |
| No AI-sounding copy | Copy reviewed; two lines that overpromised were corrected | |
| Favicon | New mark and app icons | `scripts/build_icons.py` |

## Checks run

- `uv run pytest`: 285 tests pass.
- `uv run ruff check .` and `uv run ruff format --check .`: clean.
- `uv run python scripts/check_contrast.py`: 74 of 74 pairs pass.
- In the browser, signed in as the demo account and signed out: every page at
  1024px and at 375px, in light and dark, with no sideways scrolling on phones;
  the theme switch in both directions; the run chart with the arrow keys; the
  landing page's replay, story and session picker; sign-in with the keyboard.
- Not checked: a screen reader end to end, and reduced motion in a browser (the
  code paths were reviewed; the browser here can't emulate the setting).

## What comes next

Ideas from the research that fit Runnify, not yet built:

1. **A page for each song**: every play as a dot across runs with a trend line,
   the way Strava draws matched runs, plus its heart-rate effect and skips.
2. **"Needs one more run" states**: show songs heard on one run with how much
   more evidence they need, as Garmin and Apple state data thresholds.
3. **Range controls on the dashboard's weeks**: weeks, months and a year, as on
   Apple's detail pages.
4. **Grade-adjusted pace** for hilly runs (a scoring change), as Strava does, so
   a song isn't blamed for a hill.
5. **A shareable "run soundtrack" card**: the replay as an image, for stories.
6. **A weekly friends leaderboard** beside the monthly one.
7. **Photography**: the landing page has no photos because none exist that
   Runnify may use. Two or three real photos of a runner with a watch and
   headphones would warm the hero and the closing panel.
8. **Phosphor icons** (MIT licence) in place of the hand-drawn sprite, which
   needs the icon files downloaded and vendored.
