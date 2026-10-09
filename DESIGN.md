---
name: Runnify
description: "Each run published as an official results sheet, with every song ranked in ruled rows by how it changed the runner's own pace."
colors:
  paper: "#ffffff"
  board: "#eef0f2"
  ink: "#111111"
  ink-2: "#474747"
  ink-3: "#626262"
  rule: "#d9dbde"
  rule-strong: "#b9bcc0"
  field: "#767676"
  highlight: "#e8ff3a"
  highlight-soft: "#f5ffbf"
  pen: "#c4211a"
  pen-soft: "#fdecea"
  go: "#0c7238"
  go-soft: "#e7f3ec"
  on-ink: "#ffffff"
  on-ink-2: "#b4b4b4"
  on-ink-rule: "#3a3a3a"
  ink-raised: "#262626"
  pen-on-ink: "#ff8a80"
typography:
  display:
    fontFamily: "Geist, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "clamp(2.6rem, 1.35rem + 4.6vw, 5.4rem)"
    fontWeight: 800
    lineHeight: 0.95
    letterSpacing: "-0.04em"
  headline:
    fontFamily: "Geist, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "clamp(2rem, 1.45rem + 2vw, 3rem)"
    fontWeight: 750
    lineHeight: 1.05
    letterSpacing: "-0.04em"
  title:
    fontFamily: "Geist, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "clamp(1.5rem, 1.25rem + 0.9vw, 1.875rem)"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.03em"
  title-md:
    fontFamily: "Geist, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "1.375rem"
    fontWeight: 750
    lineHeight: 1.25
    letterSpacing: "-0.03em"
  title-sm:
    fontFamily: "Geist, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.02em"
  lede:
    fontFamily: "Geist, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: "normal"
  body:
    fontFamily: "Geist, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: "normal"
  body-sm:
    fontFamily: "Geist, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: "normal"
  button:
    fontFamily: "Geist, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 650
    lineHeight: 1.1
    letterSpacing: "-0.005em"
  label:
    fontFamily: "Geist, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 650
    letterSpacing: "0.06em"
  tag:
    fontFamily: "Geist, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 700
    lineHeight: 1.4
    letterSpacing: "0.06em"
  rank:
    fontFamily: "Geist, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 800
    letterSpacing: "-0.03em"
    fontFeature: '"tnum"'
  figure:
    fontFamily: "Geist, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "clamp(1.75rem, 1.4rem + 1.2vw, 2.5rem)"
    fontWeight: 750
    lineHeight: 1
    letterSpacing: "-0.04em"
    fontFeature: '"tnum"'
