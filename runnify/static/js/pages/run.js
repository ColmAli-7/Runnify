/**
 * Run page: scrub along the charts to read the pace, heart rate and song at any
 * moment, with the pointer, a finger or the arrow keys. The charts, the song
 * lane and the results table carry all of this without scripts; this is a
 * reading aid, so the floating readout is hidden from assistive technology.
 */
const container = document.querySelector("[data-timeline]");
const source = document.getElementById("timeline-data");

function clock(seconds) {
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const rest = String(total % 60).padStart(2, "0");
  return hours ? `${hours}:${String(minutes).padStart(2, "0")}:${rest}` : `${minutes}:${rest}`;
}

function pace(secondsPerKm) {
  const total = Math.round(secondsPerKm);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

/** "+9 s/km" with a true minus sign, as the filters print it. */
function liftText(value) {
  const whole = Math.round(value);
  const sign = whole > 0 ? "+" : whole < 0 ? "−" : "±";
  return `${sign}${Math.abs(whole)} s/km`;
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

if (container && source) {
  const data = JSON.parse(source.textContent);
  const readout = container.querySelector("[data-readout]");
  const plots = [...container.querySelectorAll(".chart__plot")];
  const lane = container.querySelector(".lane");
  const series = [
    { values: data.pace, range: data.pace_range },
    { values: data.heart, range: data.heart_range },
  ];
  const marks = plots.map((plot) => {
    const guide = element("span", "chart__guide");
    const dot = element("span", "chart__dot");
    guide.hidden = dot.hidden = true;
    plot.parentElement.append(guide, dot);
    return { plot, guide, dot };
  });
  let laneGuide = null;
  if (lane) {
    laneGuide = element("span", "chart__guide chart__guide--lane");
    laneGuide.hidden = true;
    lane.parentElement.append(laneGuide);
  }
  let position = 0.5;
  let frame = 0;

  const place = (node, styles) => Object.assign(node.style, styles);

  const show = (fraction) => {
    position = Math.min(1, Math.max(0, fraction));
    const count = data.pace.length;
    const index = Math.min(count - 1, Math.floor(position * count));
    const second = position * data.seconds;
    const song = data.songs.find(([start, end]) => second >= start && second <= end);
    const outer = container.getBoundingClientRect();

    marks.forEach(({ plot, guide, dot }, i) => {
      const box = plot.getBoundingClientRect();
      const host = plot.parentElement.getBoundingClientRect();
      const x = box.left - host.left + position * box.width;
      place(guide, { left: `${x}px`, top: `${box.top - host.top}px`, height: `${box.height}px` });
      guide.hidden = false;
      const { values, range } = series[i] || {};
      const value = values?.[index];
      if (value == null || !range || range[0] === range[1]) {
        dot.hidden = true;
        return;
      }
      const share = Math.min(1, Math.max(0, (value - range[0]) / (range[1] - range[0])));
      place(dot, { left: `${x}px`, top: `${box.top - host.top + share * box.height}px` });
      dot.hidden = false;
    });

    if (lane && laneGuide) {
      const box = lane.getBoundingClientRect();
      const host = lane.parentElement.getBoundingClientRect();
      const inset = parseFloat(getComputedStyle(lane).paddingLeft) || 0;
      const width = box.width - inset;
      place(laneGuide, {
        left: `${box.left - host.left + inset + position * width}px`,
        top: `${box.top - host.top}px`,
        height: `${box.height}px`,
      });
      laneGuide.hidden = false;
    }

    // the readout: time, pace, heart rate and the song, beside the guide
    const p = data.pace[index];
    const h = data.heart[index];
    const rows = [element("span", "run__readout-time", clock(second))];
    const figures = element("span", "run__readout-figures");
    figures.append(element("span", "run__readout-pace", p == null ? "Stopped" : `${pace(p)} /km`));
    if (h != null) figures.append(element("span", "run__readout-heart", `${Math.round(h)} bpm`));
    rows.push(figures);
    if (song) {
      const [, , name, artist, lift] = song;
      const line = element("span", "run__readout-song", name);
      if (artist) line.append(element("span", "run__readout-artist", artist));
      rows.push(line);
      if (lift != null) {
        const kind = Math.abs(lift) < 1 ? "flat" : lift > 0 ? "up" : "down";
        rows.push(element("span", `lift lift--${kind}`, liftText(lift)));
      }
    } else {
      rows.push(element("span", "run__readout-none", "No music"));
    }
    readout.replaceChildren(...rows);
    readout.hidden = false;

    const first = plots[0].getBoundingClientRect();
    const x = first.left - outer.left + position * first.width;
    const width = readout.offsetWidth;
    const gap = 14;
    const left = x + gap + width > container.clientWidth ? x - gap - width : x + gap;
    place(readout, { left: `${Math.max(0, left)}px`, top: `${first.top - outer.top + 8}px` });
  };

  const hide = () => {
    marks.forEach(({ guide, dot }) => (guide.hidden = dot.hidden = true));
    if (laneGuide) laneGuide.hidden = true;
    readout.hidden = true;
  };

  const fromPointer = (event) => {
    const box = plots[0].getBoundingClientRect();
    return (event.clientX - box.left) / box.width;
  };

  container.addEventListener("pointermove", (event) => {
    if (!event.target.closest(".chart__plot, .lane")) return;
    window.cancelAnimationFrame(frame);
    frame = window.requestAnimationFrame(() => show(fromPointer(event)));
  });
  container.addEventListener("pointerleave", () => {
    window.cancelAnimationFrame(frame);
    if (document.activeElement !== container) hide();
  });

  // keyboard: arrows step through the run (Shift for bigger steps), Home and End jump
  container.addEventListener("focus", () => show(position));
  container.addEventListener("blur", hide);
  container.addEventListener("keydown", (event) => {
    const step = event.shiftKey ? 1 / 20 : 1 / 120;
    const moves = {
      ArrowRight: position + step,
      ArrowLeft: position - step,
      Home: 0,
      End: 1,
    };
    if (!(event.key in moves)) return;
    event.preventDefault();
    show(moves[event.key]);
  });
}
