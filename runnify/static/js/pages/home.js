/**
 * Landing page motion. The page reads completely without it, and nothing fades
 * in as you scroll: every movement shows something the product does.
 * - the hero: the headline's words rise once, then the sample run replays, a
 *   playhead walking its pace line while each song lights up and plays;
 * - the story: the pace line draws, the songs land on their seconds, the
 *   minutes either side of a song open out from it while its lift counts up,
 *   and the best of the ranked songs is struck with volt;
 * - the closing panel draws the run's pace line behind its words.
 * Nothing moves when the visitor prefers reduced motion, and if the animation
 * library is missing everything is simply shown.
 */
import { markSwept, sweep } from "../sweep.js";

const root = document.documentElement;
const motionAllowed = window.matchMedia("(prefers-reduced-motion: no-preference)").matches;
const { gsap, ScrollTrigger } = window;
const SVG = "http://www.w3.org/2000/svg";
const MINUS = "−";
const NBSP = " ";

function clock(seconds) {
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const rest = String(total % 60).padStart(2, "0");
  return hours ? `${hours}:${String(minutes).padStart(2, "0")}:${rest}` : `${minutes}:${rest}`;
}

/** "+9 s/km" the way the server prints it, with a true minus sign. */
function liftText(value) {
  const whole = Math.round(value);
  const sign = whole > 0 ? "+" : whole < 0 ? MINUS : "±";
  return `${sign}${Math.abs(whole)}${NBSP}s/km`;
}

/** A lift badge like the server's: arrow, signed figure, and words for screen readers. */
function liftBadge(value) {
  const kind = Math.abs(value) < 1 ? "flat" : value > 0 ? "up" : "down";
  const badge = document.createElement("span");
  badge.className = `lift lift--${kind}`;
  if (kind !== "flat") {
    const icon = document.createElementNS(SVG, "svg");
    icon.setAttribute("class", "icon");
    icon.setAttribute("aria-hidden", "true");
    const use = document.createElementNS(SVG, "use");
    const sprite = document.querySelector("svg.icon use")?.getAttribute("href")?.split("#")[0] || "";
    use.setAttribute("href", `${sprite}#i-arrow-${kind}`);
    icon.append(use);
    badge.append(icon);
  }
  badge.append(liftText(value));
  return { badge, kind };
}

/** A clipping rectangle, in the units of `svg`, for the given children; returns the rectangle. */
function clipChildren(svg, children, id, { x = "0", width = "0", height = "100%" } = {}) {
  const defs = document.createElementNS(SVG, "defs");
  const clip = document.createElementNS(SVG, "clipPath");
  clip.id = id;
  const rect = document.createElementNS(SVG, "rect");
  rect.setAttribute("x", x);
  rect.setAttribute("y", "0");
  rect.setAttribute("width", width);
  rect.setAttribute("height", height);
  clip.append(rect);
  defs.append(clip);
  const group = document.createElementNS(SVG, "g");
  group.setAttribute("clip-path", `url(#${id})`);
  const first = children[0];
  first.parentNode.insertBefore(group, first);
  group.append(...children);
  svg.append(defs);
  return rect;
}

/** Clip a run chart's fill and line so they can draw from left to right (0 to 1000 units). */
function clipLines(plot, id) {
  const lines = plot.querySelector(".chart__lines");
  const drawn = lines ? [...lines.querySelectorAll(".area, .trace")] : [];
  if (!drawn.length) return null;
  const box = lines.viewBox.baseVal.width || 1000;
  const rect = clipChildren(lines, drawn, id, { height: String(box) });
  return { rect, box };
}

/** Run `fn` once, when `element` comes into view, or now if the page is already past that point. */
function whenSeen(element, fn, start = "top 75%") {
  let done = false;
  const run = () => {
    if (done) return;
    done = true;
    fn();
  };
  const trigger = ScrollTrigger.create({ trigger: element, start, once: true, onEnter: run });
  if (trigger.scroll() >= trigger.start) run();
}

/* ---- the hero ------------------------------------------------------------ */

function splitWords(heading) {
  const words = heading.textContent.trim().split(/\s+/);
  const parts = [];
  words.forEach((word, index) => {
    const outer = document.createElement("span");
    outer.className = "word";
    const inner = document.createElement("span");
    inner.className = "word__inner";
    inner.textContent = word;
    outer.append(inner);
    parts.push(outer);
    if (index < words.length - 1) parts.push(document.createTextNode(" "));
  });
  heading.replaceChildren(...parts);
  return heading.querySelectorAll(".word__inner");
}

