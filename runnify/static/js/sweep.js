/**
 * The highlighter sweep: a stroke of highlighter drawn across the best row,
 * the way a runner marks their own name on posted results.
 *
 * Markup: a `[data-sweep-host]` around one `[data-sweep]` element. While
 * motion is allowed, CSS leaves that element unmarked until the host has
 * `.is-swept`; `sweep()` draws the stroke, then hands back to the CSS mark.
 */

/** Show the finished mark straight away (reduced motion, or no animation library). */
export function markSwept(host) {
  host.classList.add("is-swept");
}

/** Where `element` sits inside `ancestor`, ignoring transforms on the way. */
function offsetWithin(element, ancestor) {
  let top = 0;
  let left = 0;
  for (let node = element; node && node !== ancestor; node = node.offsetParent) {
    top += node.offsetTop;
    left += node.offsetLeft;
  }
  return { top, left };
}

/** Draw the stroke across the host's `[data-sweep]` element. Needs GSAP on `window`. */
export function sweep(host, { delay = 0, duration = 0.75 } = {}) {
  const target = host.querySelector("[data-sweep]");
  const { gsap } = window;
  if (!target || !gsap) {
    markSwept(host);
    return;
  }
  const { top, left } = offsetWithin(target, host);
  const mark = document.createElement("span");
  mark.className = "sweep-mark";
  mark.setAttribute("aria-hidden", "true");
  Object.assign(mark.style, {
    top: `${top}px`,
    left: `${left}px`,
    width: `${target.offsetWidth}px`,
    height: `${target.offsetHeight}px`,
  });
  host.prepend(mark);
  gsap.fromTo(
    mark,
    { scaleX: 0 },
    {
      scaleX: 1,
      duration,
      delay,
      ease: "power2.inOut",
      onComplete() {
        markSwept(host);
        mark.remove();
      },
    },
  );
}
