/**
 * Background jobs: keep a running Garmin sync's or history import's progress moving
 * by asking /jobs every couple of seconds while one runs. A page that shows the job
 * in full ([data-job-reload]) reloads when it ends, to show how it went; elsewhere
 * the job's notice says so. Screen readers hear each new stage and the end, not
 * every step. Without scripts the progress shown is as of the page load.
 */
const EVERY = 2000; // ms between checks while a job runs
const QUIET = 10000; // ms to wait after a check that failed (offline for a moment, say)

const watched = [...document.querySelectorAll("[data-job]")];
const kinds = new Set(watched.map((element) => element.dataset.job));
const reloads = new Set(
  [...document.querySelectorAll("[data-job-reload]")].flatMap((element) =>
    element.dataset.jobReload.split(" "),
  ),
);
const url = watched[0]?.dataset.jobsUrl;

// "Scoring the songs on your runs: 3 of 12" is at the stage "Scoring the songs on your runs"
const stageOf = (message) => (message || "").split(":")[0];
const stages = new Map(
  watched.map((element) => [
    element.dataset.job,
    stageOf(element.querySelector("[data-job-message]").textContent),
  ]),
);

function show(kind, job) {
  const message = job.message || "Getting started";
  const announce = stageOf(message) !== stages.get(kind);
  stages.set(kind, stageOf(message));
  for (const element of document.querySelectorAll(`[data-job="${kind}"]`)) {
    const bar = element.querySelector("[data-job-bar]");
    element.querySelector("[data-job-message]").textContent = message;
    bar.setAttribute("aria-label", message);
    if (job.percent === null) {
      bar.removeAttribute("value"); // how far isn't known yet
      bar.textContent = "";
    } else {
      bar.value = job.percent;
      bar.textContent = `${job.percent}%`;
    }
    if (announce) element.querySelector("[data-job-announce]").textContent = stageOf(message);
  }
}

// a reload would throw away what someone is typing (into the Garmin sign-in, say)
const edited = () =>
  [...document.querySelectorAll("input, textarea")].some((field) =>
    field.type === "checkbox" || field.type === "radio"
      ? field.checked !== field.defaultChecked
      : !["hidden", "file"].includes(field.type) && field.value !== field.defaultValue,
  );

function end(kind, job) {
  if (reloads.has(kind) && !edited()) {
    window.location.reload();
    return;
  }
  const ok = job.state === "ok";
  for (const element of document.querySelectorAll(`[data-job="${kind}"]`)) {
    const notice = element.closest("[data-job-notice]");
    const outcome =
      ok || job.state === "failed"
        ? job.message
        : notice?.dataset.endedFailed || "It stopped before it finished.";
    element.querySelector("[data-job-message]").textContent = outcome;
    element.querySelector("[data-job-bar]").hidden = true;
    element.querySelector("[data-job-announce]").textContent = outcome;
    if (notice) {
      notice.classList.replace("notice--job", ok ? "notice--success" : "notice--error");
      notice.querySelector("[data-job-title]").textContent = outcome;
      element.querySelector("[data-job-message]").hidden = true;
      notice.querySelector("[data-job-done]").hidden = !ok;
    }
  }
}

async function check() {
  if (document.hidden) {
    document.addEventListener("visibilitychange", check, { once: true });
    return;
  }
  let jobs;
  try {
    const response = await fetch(url, { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(`status ${response.status}`);
    jobs = await response.json();
  } catch {
    window.setTimeout(check, QUIET);
    return;
  }
  for (const kind of [...kinds]) {
    const job = jobs[kind];
    if (!document.querySelector(`[data-job="${kind}"]`)) kinds.delete(kind); // its notice was dismissed
    if (!job || !kinds.has(kind)) continue;
    if (job.running) {
      show(kind, job);
    } else {
      kinds.delete(kind);
      end(kind, job);
    }
  }
  if (kinds.size) window.setTimeout(check, EVERY);
}

if (url && kinds.size) window.setTimeout(check, EVERY);
