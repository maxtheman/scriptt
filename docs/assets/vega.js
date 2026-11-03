// Draws each ```vega-lite fence of the built pages with vega-embed. The fence holds the spec as JSON text.
// Each chart is drawn on its own, so a chart that fails shows its error and does not stop the others.
function drawCharts() {
  document.querySelectorAll("div.vega-lite:not([data-drawn])").forEach((div) => {
    div.setAttribute("data-drawn", "1");
    try {
      const spec = JSON.parse(div.textContent);
      div.textContent = "";
      vegaEmbed(div, spec, { actions: false, renderer: "svg" }).catch((error) => { div.textContent = "chart error: " + error; });
    } catch (error) {
      div.textContent = "chart error: " + error;
    }
  });
}
if (typeof document$ !== "undefined") { document$.subscribe(drawCharts); } else { document.addEventListener("DOMContentLoaded", drawCharts); }
