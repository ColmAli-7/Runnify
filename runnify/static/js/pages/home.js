/**
 * Landing page motion. The page reads completely without it; this adds:
 * - the hero: the headline's words rise, then the sample run replays, a
 *   playhead walking its pace line while each song lights up and plays;
 * - the story: each step draws or lights its picture as you reach it;
 * - quiet entrances for the results, set-up and privacy cards, and the closing line.
 * Nothing moves when the visitor prefers reduced motion, and if the animation
 * library is missing everything is simply shown.
 */
import { markSwept, sweep } from "../sweep.js";

const root = document.documentElement;
const motionAllowed = window.matchMedia("(prefers-reduced-motion: no-preference)").matches;
const { gsap, ScrollTrigger } = window;
const SVG = "http://www.w3.org/2000/svg";

function clock(seconds) {
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const rest = String(total % 60).padStart(2, "0");
  return hours ? `${hours}:${String(minutes).padStart(2, "0")}:${rest}` : `${minutes}:${rest}`;
}

/** A lift badge the way the server prints one: "+9 s/km", true minus, arrow, words for screen readers. */
function liftBadge(value) {
  const whole = Math.round(value);
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
  const sign = whole > 0 ? "+" : whole < 0 ? "−" : "±";
  badge.append(`${sign}${Math.abs(whole)} s/km`);
  return { badge, kind };
}

/**
 * Clip a run chart's fill and line to a rectangle we can widen, so the line
 * draws from left to right. Returns the rectangle (in the chart's 0-1000 units).
 */
function clipLines(plot, id) {
  const lines = plot.querySelector(".chart__lines");
  if (!lines) return null;
  const box = lines.viewBox.baseVal.width || 1000;
  const defs = document.createElementNS(SVG, "defs");
  const clip = document.createElementNS(SVG, "clipPath");
  clip.id = id;
  const rect = document.createElementNS(SVG, "rect");
  rect.setAttribute("x", "0");
  rect.setAttribute("y", "0");
  rect.setAttribute("width", "0");
  rect.setAttribute("height", String(box));
  clip.append(rect);
  defs.append(clip);
  const group = document.createElementNS(SVG, "g");
  group.setAttribute("clip-path", `url(#${id})`);
  group.append(...lines.querySelectorAll(".area, .trace"));
  lines.append(defs, group);
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
      gsap.fromTo(badge, { scale: 0.8, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.35, ease: "back.out(2)" });
    }
    gsap.fromTo([name, artist], { y: 6, opacity: 0 }, { y: 0, opacity: 1, duration: 0.3, ease: "power2.out" });
  };

  const render = (fraction) => {
    const second = fraction * data.seconds;
    const outer = chartBox.getBoundingClientRect();
    const box = plot.getBoundingClientRect();
    const x = box.left - outer.left + fraction * box.width;
    const bottomEdge = (lane ? lane.getBoundingClientRect().bottom : box.bottom) - outer.top;
    const plotTop = box.top - outer.top;
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
    const best = card.querySelectorAll(".band--best, .lane__block--best");
    gsap.fromTo(best, { opacity: 0.4 }, { opacity: 1, duration: 0.8, repeat: 1, yoyo: true, ease: "sine.inOut" });
    if (again) again.hidden = false;
  };

  const play = () => {
    tween?.kill();
    current = -2;
    card.classList.add("is-replaying");
    if (again) again.hidden = true;
    head.hidden = false;
    playhead.at = 0;
    render(0);
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

  return { play };
}

function hero() {
  const title = document.querySelector("[data-hero-title]");
  const fades = document.querySelectorAll("[data-hero-fade]");
  const card = document.querySelector("[data-replay]");
  const replay = card ? makeReplay(card) : null;
  const timeline = gsap.timeline({ defaults: { ease: "expo.out" } });
  if (title) {
    const words = splitWords(title);
    gsap.set(title, { opacity: 1 });
    timeline.from(words, { yPercent: 110, duration: 1.05, stagger: 0.05 }, 0);
  }
  timeline.fromTo(fades, { opacity: 0, y: 14 }, { opacity: 1, y: 0, duration: 0.9, stagger: 0.08 }, 0.3);
  if (card) {
    timeline.fromTo(card, { opacity: 0, y: 36, scale: 0.98 }, { opacity: 1, y: 0, scale: 1, duration: 1.2 }, 0.2);
  }
  if (replay) timeline.add(() => replay.play(), 1.1);
}

