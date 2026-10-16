# Competitor audit: Apple Health, Strava and Garmin Connect

Research for the October 2026 redesign of Runnify. Each product was studied as
it stands on 16 October 2026, from the companies' own pages, help centres,
design guidelines and press releases, reputable reviews (DC Rainmaker,
the5krunner, 9to5Mac, MacRumors, BikeRadar and others) and the live public
websites. Nobody signed in to any service; app details come from the
companies' own screenshots and documentation. Anything that could not be
confirmed is marked *unverified*. Sources follow each section.

Runnify's position is narrow and different from all three: it joins Garmin
runs with Spotify listening history and ranks every song by how it changed
the runner's pace against their own pace in the same run. None of the three
products does this. The audit is about how they present data, explain it and
make it feel trustworthy, not about copying features.

## Contents

- [The short version](#the-short-version)
- [Apple Health, Fitness and the Workout app](#apple-health-fitness-and-the-workout-app)
- [Strava](#strava)
- [Garmin Connect](#garmin-connect)
- [Side by side](#side-by-side)
- [Runnify before the redesign](#runnify-before-the-redesign)
- [What Runnify takes, and what it leaves](#what-runnify-takes-and-what-it-leaves)

## The short version

| | Apple Health | Strava | Garmin Connect |
|---|---|---|---|
| What it does best | One calm detail template for every metric; findings written as one plain sentence with a number | Synchronised analysis charts; a short "Athlete Intelligence" sentence under the stats | A score, a word, a colour and a one-line action for every metric; honest "needs more data" states |
| Look | Grey grouped page, white cards (about 24pt corners), SF Pro, one hue per data domain | Warm neutrals, Strava orange #FC5200, Boathouse type, 4px corners on web | Dark by default until 2023, now light, dark or system; one colour ladder (purple, blue, green, orange, red) for graded metrics |
| Motion | Brief and tied to real achievements (rings, awards) | Kudos, flyovers, replays; web charts scrub together | Mostly undocumented; carousels and gauges |
| Weak spots | Data spread across Health, Fitness, Vitals and Readiness; opaque trend logic | Upsell on nearly every page; AI summaries that get facts wrong | Dense, many menus; 2024 home called a "glossy brochure"; opaque scores |
| Runnify borrows | The detail template, highlight sentences, light and dark themes | The scrub-everything chart, the plain summary under the stats | Score + word + action, the dashed average line, "needs one more run" honesty |

## Apple Health, Fitness and the Workout app

### Where it stands

- iOS 27 and watchOS 27 shipped in mid-September 2026. Health on iPhone is still
  Summary, Sharing and Browse, now with the Liquid Glass controls introduced in
  iOS 26: a floating glass tab capsule and a round search button.
- A redesigned Health app (Insights, Longevity with a Health Age, Browse) was
  announced on 9 September 2026 and ran in iOS 27.2 betas 1 to 3 for US English
  only. Beta 4 removed it, with a "coming later" notice. Its design is provisional.
- New in September 2026: a Readiness score from 0 to 10 on Apple Watch Series 12
  and Ultra 4, Workout Buddy without the iPhone nearby, and GymKit on iPhone.

### Information architecture

- **Summary** runs top to bottom: a large title with the profile avatar, Pinned
  metrics (reorderable), Trends, Highlights, then "Get More From Health" and
  Articles.
- **Browse** lists categories (Activity, Heart, Sleep, Respiratory, Mobility,
  Hearing, Vitals and others) and drills from category to data type to a detail
  page. Pinned cards and highlights jump straight to the same detail page.
- **Fitness** has Summary, Fitness+, Workout and Sharing, with a customisable
  card grid (rings, steps, sessions, trends, awards, training load, readiness).

### The metric detail page (the pattern most worth borrowing)

- A segmented range control reading **D, W, M, 6M, Y**: a grey track (about
  #EEEEEF), a white selected thumb, black labels. Options vary by metric.
- A **summary header** above the chart: a small grey uppercase label (AVERAGE,
  TIME ASLEEP), the value at about 34pt in regular weight with a smaller grey
  unit, then the date range in grey.
- **The chart**: solid category-colour bars with near-square tops, y labels on
  the trailing side in tertiary grey, three or four light gridlines at round
  values, dashed day dividers. Bar charts start at zero; heart rate does not.
  The whole plot is the scrub target (Apple's Human Interface Guidelines).
- **Below the chart**: Show More data, dismissible tips, Highlights, an About
  card in plain language, Pin to Summary, data sources and units.
- Score pages (Sleep Score) add a segmented donut, a band word ("High") and
  three rows, each with a label, a plain-English detail and points.

### Highlights and trends

- A highlight card is a category glyph and name in the category colour, **one
  bold sentence**, a hairline, then a small visual made for that finding.
  Examples from Apple's screenshots: "In the 3 minutes after your last walk,
  your heart rate went down by 22 beats per minute", with a dot plot.
- The voice: second person, past tense, one finding per card, always a number,
  a unit and a timeframe, no praise words, comparisons only with your own history.
- Trends compare longer and shorter windows (Fitness compares the last 90 days
  with the last 365 and needs 180 days of data). Thresholds are not published
  (*unverified*), and reviewers found the logic opaque.
- Banded scores with published cut-offs: Training Load (Well Below to Well
  Above), Readiness (Recover, Pace Yourself, Ready, Go For It), Sleep Score
  (Very Low to Very High, with components worth 50, 30 and 20 points).

### Workouts

- After a workout, Fitness shows Workout Details, Splits, Heart Rate (with time
  in five zones), Effort and Route. Pressing and holding the pace graph scrubs
  it while the route map traces your position.
- Effort is rated 1 to 10 (Easy, Moderate, Hard, All Out). Training Load draws
  a 7-day line over a 28-day baseline.

### Visual language

- **Type**: SF Pro, Text below 20pt and Display above. Text styles run from
  Large Title 34/41 down to Caption 2 11/13. Section headings bold, category
  labels semibold in the category colour, chart values large and regular.
  SF fonts cannot be embedded in websites.
- **Colour**: one hue per data domain (activity orange-red, heart pink-red,
  sleep indigo, hearing blue), system colours tuned separately for light and dark.
- **Surfaces**: light #F2F2F7 page with white cards; dark #000 page with #1C1C1E
  cards; cards about 24pt round with no shadows and hairline dividers.
- **Liquid Glass** is for the navigation and control layer only, never content.
- **Activity rings**: the guidelines forbid reusing ring imagery for other data.

### Motion

- Apple's motion rules: purposeful, brief and precise; don't animate frequent
  interactions; let people cancel; never make motion the only carrier of
  meaning; respect accessibility settings.
- Celebrations are tied to real achievements: ring closures with a sparkle and a
  haptic, 3D award medals you can turn.
- Marketing pages: dark heroes, inline muted video, scroll-driven text reveals
  and sticky image sequences; easing cubic-bezier(0.4, 0, 0.6, 1) over 240 to
  500ms; several prefers-reduced-motion blocks per page.

### Strengths and weaknesses

- **Best**: one consistent detail template; sentences with numbers; honest data
  thresholds ("needs 7 nights"); restraint.
- **Weak**: data split across Health, Fitness, Vitals and Readiness; opaque trend
  logic; Workout Buddy reported to invent data; the redesign slipped.

Sources: [apple.com/health](https://www.apple.com/health/) ·
[Apple newsroom, Sep 2026](https://www.apple.com/newsroom/2026/09/apple-advances-health-and-fitness-capabilities-using-apple-intelligence/) ·
[MacRumors on iOS 27.2 beta 4](https://macrumors.com/2026/10/13/ios-27-2-beta-4-health-app) ·
[HIG: Charts](https://developer.apple.com/design/human-interface-guidelines/charts) ·
[HIG: Charting data](https://developer.apple.com/design/human-interface-guidelines/charting-data) ·
[HIG: Motion](https://developer.apple.com/design/human-interface-guidelines/motion) ·
[HIG: Typography](https://developer.apple.com/design/human-interface-guidelines/typography) ·
[HIG: Materials](https://developer.apple.com/design/human-interface-guidelines/materials) ·
[HIG: Activity rings](https://developer.apple.com/design/human-interface-guidelines/activity-rings) ·
[Apple Support: Health app](https://support.apple.com/guide/iphone/view-your-health-data-iphe3d379c32/ios) ·
[Apple Support: Readiness](https://support.apple.com/guide/watch/readiness-flx4gnzby346/watchos) ·
[leancrew.com on Health trends](https://leancrew.com/all-this/2024/11/apple-health-trends/) ·
[DC Rainmaker, Apple Watch Series 12 review](https://www.dcrainmaker.com/2026/10/apple-watch-series12-in-depth-review-worth-upgrade.html)

## Strava

### Where it stands

- App tabs since 2021: **Home, Maps, Record, Groups, You**. Home carries a
  swipeable band (Instant Workouts, Weekly Snapshot, Goals, streak) over the feed.
- Recent launches: Athlete Intelligence (beta Oct 2024, out of beta Feb 2025),
  the Activity Details redesign (Apr 2025), Performance Predictions (Apr 2025),
  the Runna acquisition (Apr 2025), the Record redesign (Jul 2025), Instant
  Workouts (Jan 2026), Annual Best Efforts (Apr 2026), Activity Replays in the
  feed (Jun 2026), an Events tab and club messaging (Jul 2026), and trail
  difficulty and iOS widgets (Sep 2026).
- Dark mode shipped in June 2024 with three options: follow the device, always
  light, always dark.

### The feed card

- Avatar, name, date, time, location and device; then the title; then a stat
  triplet of **Distance, Pace, Time** chosen as "the more notable stats"
  (elevation replaces pace on hilly runs); at most one achievement banner; the
  map and photos; kudos and comments.
- Custom titles get "3.5 times more kudos", which is why Quick Edit asks for one
  after an upload.

### The activity page for a run

- A full-screen map, route and media hero with best efforts and segment wins
  placed on the map, and a toggle to stats.
- **Athlete Intelligence**: one or two plain sentences under the stat box, with
  "Say More", a four-level feedback control and a hide option. Strava's own
  example: "Nice work on a challenging route! Your pace was 13 seconds faster
  than your 30-day average." It compares against the runner's own baseline.
- **Analysis on the web**: an elevation profile with stacked performance charts
  below it. Hovering updates distance, time, pace and elevation together;
  dragging selects a range and highlights it on the map.
- Splits per km, Grade Adjusted Pace on hilly runs, heart-rate zones and a
  weekly Relative Effort chart with a suggested range band ("Within range",
  "Above range"), best efforts with PR medals, segments, and **matched runs**: a
  dot per run with a trend line, the fastest in yellow and this run in orange.

### Progress over time

- A Progress chart with 1W, 1M, 3M, 6M, YTD and 1Y ranges and "Compare Date
  Range"; a Weekly Snapshot; a Training Log of circles per activity; Fitness and
  Freshness; Performance Predictions (needs 20 runs in 24 weeks, states its
  minimum openly); weekly streaks; monthly recaps.

### Visual language

- Strava orange **#FC5200** (API brand guidelines, Sep 2025), warm neutrals on
  strava.com (#21211F text, #F9F8F5 footer).
- **Boathouse** type (with condensed and extended widths), introduced around
  November 2024. The claim that the app uses Inter is *unverified*.
- Web buttons with 4px corners; marketing feature tiles are near-black rounded
  cards that show real product screens with "NEW" badges.

### Motion

- Kudos fill and count; achievement banners; Flyover 3D replays (subscribers);
  Activity Replays in the feed (2026); Year in Sport built in Rive with
  data-bound animations. Web analysis charts hover together and zoom by drag.

### Strengths and weaknesses

- **Best**: the synchronised analysis charts; the stat triplet; the sentence
  under the stats; matched runs; stating data minimums openly.
- **Weak**: upsell prompts "on nearly every page"; an algorithmic feed users
  push back on; a Weekly Snapshot criticised as guilt-inducing; Year in Sport
  behind the paywall; Athlete Intelligence errors ("nice first ride!" to someone
  with 2,165 rides).

Sources: [strava.com/features](https://www.strava.com/features) ·
[Strava API brand guidelines](https://developers.strava.com/guidelines/) ·
[Athlete Intelligence help](https://support.strava.com/hc/en-us/articles/26786795557005-Athlete-Intelligence-on-Strava) ·
[Run activity pages help](https://support.strava.com/en-us/articles/15401883-run-activity-pages) ·
[Matched activities help](https://support.strava.com/en-us/articles/15401955-matched-activities) ·
[Performance Predictions help](https://support.strava.com/en-us/articles/15401591-performance-predictions) ·
[Progress Summary help](https://support.strava.com/en-us/articles/15401618-progress-summary-chart) ·
[Feed stats help](https://support.strava.com/en-us/articles/15401664-activity-stats-in-the-feed) ·
[9to5Google on dark mode](https://9to5google.com/2024/06/26/strava-dark-mode-android-ios/) ·
[BikeRadar on the Record redesign](https://www.bikeradar.com/news/strava-redesigned-record-feature) ·
[Strava press releases](https://press.strava.com/)

## Garmin Connect

### Where it stands

- The app's Home (formerly My Day) was redesigned in 2024: Today's Activity, an
  **In Focus** carousel of up to five large panels, a context slot, **At a
  Glance** tiles (up to eight), then optional sections. Home is editable, with
  presets and a focus-area quiz.
- **Connect+** (Mar 2025) added Active Intelligence insights, the Performance
  dashboard, Live Activity and LiveTrack+. Later: Running Economy and Running
  Tolerance (May 2025), Health Status (Sep 2025), 3D maps and Connect Rundown
  (Nov and Dec 2025), a Followers model (May 2026), an opt-in **Essentials**
  dashboard with up to four metrics (Jul 2026), and Garmin Epic stories (Aug 2026).
- The app was dark-only until September 2023; it now offers light, dark and system.

### The run activity page

- Mobile tabs: Overview, Stats, Laps, Charts, Gear. Overview shows a map with the
  route coloured by pace and a "Slower to Faster" legend, a large distance, and a
  two-by-two grid of average heart rate, average pace, total time and calories.
- Web: a stats strip, the map, a Time or Distance toggle, then full-width area
  charts stacked vertically, each with a **dashed average line**, an
  "Avg: 12:12 /mi" chip and a coloured legend dot. Colours sampled from Garmin's
  images: pace #3CB8EB, heart rate #FC3A5C.
- Heart-rate zones Z1 Warm Up to Z5 Maximum, reported as grey, blue, green,
  orange and red (hex values *unverified*). Training Effect from 0.0 to 5.0 in
  worded bands.

### Readiness and status

- **Training Readiness**: Prime, High, Moderate, Low, Poor, each with a colour and
  a short instruction ("Good to go", "Time to slow down"), built from six named
  factors that are listed under the score.
- **Training Status**, **HRV Status**, **Body Battery** (5 to 100 with charged
  and drained deltas and event markers on the timeline), **Sleep Score** with a
  hypnogram, **Stress** with blue rest and orange stress.
- Honest calibration states: three days of wear before Training Readiness, about
  three weeks before HRV Status, 21 to 28 days before Health Status.

### Insights

- Active Intelligence cards sit at the top of Home, tagged by moment ("After
  wakeup"), with thumbs up and down. Reviewers found many simply restate numbers
  and some were wrong.
- The Performance dashboard offers 140+ charts with any metric over any range;
  reviewers called it mostly a lot of charts.
- Endurance Score and Hill Score use one colour ladder: pink, purple, blue, green,
  yellow, orange, red.

### Visual language

- Dark app: page #101010, cards #242424, active blue about #55AAFF. Light web:
  white cards, primary blue #1976D2, 4px button corners.
- One graded colour ladder (purple, blue, green, orange, red) runs through
  readiness, running dynamics and the scores, matching the colours watch screens
  can show. Marketing on garmin.com uses Oswald in capitals; connect.garmin.com
  uses Open Sans. Numbers are large with small grey labels.

### Strengths and weaknesses

- **Best**: every score pairs a number with a word, a fixed colour and a plain
  action; factor breakdowns say why; calibration states are honest; stacked
  charts share one time axis with an average line.
- **Weak**: the 2024 Home was likened to a "glossy brochure" with oversized tiles;
  data is spread across about a dozen menus; scores like Training Status can
  contradict their own indicators; laps need landscape on a phone.

Sources: [connect.garmin.com](https://connect.garmin.com/) ·
[DC Rainmaker, Connect app revamp](https://www.dcrainmaker.com/2024/01/garmin-connect-mobile-revamp-walk-through.html) ·
[Garmin newsroom, Connect+](https://www.garmin.com/en-US/newsroom/press-release/wearables-health/elevate-your-health-and-fitness-goals-with-garmin-connect/) ·
[DC Rainmaker, Connect+ walkthrough](https://www.dcrainmaker.com/2025/03/garmin-connect-plus-subscription-walkthrough.html) ·
[the5krunner, Training Readiness](https://the5krunner.com/garmin-features/training/training-readiness/) ·
[Garmin manual, Training Readiness](https://www8.garmin.com/manuals-apac/webhelp/forerunner955/EN-SG/GUID-6226F839-5FA4-4864-ADBD-6BF64CFBA0F4-7389.html) ·
[Garmin blog, Performance dashboard](https://www.garmin.com/en-US/blog/fitness/what-is-the-garmin-connect-performance-dashboard/) ·
[Garmin Connect brand guidelines](https://developer.garmin.com/brand-guidelines/connect/) ·
[Gadgets and Wearables, Followers](https://gadgetsandwearables.com/2026/05/21/garmin-connect-followers/) ·
[Garmin forums on the web dashboard](https://forums.garmin.com/apps-software/mobile-apps-web/f/garmin-connect-web/369216/garmin-connect-web-dashboard--information-is-now-less-accessible-than-before/1764073)

## Side by side

| Pattern | Apple | Strava | Garmin | Runnify now |
|---|---|---|---|---|
| Themes | Light and dark, follows system | Device, always light, always dark | Light, dark, system | Auto, Light, Dark (footer and account menu) |
| Page ground | #F2F2F7 grey with white cards | Warm white | #101010 dark or white | #F3F4F6 grey or #0A0B0D, with cards |
| Corner radius | About 24pt cards, capsule controls | 4px web buttons | 4 to 6px web cards | 20px cards, 10px controls, 6px badges, no capsules |
| Big numbers | Regular weight, about 34pt | Bold value, small label | Large and light, small grey label | 650 weight, tabular, small grey unit |
| Range control | D W M 6M Y segmented | 1W to 1Y with compare | 7d, 4w, 1y | Last 30 days, 90 days, this year, all time |
| Findings in words | Highlights: one sentence with a number | Athlete Intelligence (generated) | Active Intelligence (generated) | Highlights worked out from the numbers, never generated |
| Evidence shown | Data sources, thresholds | Minimums stated | Factors listed, calibration states | Runs and plays behind every lift |
| Chart scrubbing | Press and hold | Hover syncs all charts and the map | Crosshair (web *unverified*) | Pointer, finger or arrow keys across pace, lane and heart rate |
| Average line | Summary header | Average marked on pace | Dashed line with an "Avg" chip | Dashed "Moving avg" line on every run chart |

## Runnify before the redesign

The October 2026 design, "The Official Results Sheet", was careful and
consistent: white paper, near-black ink, highlighter yellow for the best row,
red pen for drags, 2px heavy rules, square 2px corners, no shadows, light only,
one typeface (Geist) and motion only on the landing page. It passed 21 contrast
pairs and every page worked without scripts.

What held it back against Apple, Strava and Garmin:

- **It read as a printed document, not an app.** Heavy rules and uppercase
  column heads gave every page the same ledger feel; dashboards and charts lacked
  the soft hierarchy runners know from their own apps.
- **No dark mode.** All three benchmarks offer one; runners check results early
  and late.
- **Charts were thin.** A single black trace without a fill, no average line, no
  colour for pace or heart rate, and song bands without names.
- **Findings were lists, not sentences.** The Insights page ranked songs well but
  never said what it meant in a line, the way Apple Highlights and Strava's
  summary do.
- **The landing page explained the method in a print metaphor** (a tilted sheet,
  a results ticker, stacking sheets) rather than showing the product doing its
  one job: a run playing back with its songs.
- **What it got right, and the redesign keeps**: measuring each song against the
  runner's own pace, showing the evidence behind every number, plain copy, the
  strict Content-Security-Policy, server-drawn charts, and pages that work
  without scripts.

## What Runnify takes, and what it leaves

**Takes**

1. Apple's calm surfaces: a grey page with raised cards, both themes, big
   tabular numbers with small grey units, and one colour per kind of data.
2. Apple's Highlights voice: one sentence, a number, a unit and the evidence,
   comparing only with the runner's own history.
3. Strava's synchronised analysis: one scrub moves a guide across pace, the song
   lane and heart rate together, with the song and its lift in the readout.
4. Strava's summary under the stats: a sentence naming the fastest and slowest
   songs on every run page.
5. Garmin's dashed average line on stacked charts, and its habit of pairing a
   number with a word ("Power song", "Drag song") and an action ("Save it for
   the cool-down").
6. Garmin's and Apple's honesty about thresholds: songs rank only after two runs,
   and the page says so.
7. Strava's marketing tiles: real product screens on dark cards rather than
   illustrations or fake dashboards.

**Leaves**

- Generated AI summaries. Every Runnify sentence is worked out from stored
  numbers, so it can't invent a fact.
- Upsell prompts, streak guilt and engagement nudges.
- Maps, segments and geography: Runnify's subject is the song, not the route.
- Ring imagery (Apple's guidelines forbid reusing it) and Strava orange.
- Glass on content: blur is used only for the header and the phone tab bar.
- Dozens of physiology metrics and a dashboard of 140 charts.
