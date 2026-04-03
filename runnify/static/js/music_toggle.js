// toggles between showing all runs or only those with music
document.getElementById("musicFilter").addEventListener("change", function () {
	const url = new URL(window.location); 
	if (this.checked) url.searchParams.set("music_only", "true"); // enable music filter
	else url.searchParams.delete("music_only"); 
	window.location = url; // reload page with updated query
});
