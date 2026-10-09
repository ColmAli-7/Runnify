/**
 * Import page: show the chosen file's name, accept a dropped file, and stop a
 * second submit while the upload is on its way. The form works without it.
 */
const form = document.querySelector("[data-upload]");

if (form) {
  const zone = form.querySelector("[data-dropzone]");
  const input = form.querySelector("[data-file]");
  const name = form.querySelector("[data-file-name]");
  const button = form.querySelector("button[type=submit]");
  const original = name.textContent;

  const showFile = () => {
    const file = input.files?.[0];
    name.textContent = file ? file.name : original;
    zone.classList.toggle("has-file", Boolean(file));
  };

  input.addEventListener("change", showFile);
  zone.addEventListener("dragover", (event) => {
    event.preventDefault();
    zone.classList.add("is-over");
  });
  zone.addEventListener("dragleave", () => zone.classList.remove("is-over"));
  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    zone.classList.remove("is-over");
    if (event.dataTransfer?.files?.length) {
      input.files = event.dataTransfer.files;
      showFile();
    }
  });

  form.addEventListener("submit", () => {
    button.disabled = true;
    button.textContent = "Uploading";
  });
}