function makeReplay(card) {
  const source = document.getElementById("replay-data");
  const chartBox = card.querySelector("[data-replay-chart]");
  const plot = chartBox?.querySelector(".chart__plot");
  if (!source || !plot) return null;
  const data = JSON.parse(source.textContent);
  const clip = clipLines(plot, "replay-clip");
  const bands = [...plot.querySelectorAll(".band")];
  const blocks = [...chartBox.querySelectorAll(".lane__block")];
  const lane = chartBox.querySelector(".lane");
  const now = card.querySelector(".replay__now");
  const state = card.querySelector("[data-replay-state]");
  const name = card.querySelector("[data-replay-song]");
  const artist = card.querySelector("[data-replay-artist]");
  const liftHost = card.querySelector("[data-replay-lift]");
  const distance = card.querySelector("[data-replay-distance]");
  const time = card.querySelector("[data-replay-time]");
  const again = card.querySelector("[data-replay-again]");

  // the finished state, as the server drew it, to come back to at the end
  const final = {
    state: state.textContent,
    name: name.textContent,
    artist: artist.textContent,
    lift: [...liftHost.childNodes].map((node) => node.cloneNode(true)),
    distance: distance.textContent,
    time: time.textContent,
  };

  const head = document.createElement("span");
  head.className = "replay__playhead";
  const dot = document.createElement("span");
  dot.className = "replay__dot";
  head.hidden = dot.hidden = true;
  chartBox.append(head, dot);

  // distance covered by each point of the pace line, scaled to the run's real total
  const count = data.pace.length;
  const step = data.seconds / count;
  const covered = [];
  let metres = 0;
  data.pace.forEach((pace) => {
    metres += pace ? (step * 1000) / pace : 0;
    covered.push(metres);
  });
  const scale = metres ? data.metres / metres : 0;
  const [top, bottom] = data.range;

  let current = -2;
  const playhead = { at: 0 };
  let tween = null;

  const showSong = (index) => {
    if (index < 0) {
      state.textContent = "Between songs";
      name.textContent = "No music";
      artist.textContent = "";
      liftHost.replaceChildren();
      now.dataset.kind = "none";
      return;
    }
    const [, , title, by, lift] = data.songs[index];
    state.textContent = "Now playing";
    name.textContent = title;
    artist.textContent = by;
    if (lift == null) {
      liftHost.replaceChildren();
      now.dataset.kind = "none";
    } else {
      const { badge, kind } = liftBadge(lift);
      liftHost.replaceChildren(badge);
      now.dataset.kind = kind;
      gsap.fromTo(badge, { scale: 0.85 }, { scale: 1, duration: 0.35, ease: "back.out(2)" });
    }
  };

  const render = (fraction) => {
    const second = fraction * data.seconds;
    const outer = chartBox.getBoundingClientRect();
    const box = plot.getBoundingClientRect();
    const x = box.left - outer.left + fraction * box.width;
    const plotTop = box.top - outer.top;
    const bottomEdge = (lane ? lane.getBoundingClientRect().bottom : box.bottom) - outer.top;
    Object.assign(head.style, { left: `${x}px`, top: `${plotTop}px`, height: `${bottomEdge - plotTop}px` });
    if (clip) clip.rect.setAttribute("width", String(fraction * clip.box));

    const index = Math.min(count - 1, Math.floor(fraction * count));
    const pace = data.pace[index];
    if (pace == null || top === bottom) {
      dot.hidden = true;
    } else {
      const share = Math.min(1, Math.max(0, (pace - top) / (bottom - top)));
      Object.assign(dot.style, { left: `${x}px`, top: `${plotTop + share * box.height}px` });
      dot.hidden = false;
    }

    data.songs.forEach(([start], i) => {
      const lit = start <= second;
      bands[i]?.classList.toggle("is-lit", lit);
      blocks.find((block) => block.dataset.lane === String(i))?.classList.toggle("is-lit", lit);
    });

    const playing = data.songs.findIndex(([start, end]) => second >= start && second < end);
    if (playing !== current) {
      current = playing;
      showSong(playing);
    }
    time.textContent = clock(second);
    distance.textContent = ((covered[index] * scale) / 1000).toFixed(2);
  };

  const settle = () => {
    head.hidden = dot.hidden = true;
    if (clip) clip.rect.setAttribute("width", String(clip.box));
    card.classList.remove("is-replaying");
    state.textContent = final.state;
    name.textContent = final.name;
    artist.textContent = final.artist;
    liftHost.replaceChildren(...final.lift.map((node) => node.cloneNode(true)));
    now.dataset.kind = "up";
    distance.textContent = final.distance;
    time.textContent = final.time;
    gsap.fromTo(now, { scale: 0.98 }, { scale: 1, duration: 0.5, ease: "back.out(3)" });
    if (again) again.hidden = false;
  };

  // the start of the run: nothing drawn yet, every song still dark
  const prepare = () => {
    tween?.kill();
    current = -2;
    card.classList.add("is-replaying");
    if (again) again.hidden = true;
    head.hidden = false;
    playhead.at = 0;
    render(0);
  };

  const play = () => {
    prepare();
    tween = gsap.to(playhead, {
      at: 1,
      duration: 9,
      ease: "none",
      onUpdate: () => render(playhead.at),
      onComplete: settle,
    });
  };

  again?.addEventListener("click", play);

  // hold the replay while the card is off screen
  ScrollTrigger.create({
    trigger: card,
    start: "top bottom",
    end: "bottom top",
    onLeave: () => tween?.pause(),
    onLeaveBack: () => tween?.pause(),
    onEnter: () => tween?.resume(),
    onEnterBack: () => tween?.resume(),
  });

  return { prepare, play };
}

