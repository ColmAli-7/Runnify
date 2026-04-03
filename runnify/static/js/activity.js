// formats seconds into mm:ss
function fmtTime(s) {
  const m = Math.floor(s / 60);
  const ss = String(Math.round(s % 60)).padStart(2, "0");
  return `${m}:${ss}`;
}

// formats pace values into readable form (min/km)
function fmtPace(v) {
  if (v == null || !isFinite(v)) return "-:-/km";
  const m = Math.floor(v / 60);
  const s = String(Math.round(v % 60)).padStart(2, "0");
  return `${m}:${s} /km`;
}

// extract timeline data from payload
const t = PAYLOAD.timeline.t_s;
const paceVals = PAYLOAD.timeline.pace_s_per_km;
const hrVals = PAYLOAD.timeline.hr_bpm;

// build datasets for chart.js
const paceData = t.map((sec, i) => ({ x: sec, y: paceVals[i] }));
const hrData = t.map((sec, i) => ({ x: sec, y: hrVals[i] }));

// fill and border colours for annotation boxes
const fills = [
  "rgba(249,115,22,0.12)", "rgba(25,146,212,0.12)", "rgba(16,185,129,0.12)",
  "rgba(234,179,8,0.12)", "rgba(139,92,246,0.12)", "rgba(236,72,153,0.12)",
  "rgba(14,165,233,0.12)", "rgba(34,197,94,0.12)", "rgba(239,68,68,0.12)"
];
const borders = fills.map(c => c.replace("0.12", "0.5"));

// create shaded song sections on chart
function buildSongAnnotations() {
  const anns = {};
  (PAYLOAD.segments || []).forEach((seg, i) => {
    anns[`song_${i}`] = {
      type: "box",
      xMin: seg.start_s,
      xMax: seg.end_s,
      yMin: -Infinity,
      yMax: Infinity,
      backgroundColor: fills[i % fills.length],
      borderColor: borders[i % borders.length],
      borderWidth: 1
    };
  });
  return anns;
}

// create chart for pace or heart rate
function makeChart(ctx, data, yLabel, valueFmt) {
  return new Chart(ctx, {
    type: "line",
    data: {
      datasets: [{
        data,
        borderWidth: 2,
        borderColor: yLabel.includes("Pace") ? "green" : "red",
        pointRadius: 0,
        hitRadius: 20,
        hoverRadius: 20,
        tension: 0.25,
        spanGaps: true
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      scales: {
        x: {
          type: "linear",
          title: { display: true, text: "Time (mm:ss)" },
          ticks: { callback: (v) => fmtTime(v) }
        },
        y: {
          title: { display: true, text: yLabel },
          ticks: { callback: (v) => valueFmt(v) }
        }
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: (items) => fmtTime(items[0].parsed.x), // show mm:ss in tooltip
            label: (ctx) => {
              const x = ctx.parsed.x;
              const y = ctx.parsed.y;
              const seg = (PAYLOAD.segments || []).find(
                s => x >= s.start_s && x <= s.end_s
              );
              const song = seg
                ? `${seg.track_name} — score ${seg.score ?? "-"}`
                : "No song";
              return [`${fmtTime(x)}  ${valueFmt(y)}`, song];
            }
          }
        },
        annotation: { annotations: buildSongAnnotations() }
      }
    }
  });
}

// initialise both charts
makeChart(document.getElementById("paceChart"), paceData, "Pace (min/km)", fmtPace);
makeChart(document.getElementById("hrChart"), hrData, "Heart rate (bpm)", v => v == null ? "–" : `${Math.round(v)} bpm`);

const list = document.getElementById("songList");
let sortByScore = false;

// renders the song list under the chart
function renderSongList() {
  if (!PAYLOAD.segments || PAYLOAD.segments.length === 0) {
    list.innerHTML = '<div class="muted-text">No songs overlapped this run.</div>';
    return;
  }
  const segs = [...PAYLOAD.segments];
  if (sortByScore) segs.sort((a, b) => (b.score ?? 0) - (a.score ?? 0)); // sort if toggled

  list.innerHTML = segs.map((s, i) => `
    <div class="song-item">
      <div class="song-meta">
        <div class="song-color" style="background:${fills[i % fills.length]}"></div>
        <div>
          <div style="font-weight:600">${i + 1}. ${s.track_name}</div>
          <div class="muted-text">${s.artist_name} • ${fmtTime(s.start_s)} → ${fmtTime(s.end_s)}</div>
        </div>
      </div>
      <div class="tag">${s.score ?? "no score"}</div>
    </div>
  `).join("");
}
renderSongList();

// sort button for toggling between time and score
document.addEventListener("DOMContentLoaded", () => {
  const sortBtn = document.getElementById("sortBtn");
  if (sortBtn) {
    sortBtn.addEventListener("click", () => {
      sortByScore = !sortByScore;
      sortBtn.innerText = sortByScore ? "Sort by Time" : "Sort by Score";
      renderSongList();
    });
  }
});
