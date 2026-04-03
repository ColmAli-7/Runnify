// handles spotify history zip upload dropzone
document.addEventListener("DOMContentLoaded", () => {
	const dz = document.getElementById("dropzone");
	const fileInput = document.getElementById("file-input"); 
	const dzText = document.getElementById("dz-text"); 
	const dzFile = document.getElementById("dz-file"); 
	const submitBtn = document.getElementById("submit-btn"); 

	function enableSubmit() {
		submitBtn.disabled = false; // enable submit once valid file is chosen
		submitBtn.classList.add("enabled");
	}

	dz.addEventListener("click", () => fileInput.click()); // click to open file picker

	dz.addEventListener("dragover", (e) => {
		e.preventDefault();
		dz.classList.add("dragover"); // highlight on drag
	});

	dz.addEventListener("dragleave", () => dz.classList.remove("dragover")); // remove highlight when leaving

	dz.addEventListener("drop", (e) => {
		e.preventDefault();
		dz.classList.remove("dragover");
		const f = e.dataTransfer.files[0]; // get dropped file
		if (!f) return;
		if (!f.name.toLowerCase().endsWith(".zip")) {
			// must be .zip file
			alert("Please drop a .zip file.");
			return;
		}
		fileInput.files = e.dataTransfer.files; // set input to dropped file
		dzText.hidden = true; 
		dzFile.hidden = false; 
		dzFile.textContent = f.name;
		enableSubmit(); 
	});

	fileInput.addEventListener("change", () => {
		// triggered when file selected manually
		const f = fileInput.files[0];
		if (!f) return;
		if (!f.name.toLowerCase().endsWith(".zip")) {
			// must be .zip file
			alert("Please choose a .zip file.");
			fileInput.value = "";
			return;
		}
		dzText.hidden = true;
		dzFile.hidden = false;
		dzFile.textContent = f.name;
		enableSubmit();
	});
});