rounded:
  none: "0px"
  radius: "2px"
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
components:
  button:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.button}"
    rounded: "{rounded.radius}"
    padding: "0 24px"
    height: "44px"
  button-hover:
    backgroundColor: "{colors.highlight}"
    textColor: "{colors.ink}"
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    typography: "{typography.button}"
    rounded: "{rounded.radius}"
    padding: "0 24px"
    height: "44px"
  button-primary-hover:
    backgroundColor: "{colors.highlight}"
    textColor: "{colors.ink}"
  button-danger:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.pen}"
    typography: "{typography.button}"
    rounded: "{rounded.radius}"
    padding: "0 24px"
    height: "44px"
  button-danger-hover:
    backgroundColor: "{colors.pen}"
    textColor: "{colors.paper}"
  button-quiet:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    typography: "{typography.button}"
    padding: "0 8px"
    height: "40px"
  button-quiet-hover:
    backgroundColor: "{colors.highlight}"
  button-disabled:
    backgroundColor: "{colors.board}"
    textColor: "{colors.ink-3}"
  button-sm:
    padding: "0 16px"
    height: "36px"
  button-lg:
    padding: "0 32px"
    height: "56px"
  input:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.radius}"
    padding: "12px 16px"
    height: "48px"
  checkbox:
    backgroundColor: "{colors.paper}"
    rounded: "{rounded.radius}"
    size: "22px"
  checkbox-checked:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
  tag:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    typography: "{typography.tag}"
    rounded: "{rounded.radius}"
    padding: "2px 8px"
  tag-ink:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
  tag-go:
    textColor: "{colors.go}"
  tag-pen:
    textColor: "{colors.pen}"
  lift-up:
    backgroundColor: "{colors.highlight}"
    textColor: "{colors.ink}"
    rounded: "{rounded.radius}"
    padding: "1px 8px"
  lift-down:
    backgroundColor: "transparent"
    textColor: "{colors.pen}"
    padding: "1px 8px"
  lift-flat:
    backgroundColor: "{colors.board}"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.radius}"
    padding: "1px 8px"
  sheet:
    backgroundColor: "{colors.paper}"
    rounded: "{rounded.none}"
  sheet-head:
    typography: "{typography.title-sm}"
    padding: "16px 24px"
  sheet-body:
    padding: "24px"
  results-head:
    textColor: "{colors.ink-2}"
    typography: "{typography.label}"
    padding: "12px 16px"
  results-cell:
    typography: "{typography.body-sm}"
    padding: "12px 16px"
  results-row-best:
    backgroundColor: "{colors.highlight}"
    textColor: "{colors.ink}"
  results-row-hover:
    backgroundColor: "{colors.highlight-soft}"
  rank-row:
    padding: "12px 8px"
  rank-row-best:
    backgroundColor: "{colors.highlight}"
    textColor: "{colors.ink}"
  stat-value:
    typography: "{typography.figure}"
  notice:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.radius}"
    padding: "12px 12px 12px 16px"
  notice-error:
    backgroundColor: "{colors.pen-soft}"
  notice-success:
    backgroundColor: "{colors.go-soft}"
  app-header:
    backgroundColor: "{colors.paper}"
    height: "64px"
  app-tab-bar:
    backgroundColor: "{colors.paper}"
    height: "64px"
  nav-link:
    textColor: "{colors.ink-2}"
    padding: "0 12px"
    height: "64px"
  nav-link-current:
    textColor: "{colors.ink}"
  segmented-current:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    height: "40px"
  avatar:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.radius}"
    size: "40px"
  ink-band:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.on-ink}"
---

<!-- Recorded from the built code on 9 October 2026, after the landing page's finish review (disposition: ship, scoped to its scored fixes). Code-led build with no comps. Where a screenshot and the code differ, the code wins. -->

# Design system: Runnify

## Overview

**Creative North Star: "The Official Results Sheet"**

Runnify publishes every run the way a race posts its official results. The songs are the entrants, ranked in ruled rows by how much faster or slower the runner went while each one played, against their own pace in the same run. Every screen is a printed sheet: white paper, near-black print, hairline rules between rows and heavy ink rules under the headers, with positions set heavy like race numbers. Product pages are working sheets; the landing page posts a sample one.

Two marks sit on top of the print, the marks a runner makes on posted results. Highlighter yellow strikes through the best row and backs every lift. Red pen marks the drags, as red ink and a line through the song's name. Everything else is ink on paper, and a quiet green only reports that something is connected or done. Density is that of a results table: compact rows, short uppercase column heads, and tabular figures that line up down the page.

The world refuses the dark neon fitness dashboard. It is light only, flat and square: no shadows, glass or gradients, no corner rounder than 2px, and no emoji. Choreographed motion belongs to the landing page alone and stops entirely under reduced motion, and every page reads and works without JavaScript.

**Key Characteristics:**
- White results paper and near-black ink carry almost every surface; a grey noticeboard and full-width ink bands are the only other grounds.
- Highlighter yellow means best (and lift), red pen means drag (and error), solid ink means selected.
- Hairline row rules, a firmer rule under every fifth row, and heavy 2px ink rules along the top of every sheet and under every column head.
- One typeface, Geist, with tabular figures for every number and positions set like race numbers.
- Flat and square: no shadows, glass or gradients, 2px corners on controls, square-cut sheets.
- Numbers formatted one way everywhere, down to the true minus sign in a drag.
- Motion only on the landing page, none under reduced motion, and nothing that needs JavaScript to read.

## Colors

A print palette: paper and ink do almost all the work, two marking colours carry the meaning (highlighter for the best, red pen for drags), and one green reports status. The system is light only, and all 21 colour pairs it uses pass WCAG 2.2 AA in the project's contrast check: 4.5:1 for text, 3:1 for control borders and meaningful graphics.

