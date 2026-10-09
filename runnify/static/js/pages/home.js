/**
 * Landing page behaviour. Everything works without it; this adds:
 * - the highlighter sweep over the winning rows (once each);
 * - a quiet scale-and-fade as the sample panels arrive;
 * - the measuring sheets receding as the next one stacks on top (wide screens);
 * - the steps accordion and the findings carousel controls.
 * Motion is skipped entirely when the visitor prefers reduced motion.
 */
import { markSwept, sweep } from "../sweep.js";

const motion = window.matchMedia("(prefers-reduced-motion: no-preference)");
const { gsap, ScrollTrigger } = window;

function animate() {
  const hosts = [...document.querySelectorAll("[data-sweep-host]")];
  if (!motion.matches || !gsap || !ScrollTrigger) {
    hosts.forEach(markSwept);
    return;
  }
  gsap.registerPlugin(ScrollTrigger);

  // the hero sheet settles first (CSS), then its winning row is marked
  const [hero, ...rest] = hosts;
  if (hero) sweep(hero, { delay: 0.7 });
  rest.forEach((host) => {
    ScrollTrigger.create({ trigger: host, start: "top 75%", once: true, onEnter: () => sweep(host, { delay: 0.35 }) });
  });

  gsap.utils.toArray("[data-reveal]").forEach((panel, index) => {
    gsap.from(panel, {
      opacity: 0,
      scale: 0.97,
      y: 24,
      duration: 0.7,
      delay: (index % 2) * 0.08,
      ease: "power3.out",
      scrollTrigger: { trigger: panel, start: "top 88%", once: true },
    });
  });

  // the card stays opaque; only its contents fade, so nothing shows through the sheet on top
  gsap.matchMedia().add("(min-width: 1024px)", () => {
    const cards = gsap.utils.toArray(".method__card");
    cards.slice(0, -1).forEach((card, index) => {
      gsap
        .timeline({
          scrollTrigger: { trigger: cards[index + 1], start: "top bottom", end: "top top+=160", scrub: true },
        })
        .to(card, { scale: 0.94, ease: "none" }, 0)
        .to(card.children, { opacity: 0.3, ease: "none" }, 0);
    });
  });
}

/** One step open at a time; on wide screens with a mouse, hovering a step opens it. */
function steps() {
  const all = [...document.querySelectorAll(".how__details")];
  const wide = window.matchMedia("(min-width: 960px)");
  all.forEach((details) => {
    details.addEventListener("toggle", () => {
      if (details.open) all.forEach((other) => other !== details && (other.open = false));
    });
    // on wide screens one step always stays open, so clicking the open one does nothing
    details.querySelector("summary").addEventListener("click", (event) => {
      if (wide.matches && details.open) event.preventDefault();
    });
  });
  if (!window.matchMedia("(hover: hover)").matches) return;
  all.forEach((details) => {
    let timer;
    details.parentElement.addEventListener("pointerenter", () => {
      if (wide.matches) timer = window.setTimeout(() => (details.open = true), 150);
    });
    details.parentElement.addEventListener("pointerleave", () => window.clearTimeout(timer));
  });
}

/** Previous and next buttons, and a "2 of 4" count, for the scrollable findings. */
function carousel() {
  const track = document.querySelector("[data-carousel]");
  const controls = document.querySelector("[data-carousel-controls]");
  if (!track || !controls) return;
  const slides = [...track.children];
  const prev = controls.querySelector("[data-carousel-prev]");
  const next = controls.querySelector("[data-carousel-next]");
  const count = controls.querySelector("[data-carousel-count]");
  const step = () => (slides.length > 1 ? slides[1].offsetLeft - slides[0].offsetLeft : track.clientWidth);
  const atEnd = () => track.scrollLeft + track.clientWidth >= track.scrollWidth - 2;

  const update = () => {
    const index = atEnd() ? slides.length - 1 : Math.round(track.scrollLeft / step());
    count.textContent = `${index + 1} of ${slides.length}`;
    prev.setAttribute("aria-disabled", String(track.scrollLeft <= 2));
    next.setAttribute("aria-disabled", String(atEnd()));
  };
  const go = (button, direction) => {
    if (button.getAttribute("aria-disabled") === "true") return;
    track.scrollBy({ left: direction * step(), behavior: motion.matches ? "smooth" : "auto" });
  };

  prev.addEventListener("click", () => go(prev, -1));
  next.addEventListener("click", () => go(next, 1));
  let frame;
  track.addEventListener(
    "scroll",
    () => {
      window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(update);
    },
    { passive: true },
  );
  controls.hidden = false;
  update();
}

animate();
steps();
carousel();