function hero() {
  const title = document.querySelector("[data-hero-title]");
  const card = document.querySelector("[data-replay]");
  const replay = card ? makeReplay(card) : null;
  replay?.prepare();
  const timeline = gsap.timeline();
  if (title) {
    const words = splitWords(title);
    gsap.set(title, { opacity: 1 });
    timeline.from(words, { yPercent: 110, duration: 1.05, stagger: 0.05, ease: "expo.out" }, 0);
  }
  if (replay) timeline.add(() => replay.play(), 0.7);
}

/* ---- the story ------------------------------------------------------------ */

/** Count a lift badge's figure up from zero, keeping its arrow and its words for screen readers. */
function countUp(badge, value) {
  const figure = [...badge.childNodes].find((node) => node.nodeType === Node.TEXT_NODE && node.nodeValue.trim());
  if (!figure) return;
  const shown = { value: 0 };
  figure.nodeValue = liftText(0);
  gsap.to(shown, {
    value,
    duration: 1.1,
    ease: "power2.out",
    onUpdate: () => (figure.nodeValue = liftText(shown.value)),
    onComplete: () => (figure.nodeValue = liftText(value)),
  });
}

function story() {
  document.querySelectorAll("[data-story-step]").forEach((step, index) => {
    const kind = step.dataset.storyStep;
    const figure = step.querySelector(".story__figure");
    const plot = figure?.querySelector(".chart__plot");
    let play = () => {};

    if (kind === "pace" && plot) {
      // the line draws itself, left to right
      const clip = clipLines(plot, `story-clip-${index}`);
      if (clip) play = () => gsap.to(clip.rect, { attr: { width: clip.box }, duration: 1.8, ease: "power2.inOut" });
    } else if (kind === "songs" && plot) {
      // the songs land along the run, from its start to its finish
      const bands = [...plot.querySelectorAll(".band")];
      const lane = figure.querySelector(".lane");
      const reveal = bands.length ? clipChildren(plot, bands, `story-bands-${index}`, { width: "0%" }) : null;
      if (lane) gsap.set(lane, { clipPath: "inset(0 100% 0 0)" });
      play = () => {
        if (reveal) gsap.to(reveal, { attr: { width: "100%" }, duration: 1.6, ease: "power2.inOut" });
        if (lane) gsap.to(lane, { clipPath: "inset(0 0% 0 0)", duration: 1.6, ease: "power2.inOut" });
      };
    } else if (kind === "context" && plot) {
      // the five minutes either side open out from the song, and its lift counts up
      const around = [...plot.querySelectorAll(".band--context")];
      const song = plot.querySelector(".band--best");
      const result = figure.querySelector("[data-story-result]");
      const badge = result?.querySelector(".lift");
      const lift = Number.parseFloat(result?.dataset.lift ?? "");
      if (around.length && song) {
        const from = { x: song.getAttribute("x"), width: song.getAttribute("width") };
        const first = Number.parseFloat(around[0].getAttribute("x"));
        const last = around[around.length - 1];
        const end = Number.parseFloat(last.getAttribute("x")) + Number.parseFloat(last.getAttribute("width"));
        const opening = clipChildren(plot, around, `story-context-${index}`, from);
        play = () => {
          gsap.to(opening, {
            attr: { x: `${first}%`, width: `${end - first}%` },
            duration: 1.2,
            delay: 0.2,
            ease: "power3.out",
          });
          if (badge && Number.isFinite(lift)) countUp(badge, lift);
        };
      }
    } else if (kind === "ranked" && figure) {
      // the strongest song is struck with volt
      const host = figure.querySelector("[data-sweep-host]");
      if (host) play = () => sweep(host, { delay: 0.3 });
    }

    whenSeen(step, play, "top 65%");
  });
}

/* ---- the closing panel ------------------------------------------------------ */

function closingLine() {
  const trace = document.querySelector(".cta__trace");
  if (!trace) return;
  gsap.set(trace, { clipPath: "inset(0 100% 0 0)" });
  whenSeen(trace, () => gsap.to(trace, { clipPath: "inset(0 0% 0 0)", duration: 2.4, ease: "power2.inOut" }));
}

/* ---- start --------------------------------------------------------------- */

if (!motionAllowed || !gsap || !ScrollTrigger) {
  root.classList.remove("motion-ok");
  document.querySelectorAll("[data-sweep-host]").forEach(markSwept);
} else {
  gsap.registerPlugin(ScrollTrigger);
  root.classList.add("is-animating");
  hero();
  story();
  closingLine();
  document.fonts?.ready.then(() => ScrollTrigger.refresh());
}
