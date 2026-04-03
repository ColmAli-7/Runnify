// dark mode toggle
const toggle = document.getElementById("theme-toggle");
const prefersDark =
	window.matchMedia &&
	window.matchMedia("(prefers-color-scheme: dark)").matches;
const storedTheme = localStorage.getItem("theme");
if (storedTheme === "dark" || (!storedTheme && prefersDark)) {
	document.body.classList.add("dark"); // enable dark mode on load
}
toggle.addEventListener("click", () => {
	document.body.classList.toggle("dark"); // toggle dark/light mode
	const isDark = document.body.classList.contains("dark");
	localStorage.setItem("theme", isDark ? "dark" : "light"); // remember user preference
});

// flash message auto hide
document.addEventListener("DOMContentLoaded", () => {
	const flashes = document.querySelectorAll(".flash");
	flashes.forEach((flash) => {
		setTimeout(() => {
			flash.classList.add("hide"); // fade out after 4s
			setTimeout(() => flash.remove(), 1000); // remove from dom
		}, 4000);
	});
});

// password visibility toggle
function togglePassword(btn) {
	const input = btn.previousElementSibling; // find related input field
	if (input.type === "password") {
		input.type = "text"; // show password
		btn.textContent = "●";
	} else {
		input.type = "password"; // hide password
		btn.textContent = "●";
	}
}
