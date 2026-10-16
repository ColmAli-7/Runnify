// Runs in <head>, before the page paints: applies the theme the runner chose
// (Settings or the footer) so a dark page never flashes light, and marks the
// page as scripted so stylesheets can prepare entrances. Not a module, so it
// blocks rendering for the few lines it takes.
(function () {
  var root = document.documentElement;
  root.classList.add("js");
  try {
    var saved = window.localStorage.getItem("runnify-theme");
    if (saved === "light" || saved === "dark") root.setAttribute("data-theme", saved);
  } catch (error) {
    // storage is blocked: follow the system theme
  }
  if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: no-preference)").matches) {
    root.classList.add("motion-ok");
  }
})();
