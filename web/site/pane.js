// The reading pane of the landing page: the copy is plain HTML first (readable and crawlable); the board loads behind it and
// says when it has drawn ({scriptt: "ready"}), or that its engine did not load ({scriptt: "failed"}). Same origin only.
const pane = document.getElementById("reading"), frame = document.getElementById("boardframe");
addEventListener("message", (event) => {
  if (event.origin !== location.origin || event.source !== frame.contentWindow || !event.data) return;
  if (event.data.scriptt === "ready") { pane.classList.add("ready"); frame.tabIndex = 0; }
  if (event.data.scriptt === "failed") { document.getElementById("loading").classList.add("failed"); document.getElementById("loadtext").textContent = "✕ the engine did not load"; frame.remove(); }
});