### Primary
- **Results ink** (#111111): The print itself. Body text and headings, the 2px heavy rules, primary buttons, checked boxes, the current tab's rule, chart traces and bars, and the full-width ink bands on the landing page (the results ticker and the privacy band). 18.9:1 on paper.

### Secondary
- **Highlighter yellow** (#e8ff3a): The runner's highlighter. It fills the best row of a results table and the top power song, backs every lift figure, underlines "Run" in the wordmark, wipes across a button on hover, backs a hovered link, marks selected text and rings a focused field. Ink on it reads at 16.9:1, and on the ink bands it becomes the colour of lifts. Never text on paper.
- **Highlighter wash** (#f5ffbf): A lighter pass of the highlighter for hovered table rows that lead somewhere, the dropzone while a file is over it, and hovered rows in ruled section lists.

### Tertiary
- **Red pen** (#c4211a): Drags and errors. Drag figures and the line through a drag song's name, field errors and invalid borders, danger buttons and the danger row in settings, failed states, and negative bars in charts. 5.9:1 on paper.
- **Red pen wash** (#fdecea): The ground of error notices and failed uploads, and the band behind the slowest song in a run chart. Never behind a drag figure.
- **Red pen on ink** (#ff8a80): Drag figures on the ink bands, 8.3:1 on ink.
- **Finish green** (#0c7238): Status only: connected and done tags, the success notice border and icon, and the ticks beside the upload page's privacy promises. 6.0:1 on paper.
- **Finish green wash** (#e7f3ec): The ground of success notices.

### Neutral
- **Results paper** (#ffffff): The page, and every sheet, panel, field and menu on it.
- **Noticeboard grey** (#eef0f2): The board the sheets are pinned to: alternate landing page sections, the context panel beside sign-in forms, notes, disabled buttons, flat lifts, alternate song bands in charts and meter tracks.
- **Secondary print** (#474747): Ledes, column heads and stat labels, step and empty-state text, inactive navigation labels and flat lift figures. 9.3:1 on paper.
- **Meta print** (#626262): Meta lines, hints, units, run counts, chart labels, captions and the legal line. 6.1:1 on paper and 5.3:1 on the board.
- **Hairline rule** (#d9dbde): The 1px rule between rows, around sheets and between cells; also muted bars. Decorative, so it never carries meaning alone.
- **Fifth-row rule** (#b9bcc0): The firmer rule under every fifth row of a results table, as on printed results, and between steps set on the board.
- **Field grey** (#767676): Form control borders at 4.5:1 (above the 3:1 needed), disabled button borders, the dashed gap row in a shortened table and the dropzone outline.
- **Print on ink** (#ffffff): Text on the ink bands.
- **Secondary print on ink** (#b4b4b4): Positions and supporting text on the ink bands, 9.1:1 on ink.
- **Ink band rule** (#3a3a3a): The rules between items on the ink bands.
- **Raised ink** (#262626): A control on an ink band under the pointer, such as the ticker's pause toggle.

### Named rules

**The Best Not Selected Rule.** Highlighter yellow means best: the winning row, the top power song and every lift. On controls it is only the hover and focus mark. A selected option, the current page and a checked box are always solid ink.

**The Red Pen Rule.** A drag is written in red ink: a red figure behind a down arrow and, where drag songs are listed, a red line through the name. It never sits on a tinted chip or a red row; the red wash is kept for error grounds and the slowest band in a chart.

**The Never Alone Rule.** Colour is never the only signal. Every lift and drag carries an arrow and a sign, drag songs in lists are struck through as well as red, and assistive technology hears "faster" or "slower". A new colour pair joins the contrast check before it ships.

## Typography

**Display Font:** Geist (with ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif)

**Body Font:** Geist (with ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif)

**Mono Font:** ui-monospace (with SFMono-Regular, Menlo, Consolas, monospace)

**Character:** One family does every job through weight and tracking. Headlines and positions are heavy (750 to 800) and tightly tracked, like the bold print on a results board; body text is plain and open; column heads and tags are short, uppercase and tracked out. Every number uses tabular figures, so paces and lifts line up down a column.

Geist is self-hosted as a single variable font file (weights 100 to 900) under the SIL Open Font License and preloaded on every page. It was chosen for its tabular figures and its open licence: only open-licence fonts were approved, which ruled out the first pick, Cabinet Grotesk. The impeccable detector's overused-font rule is waived for Geist on purpose. The monospace stack appears only for codes and secrets, such as a two-step set-up key.

### Hierarchy
- **Display** (800, 2.6rem to 5.4rem fluid, line-height 0.95, -0.04em): The closing call to action on the landing page. The landing hero headline is a close variant: 750, 2.6rem to 4.6rem, line-height 0.98 and -0.035em, held to 16ch so it sets in two lines.
- **Headline** (750, 2rem to 3rem fluid, line-height 1.05, -0.04em): Landing section titles, sign-in and sign-up titles, legal documents and error pages. Product page titles use the same size at 700 with line-height 1.08 and -0.035em.
- **Title** (700, 1.5rem to 1.875rem fluid, line-height 1.25, -0.03em): The base second-level heading. On the landing page it sets the sample findings (650, line-height 1.2), the verdict song (750) and the positions on the sample sheet (800).
- **Title medium** (750, 1.375rem, line-height 1.25, -0.03em): Landing sheet and card titles, wide accordion step titles and section headings in legal documents.
- **Title small** (700, 1.125rem, line-height 1.25, -0.02em): Sheet and panel titles, empty-state titles and step titles; third-level headings at 650.
- **Lede** (400, 1.125rem, line-height 1.55): The paragraph under a section, page or form title, in secondary print, up to 56ch.
- **Body** (400, 1rem, line-height 1.55): Running text, held to a 66ch measure. Legal documents set it at 1.0625rem with line-height 1.65.
- **Small** (400, 0.875rem, line-height 1.55): Table cells, meta lines, hints, navigation and most supporting text. Buttons use it at 650 with -0.005em.
- **Label** (650, 0.75rem, 0.06em, uppercase): Column heads, stat labels and legal table heads, in secondary print. The landing sample sheet's field labels drop to 0.6875rem with 0.08em.
- **Tag** (700, 0.6875rem, 0.06em, uppercase): Status tags and sample tags.
- **Rank** (800, 1.125rem, -0.03em, tabular): Positions in results tables, set like race numbers; 1.375rem in ranked lists.
- **Figure** (750, 1.75rem to 2.5rem fluid, line-height 1, -0.04em, tabular): Stat values such as distance, time and pace, with the unit after the figure at 0.875rem and 600 in meta print.

### Named rules

**The Tabular Figures Rule.** Every number that could sit in a column uses tabular figures: paces, times, distances, lifts, positions, counts and chart labels.

**The One Format Rule.** A number reads the same on every page. Pace is minutes and seconds per km (4:52). Durations read 48:12 or 1:02:45. Distances carry two decimals (10.02 km). Lifts are whole seconds per km with a sign and a non-breaking space before the unit: +9 s/km, −5 s/km with a true minus sign (U+2212), and ±0 s/km for no change. Dates read Mon 5 Oct 2026 and clock times 07:05. A missing value is a single hyphen.

**The Race Number Rule.** Positions and step numbers are the heaviest type on a sheet (800), tightly tracked and larger than the row around them.

## Layout

Content sits in a centred column up to 1240px wide with a fluid gutter of 16px to 40px. Long text keeps to a 66ch measure and sign-in forms to 30rem. Spacing runs on a 4px base; the steps used most are 24px, 12px, 8px and 16px, so sheets are tight inside, while landing page sections carry 96px above and below (128px from 1024px).

Pages are a single column on phones and split from 960px or 1024px: a 12-column grid for the landing hero and the dashboard, a 1.65 to 1 main and side split, and a 14rem list of sections beside settings and legal documents. Separate sheets sit 24px apart; cells that belong together share their rules instead.

- **Breakpoints:** 560px (below it, table cells tighten and the hero buttons stack), 760px (optional table columns, four-up stats, the full public navigation), 900px (the app navigation moves from the bottom tab bar into the header), 960px (two-column splits and the horizontal steps accordion) and 1024px (the main wide layout). A few components keep a single breakpoint of their own (420px, 480px, 600px, 640px, 680px and 1100px).
- **Public pages:** a sticky 64px header with a hairline under it: the wordmark on the left, links and the sign-up button on the right. Below 420px the button's label shortens from "Create free account" to "Sign up".
- **App pages:** a sticky 64px header holds the wordmark, the navigation, an Import button and the account menu. Below 900px the navigation becomes a fixed 64px tab bar along the foot of the screen (plus the safe area), and page content keeps clear of it. Below 600px the Import button shows its icon only.
- **Page head:** the page title with a meta line under it and actions on the right, closed by a heavy ink rule 32px above the content.
- **Tables:** scroll sideways inside their sheet rather than squeezing; optional columns drop out below 760px.
- **Landing page:** sections alternate paper, noticeboard grey and one ink band (the privacy commitments), with the ink results ticker directly under the hero.

### Named rules

**The Ruled Board Rule.** Cells that belong together share one set of rules. Stats, the landing sample board, steps, ranked lists and settings rows draw hairlines between cells under one heavy rule along the top, instead of boxing each cell or leaving gaps.

## Elevation & Depth

The system is flat paper. There are no shadows, no glass or blur and no gradients. Depth comes from four things only: the weight of the rules (1px hairlines against 2px ink rules, and 6px ink header rules on the landing page's sample sheets); the step from paper to noticeboard grey to an ink band; a border on anything that sits over the page (the account menu has a 2px ink border, the sticky headers a hairline); and, on the landing page only, overlap: the sample sheet is pinned at a slight tilt over the ticker, and the method sheets stack as you scroll.

Where the stylesheets use the box-shadow property, it always has zero blur and draws a flat rule or stroke, never a shadow:

- **Field focus:** a 2px ink ring with a 6px highlighter halo outside it.
- **Invalid field:** a 1px red pen ring.
- **Current navigation item:** a 3px ink rule under it in the header, or along its top edge in the phone tab bar.
- **Selected card:** a 5px ink rule along the top of a chosen session card, and 4px across the open step of the landing accordion.
- **Highlighter underline:** a stroke covering the lower 38% to 55% of a word: "Run" in the wordmark, a power song named in a finding, the winning song in the verdict.

### Named rules

**The Flat Paper Rule.** Nothing floats. A surface is paper, noticeboard grey or ink, and it is set apart from its neighbours by rules, never by a shadow. Any box-shadow in the stylesheets has zero blur and draws a rule or a highlighter stroke.

**The Opaque Sheet Rule.** Sheets are paper, so they never show through. Where sheets overlap, each stays fully opaque, and a receding sheet fades only its contents.

## Shapes

The form language is ruled and square. 2px is the only radius, and it goes on every control and mark: buttons, fields, selects, checkboxes, tags, lift marks, notices, segmented controls, menus, the avatar, step numbers, dropzones and session cards. Sheets, panels, boards, tables, stats, charts and meters are square-cut paper. Nothing is round: the avatar is a 40px square of initials, and step numbers are squares (32px in lists, 44px and 64px on the landing page).

Rules carry the structure:

- **Hairline:** 1px hairline grey between rows, around sheets and between cells.
- **Fifth-row rule:** 1px in the firmer grey under every fifth row of a results table.
- **Heavy rule:** 2px ink along the top of every sheet and stat grid, under every column head and page head, and along the top of the footer and the phone tab bar.
- **Header rule:** 6px ink along the top of the landing page's sample and method sheets; 3px along the top of a notice or upload status, in its own colour.
- **Dashed rules:** 1px field grey for the gap row in a shortened table; 2px for the dropzone (field grey) and the recovery code frame (ink).
- **Frame:** a 4px ink frame round an error page's status code, printed like a race number.

Icons are inline SVG from one sprite, drawn on a 24-unit grid with a single 2px stroke, square caps and mitred joins, in the current text colour. They sit at 1.15em by default and 22px in the tab bar. There are no glyph or emoji icons, and no Garmin or Spotify logos.

Charts share the geometry: a 2px ink trace (the one line with round joins and caps), a 2px ink baseline, hairline gridlines, square-ended bars and 14px square legend swatches.

The only rotation in the system is the landing page's sample sheet, pinned 1.25 degrees askew on phones and 2 degrees on wide screens. The favicon repeats the sheet: an ink square with two white rules and a highlighter band.

### Named rules

**The Two Pixel Rule.** No corner is rounder than 2px. Controls take 2px, sheets and panels stay square, and there are no pills, round avatars or round badges.

**The Across Not Down Rule.** Emphasis rules run across: along the top of a sheet, notice, status or selected card, or under the current navigation item. Nothing carries a coloured stripe down its side.

## Components

Components are Jinja macros and plain CSS in cascade layers (reset, base, layout, components, pages, utilities), with no framework or build step. Templates never carry inline styles, scripts or event handlers, because a strict Content-Security-Policy is enforced and tested; behaviour is attached from script modules through data attributes, and chart geometry is computed on the server in percentages so nothing needs an inline style.

### Buttons
- **Character:** printed tickets: a 2px ink outline, short bold labels, and a highlighter stroke that wipes across on hover.
- **Shape:** squared-off corners (2px radius) and a 2px ink border; 44px high with 24px side padding, small 36px with 16px, large 56px with 32px and 1rem labels. Labels are 0.875rem at 650.
- **Primary:** ink fill with paper text, for the main action in a view: Create free account, Build a playlist, Create account.
- **Secondary:** paper fill with ink text and border: See a sample result, Full results, Import.
- **Hover:** a highlighter stroke wipes in from the left over 220ms on the system easing; a primary button turns to ink text on highlighter.
- **Focus:** the shared 3px ink outline, offset 3px.
- **Danger:** red pen border and text, and a red pen stroke with paper text on hover. Destructive forms also ask for confirmation.
- **Quiet:** underlined text with no border, 40px high, backed by the highlighter on hover: Disconnect, Decline, Delete.
- **Disabled:** noticeboard grey fill, field grey border and meta print text, with no hover stroke.
- **Icon only:** a 44px square (36px small) with an accessible name.

### Tags
- **Style:** uppercase 0.6875rem at 700 with 0.06em tracking, a 1px border in the text colour, 2px corners and 2px by 8px padding.
- **Default:** an ink outline for neutral states (Not connected, Importing, Off, You) and the Sample tag on landing page findings.
- **Ink:** solid ink with paper text, for Sample data on the landing results sheet and for counts of waiting requests.
- **Status:** finish green for done states (Connected, Imported, On, In Spotify) and red pen for Failed.

### Lift marks
The figure that matters most on any sheet: how much faster or slower the runner went while a song played.
- **Lift:** highlighter ground, an ink figure at 700, an up arrow and a plus sign (+12 s/km).
- **Drag:** a red pen figure on no ground, a down arrow and a true minus sign (−10 s/km).
- **Flat:** noticeboard grey ground and secondary print with no arrow (+1 or ±0 s/km). A change under 1 s/km counts as flat.
- **Shape:** 2px corners and 1px by 8px padding, with tabular figures that never wrap. Under a column head that carries the unit, the figure drops it.
- **Evidence:** the sample size sits beside or under the figure in 0.75rem meta print (11 runs).

### Sheets and panels
- **Corner style:** square.
- **Background:** results paper.
- **Border:** a 1px hairline on the sides and foot, and a 2px ink rule along the top.
- **Shadow strategy:** none (see Elevation & Depth).
- **Head:** 16px by 24px with a hairline under it: the title on the left, a 0.875rem meta line in meta print on the right.
- **Internal padding:** 24px, or flush when the body is a table, list or stat grid.
- **Foot:** 12px by 24px with a hairline above, in small meta print.
- **Landing sheets:** the sample results sheet and the method sheets use a 1px ink border with a 6px ink rule along the top.

### Results table
The signature component: a run's songs ranked like finishers.
- **Columns:** position, track (the song at 650 with the artist under it in meta print), the time it came on, an optional heart-rate change and the lift. Units sit in the column head in lowercase meta print (s/km, bpm), so cells carry bare figures.
- **Head row:** label type in secondary print over a 2px ink rule.
- **Rows:** 12px by 16px cells (8px at the sides below 560px), a hairline under each row and the firmer rule under every fifth. Figures are right-aligned and never wrap.
- **Best row:** the whole row in highlighter yellow.
- **Hover:** a row that leads to a run takes the highlighter wash, and a click anywhere on it follows its link; the link stays the real target.
- **Shortened:** the top rows, a dashed gap row saying how many more songs there are, then the last-placed row.
- **Phones:** optional columns drop out below 760px, and the table scrolls sideways rather than squeezing.

### Stats
- **Style:** a grid of cells ruled with hairlines under a 2px ink rule; two across, then three or four from 760px.
- **Label:** label type in secondary print.
- **Value:** figure type, with the unit after it at 0.875rem and 600 in meta print.
- **Note:** an optional 0.75rem meta line under the value.

### Ranked lists
- **Rows:** the position (1.375rem, 800), the name at 650 with its detail under it in meta print, and the lift with its run count on the right, each row on a hairline.
- **Best:** the first power song's row in highlighter yellow, its meta lines stepping up to secondary print.
- **Drag songs:** the name struck through with a 2px red pen line, beside a red pen lift.

### Inputs and fields
- **Style:** a label above (0.875rem, 650) and an optional hint under it in meta print, then a 48px field with 12px by 16px padding, a 1px field grey border, 2px corners, a paper ground and 1rem text.
- **Hover:** the border turns ink.
- **Focus:** an ink border, a 2px ink ring and a 6px highlighter halo, in place of the outline.
- **Error:** a red pen border and ring, and a red pen message with an alert icon under the field, tied to it for assistive technology.
- **Password:** an underlined Show or Hide button inside the field on the right; its label always says what it will do next.
- **Checkbox:** a 22px square with a 2px ink border and 2px corners; checked, it fills with ink and a paper tick.
- **Select:** drawn as a field, with a square-capped chevron.
- **Codes:** one-time codes at 1.375rem and 650, tabular, with 0.18em tracking.
- **Dropzone:** a 2px dashed field grey frame that turns ink over the highlighter wash while a file is over it, and solid ink once a file is chosen.
- **Session cards:** radio choices drawn as cards with a 1px field grey border and 2px corners; the chosen card gains an ink edge, a 5px ink top rule and an ink fill in its session shape.

### Navigation
- **Wordmark:** "Runnify" at 1.375rem and 800 with tight tracking, "Run" underlined by a highlighter stroke. It is the only brand mark in the interface.
- **Public header:** links at 0.875rem and 550 with no underline until hover, then the primary sign-up button.
- **App navigation:** on wide screens, a row of text links in the 64px header at 0.875rem and 600 in secondary print, with the current page in ink over a 3px ink rule. On phones, a fixed tab bar of five equal tabs, 22px icons over 0.6875rem labels, with the current tab in ink under a 3px ink rule.
- **Account menu:** a 40px square avatar of initials opens a panel with a 2px ink border and 40px rows that take the highlighter on hover. It is a native disclosure that closes on Escape, an outside click or focus leaving.
- **Segmented control:** a 2px ink frame around 40px options divided by 2px ink rules; the current option is solid ink with paper text, and hover is highlighter. Below 480px it becomes a two by two grid.
- **Section lists:** settings and legal pages list their sections as bordered links on phones and, from 1024px, as a sticky ruled list under a heavy rule with the highlighter wash on hover; legal pages mark the current document in solid ink.
- **Links:** underlined at 1px with a 0.2em offset; on hover the underline thickens to 2px and the highlighter backs the text.
- **Focus:** a 3px ink outline offset 3px on every interactive element; on the ink band, the ticker's toggle uses a highlighter outline.

### Notices
- **Style:** a 1px border with a 3px top rule in the notice's colour, 2px corners, an icon, the message at 0.875rem and 550, and a 32px dismiss button.
- **Default:** an ink border on paper, for information.
- **Error:** a red pen border on the red pen wash, announced at once.
- **Success:** a finish green border on the green wash.

### Charts
- **Drawing:** inline SVG computed on the server in percentages, so a chart takes its size from the stylesheet and appears without scripts. Plot heights are 150px compact, 200px by default and 240px tall (300px from 760px).
- **Marks:** a 2px ink trace, hairline gridlines, a 2px ink baseline, ink bars with red pen bars for negative values, and 0.75rem tabular labels in meta print.
- **Song bands:** alternate songs in noticeboard grey, the fastest song in highlighter and the slowest in the red pen wash; legends use 14px square swatches with a 1px border.
- **Meters:** an 8px noticeboard grey track with an ink fill, red pen when negative.
- **Reading aid:** on a run page, a pointer guide and readout show the time, pace, heart rate and song at any moment; the chart and the table carry the same facts without it.

### Steps and empty states
- **Steps:** numbered 32px squares with a 2px ink border and 800 figures, with hairlines between steps; a finished step fills with ink and shows a tick.
- **Empty states:** left-aligned: a 1.125rem title at 700, a short explanation in secondary print up to 52ch, and the action that fixes it.

### The highlighter sweep
The signature motion, used on the landing page only.
- **Behaviour:** a highlighter stroke is drawn once across the winning row or song name, left to right, the way a runner marks their own name on posted results. It runs for 750ms on an ease-in-out curve, starts when the row's top passes 80% of the viewport, and waits 0.7s in the hero (for the sheet to settle) or 0.35s elsewhere. When it lands, the static mark takes over.
- **Without motion:** under reduced motion, or without scripts, the mark is simply drawn.

### Landing page motion
- **Scope:** choreographed motion lives on the landing page only. Product pages have state changes alone: 120ms for links and fields and 220ms for the button stroke and disclosure icons, on one easing curve.
- **Entrances:** the hero sheet settles into its tilt over 700ms from 28px lower and 5 degrees of turn; on wide screens the open step's text rises 8px over 420ms.
- **Ticker:** an ink band of sample results runs in a 60s loop. It waits for the hero sweep to land, pauses on hover, on focus and with its pause toggle, and gives screen readers a plain list instead.
- **Stacking:** from 1024px each method sheet scales to 0.94 and fades its contents to 30% as the next sheet slides over it, tied to scroll.
- **Accordion:** on wide screens the open step widens over 560ms, and one step is always open.
- **Reduced motion:** all of it is skipped; transitions collapse to 1ms, and the ticker stands still with no toggle.

## Do's and Don'ts

### Do:
- **Do** build every surface from results paper (#ffffff), noticeboard grey (#eef0f2) or a full-width ink band (#111111), set apart by rules.
- **Do** run a 2px ink rule along the top of every sheet and under every column head, with 1px hairlines (#d9dbde) between rows and the firmer rule (#b9bcc0) under every fifth.
- **Do** fill the best row, or the top power song, with highlighter yellow (#e8ff3a), and back every lift with it beside an up arrow and a signed figure.
- **Do** write drags in red pen (#c4211a): a red figure behind a down arrow, and a 2px red line through the song's name in drag lists.
- **Do** use solid ink for selected, current and checked states.
- **Do** set every number in tabular figures and the shared formats: 4:52 pace, 48:12 durations, 10.02 km, and signed whole s/km lifts with a true minus sign and a non-breaking space before the unit.
- **Do** set positions and step numbers at 800 with tight tracking, larger than the row around them.
- **Do** keep controls at 2px corners and sheets square.
- **Do** mark demonstration data as sample, with a Sample tag or a plain line in the section's lede, and compute it with the real engine.
- **Do** make every page work without JavaScript: native disclosures for menus and accordions, server-drawn charts and a CSS pause toggle for the ticker, with scripts only adding to them.
- **Do** keep templates free of inline styles, scripts and event handlers, and attach behaviour from script modules through data attributes.
- **Do** add any new text or graphic colour pair to the contrast check and hold it to WCAG 2.2 AA.

### Don't:
- **Don't** use shadows, glass, blur or gradients; zero-blur rules and highlighter strokes are the only use of shadow properties.
- **Don't** round anything past 2px: no pills, round avatars, round badges or rounded cards.
- **Don't** use highlighter yellow for selected or current states, or as text on paper.
- **Don't** put a drag on a tinted chip or wash its row in red.
- **Don't** add coloured stripes down the side of a card, notice or row; emphasis rules run along the top.
- **Don't** use emoji or text characters as icons; use the 2px square-capped icon set.
- **Don't** add entrances, sweeps, tickers or scroll effects to product pages, or any motion that survives reduced motion.
- **Don't** rely on colour alone: a lift or drag keeps its arrow and sign, and a drag song in a list keeps its strike.
- **Don't** add a second typeface: Geist sets every role, and the platform monospace appears only for codes.
- **Don't** load fonts, scripts or styles from third parties; Geist and GSAP are self-hosted.
- **Don't** use Garmin or Spotify logos or brand colours; their names only describe the integrations.
- **Don't** build a dark theme or a neon dashboard: the page is always white paper, and large ink areas are the landing page's full-width bands only.
