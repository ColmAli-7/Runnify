/**
 * Run page: move along the charts to read the pace, heart rate and song at any
 * moment. The charts and the results table carry all of this without scripts;
 * this is a reading aid, so the readout is hidden from assistive technology.
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

if (container && source) {
  const data = JSON.parse(source.textContent);
  const readout = container.querySelector("[data-readout]");
  const plots = [...container.querySelectorAll(".chart__plot")];
  const guides = plots.map((plot) => {
    const guide = document.createElement("span");
    guide.className = "chart__guide";
    guide.hidden = true;
    plot.parentElement.append(guide);
    return guide;
  });

  const span = (text, className) => {
    const element = document.createElement("span");
    element.textContent = text;
    if (className) element.className = className;
    return element;
  };

  const show = (fraction) => {
    const index = Math.min(data.pace.length - 1, Math.floor(fraction * data.pace.length));
    const second = fraction * data.seconds;
    const song = data.songs.find(([start, end]) => second >= start && second <= end);
    const parts = [span(clock(second), "run__readout-time")];
    const p = data.pace[index];
    const h = data.heart[index];
    parts.push(span(p == null ? "Stopped" : `${pace(p)} /km`));
    if (h != null) parts.push(span(`${Math.round(h)} bpm`));
    parts.push(span(song ? song[2] : "No music", song ? "run__readout-song" : "muted"));
    readout.replaceChildren(...parts);
    plots.forEach((plot, i) => {
      const box = plot.getBoundingClientRect();
      const outer = plot.parentElement.getBoundingClientRect();
      guides[i].style.left = `${box.left - outer.left + fraction * box.width}px`;
      guides[i].style.height = `${box.height}px`;
      guides[i].hidden = false;
    });
  };

  const hide = () => {
    guides.forEach((guide) => (guide.hidden = true));
    readout.replaceChildren();
  };

  for (const plot of plots) {
    plot.addEventListener("pointermove", (event) => {
      const box = plot.getBoundingClientRect();
      show(Math.min(1, Math.max(0, (event.clientX - box.left) / box.width)));
    });
    plot.addEventListener("pointerleave", hide);
  }
}
