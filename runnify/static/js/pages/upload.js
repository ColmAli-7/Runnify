/**
 * Import page: show the chosen file's name, accept a dropped file, and send the
 * upload with a progress bar, staying on the page until the server has the file.
 * The form works without it, as an ordinary upload.
 */
const form = document.querySelector("[data-upload]");

if (form) {
  const zone = form.querySelector("[data-dropzone]");
  const input = form.querySelector("[data-file]");
  const name = form.querySelector("[data-file-name]");
  const button = form.querySelector("button[type=submit]");
  const sending = form.querySelector("[data-upload-progress]");
  const message = form.querySelector("[data-upload-message]");
  const bar = form.querySelector("[data-upload-bar]");
  const announce = form.querySelector("[data-upload-announce]");
  const problem = form.querySelector("[data-upload-error]");
  const original = name.textContent;
  const label = button.textContent;
  const limit = Number(form.dataset.maxBytes) || Infinity;
  const tooLarge = `That file is larger than ${Math.floor(limit / (1024 * 1024))} MB.`;

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

  // leaving the page would stop the upload, so the browser asks first
  const stay = (event) => {
    event.preventDefault();
    event.returnValue = "";
  };

  const progress = (text, percent) => {
    message.textContent = text;
    bar.setAttribute("aria-label", text);
    if (percent === null) bar.removeAttribute("value");
    else bar.value = percent;
  };

  const fail = (text) => {
    window.removeEventListener("beforeunload", stay);
    sending.hidden = true;
    problem.textContent = text;
    problem.hidden = false;
    button.disabled = false;
    button.textContent = label;
  };

  form.addEventListener("submit", (event) => {
    const file = input.files?.[0];
    if (!file) return; // the browser asks for one
    event.preventDefault();
    problem.hidden = true;
    if (file.size > limit) {
      fail(tooLarge);
      return;
    }
    button.disabled = true;
    button.textContent = "Uploading";
    sending.hidden = false;
    progress("Uploading: 0%", 0);
    announce.textContent = "Uploading";
    window.addEventListener("beforeunload", stay);

    const request = new XMLHttpRequest();
    request.open("POST", form.action);
    request.setRequestHeader("Accept", "application/json");
    request.upload.addEventListener("progress", (step) => {
      if (!step.lengthComputable) return;
      const percent = Math.floor((100 * step.loaded) / step.total);
      progress(`Uploading: ${percent}%`, percent);
    });
    request.upload.addEventListener("load", () => {
      progress("Checking the file", null);
      announce.textContent = "Uploaded. Checking the file";
    });
    request.addEventListener("load", () => {
      if (request.status === 413) {
        fail(tooLarge);
        return;
      }
      if (request.status === 429) {
        fail("That's a lot of uploads in a row. Please wait a while and try again.");
        return;
      }
      window.removeEventListener("beforeunload", stay);
      let target = request.responseURL || window.location.href;
      try {
        target = JSON.parse(request.responseText).location || target;
      } catch {
        // not the import's answer (an expired form, say): go and see the page
      }
      window.location.assign(target);
    });
    request.addEventListener("error", () =>
      fail("The upload didn't get through. Check your connection and try again."),
    );
    request.send(new FormData(form));
  });
}