/* ---- the story ------------------------------------------------------------ */

function story() {
  const steps = [...document.querySelectorAll("[data-story-step]")];
  steps.forEach((step, index) => {
    const kind = step.dataset.storyStep;
    const figure = step.querySelector(".story__figure");
    const plot = figure?.querySelector(".chart__plot");
    let play = () => {};

    if (kind === "pace" && plot) {
      const clip = clipLines(plot, `story-clip-${index}`);
      if (clip) {
        play = () => gsap.to(clip.rect, { attr: { width: clip.box }, duration: 1.8, ease: "power2.inOut" });
      }
    } else if (kind === "songs" && plot) {
      const bands = plot.querySelectorAll(".band");
      const blocks = figure.querySelectorAll(".lane__block");
      gsap.set(bands, { opacity: 0 });
      gsap.set(blocks, { opacity: 0, y: -10 });
      play = () => {
        gsap.to(blocks, { opacity: 1, y: 0, duration: 0.5, stagger: 0.06, ease: "back.out(1.6)" });
        gsap.to(bands, { opacity: 1, duration: 0.6, stagger: 0.06, delay: 0.15, ease: "power1.out" });
      };
    } else if (kind === "context" && plot) {
      const around = plot.querySelectorAll(".band--context");
      const song = plot.querySelectorAll(".band--best");
      const result = figure.querySelector("[data-story-result]");
      gsap.set([...around, ...song], { opacity: 0 });
      if (result) gsap.set(result, { opacity: 0, y: 8 });
      play = () => {
        const sequence = gsap.timeline();
        sequence.to(song, { opacity: 1, duration: 0.5, ease: "power1.out" });
        sequence.to(around, { opacity: 1, duration: 0.6, stagger: 0.15, ease: "power1.out" }, "+=0.15");
        if (result) sequence.to(result, { opacity: 1, y: 0, duration: 0.6, ease: "expo.out" }, "+=0.1");
      };
    } else if (kind === "ranked" && figure) {
      const host = figure.querySelector("[data-sweep-host]");
      const rows = figure.querySelectorAll(".mini-rank");
      gsap.set(rows, { opacity: 0, y: 12 });
      play = () => {
        gsap.to(rows, { opacity: 1, y: 0, duration: 0.6, stagger: 0.08, ease: "expo.out" });
        if (host) sweep(host, { delay: 0.45 });
      };
    }

    whenSeen(step, play, "top 65%");
    ScrollTrigger.create({ trigger: step, start: "top 55%", end: "bottom 45%", toggleClass: "is-active" });
  });
}

/* ---- everything else that eases in -------------------------------------- */

function reveals() {
  const items = gsap.utils.toArray("[data-reveal]");
  gsap.set(items, { y: 24 });
  ScrollTrigger.batch(items, {
    start: "top 88%",
    once: true,
    onEnter: (batch) =>
      gsap.to(batch, { opacity: 1, y: 0, duration: 0.9, stagger: 0.08, ease: "expo.out", overwrite: true }),
  });
  // anything the page has already gone past is simply shown
  items.forEach((item) => {
    if (item.getBoundingClientRect().bottom < 0) gsap.set(item, { opacity: 1, y: 0 });
  });

  const trace = document.querySelector(".cta__trace");
  if (trace) {
    gsap.set(trace, { clipPath: "inset(0 100% 0 0)" });
    whenSeen(trace, () =>
      gsap.to(trace, { clipPath: "inset(0 0% 0 0)", duration: 2.4, ease: "power2.inOut" }),
    );
  }
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
  reveals();
  document.fonts?.ready.then(() => ScrollTrigger.refresh());
}
