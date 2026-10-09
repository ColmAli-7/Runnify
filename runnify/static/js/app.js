// Small enhancements shared by every page. Everything works without JavaScript;
// this only makes it nicer. No inline handlers: behaviour is attached here via
// data attributes, which keeps the Content-Security-Policy strict.

// account menu: close on Escape, on outside click, and when focus leaves it
for (const menu of document.querySelectorAll("[data-menu]")) {
  const close = () => menu.removeAttribute("open");
  document.addEventListener("click", (event) => {
    if (!menu.contains(event.target)) close();
  });
  menu.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && menu.open) {
      close();
      menu.querySelector("summary").focus();
    }
  });
  menu.addEventListener("focusout", (event) => {
    if (!menu.contains(event.relatedTarget)) close();
  });
}

// dismissible notices
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-dismiss]");
  if (button) button.closest(".notice")?.remove();
});

// show / hide password
for (const toggle of document.querySelectorAll("[data-reveal]")) {
  const input = document.getElementById(toggle.dataset.reveal);
  if (!input) continue;
  toggle.addEventListener("click", () => {
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    toggle.textContent = show ? "Hide" : "Show";
    toggle.setAttribute("aria-pressed", String(show));
    input.focus();
  });
}

// forms that need a second thought (deleting, disconnecting) ask first
document.addEventListener("submit", (event) => {
  const message = event.target.dataset?.confirm;
  if (message && !window.confirm(message)) event.preventDefault();
});

// copy buttons (recovery codes)
for (const button of document.querySelectorAll("[data-copy]")) {
  button.addEventListener("click", async () => {
    const source = document.getElementById(button.dataset.copy);
    if (!source || !navigator.clipboard) return;
    await navigator.clipboard.writeText(source.innerText.trim());
    const label = button.textContent;
    button.textContent = "Copied";
    setTimeout(() => (button.textContent = label), 1600);
  });
}

// print buttons
for (const button of document.querySelectorAll("[data-print]")) {
  button.addEventListener("click", () => window.print());
}
