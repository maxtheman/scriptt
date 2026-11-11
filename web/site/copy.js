// Copies the install prompt of the page (the <template id="prompt">) to the clipboard.
const button = document.getElementById("copy");
button.addEventListener("click", async () => {
  const words = document.getElementById("prompt").innerHTML.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
  try { await navigator.clipboard.writeText(words); }
  catch { const area = Object.assign(document.createElement("textarea"), { value: words }); document.body.append(area); area.select(); document.execCommand("copy"); area.remove(); }
  button.textContent = "Copied";
  setTimeout(() => { button.textContent = "Copy the install prompt"; }, 3000);
});
