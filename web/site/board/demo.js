// With ?demo, the board's engine runs in this page: Pyodide loads the shipped harness.py, agree.py and scriptt16.py, and
// answers the board's requests (GET /readings, /worlds, /log; POST /edit, /edits, /accept, /restore) on a store in memory
// that starts from demo/events.jsonl. Rerun needs d1, which the page does not have. Without ?demo this file does nothing.
(() => {
  if (!new URL(location).searchParams.has("demo")) return;
  const real = window.fetch.bind(window);
  const note = (text) => { const dock = document.getElementById("dock"); if (dock && !dock.querySelector("button")) dock.textContent = text; };
  addEventListener("DOMContentLoaded", () => note("◌ loading the engine: Python 3.14 in this page (Pyodide)"));
  const ready = (async () => {
    await new Promise((loaded, failed) => {
      const script = Object.assign(document.createElement("script"), { src: "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/pyodide.js", onload: loaded, onerror: failed });
      document.head.append(script);
    });
    const py = await loadPyodide();
    py.FS.mkdirTree("/demo/.scriptt");
    const files = { "../harness.py": "harness.py", "../agree.py": "agree.py", "../scriptt16.py": "scriptt16.py", "demo/world.py": "world.py", "demo/events.jsonl": "events.jsonl" };
    for (const [from, to] of Object.entries(files)) py.FS.writeFile("/demo/.scriptt/" + to, await (await real(from)).text());
    py.runPython(`
import json, sys
sys.path.insert(0, "/demo/.scriptt")
import agree, harness, scriptt16

def answer(path, body):
    try:
        if path == "/readings":
            return 200, scriptt16.saved(harness.store())
        if path == "/worlds":
            return 200, {agree.identity(harness.world()): agree.world_record(harness.world())}
        if path == "/log":
            return 200, []
        return 200, harness.posted(path, json.loads(body))
    except (LookupError, ValueError, TypeError, IndexError, AttributeError) as error:
        return 400, {"error": f"{type(error).__name__}: {error}"}
`);
    note("");
    return py;
  })();
  ready.catch((error) => { note(`✕ the engine did not load: ${error}`); if (parent !== window) parent.postMessage({ scriptt: "failed" }, location.origin); });
  const ours = new Set(["/readings", "/worlds", "/log", "/edit", "/edits", "/accept", "/restore", "/rerun"]);
  window.fetch = async (input, init = {}) => {
    const path = new URL(typeof input === "string" ? input : input.url, location).pathname;
    if (!ours.has(path)) return real(input, init);
    const reply = (status, body) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
    if (path === "/rerun") return reply(400, { error: "rerun asks d1, and this page has no d1" });
    const py = await ready;
    const [status, body] = py.globals.get("answer")(path, init.body || "null").toJs({ dict_converter: Object.fromEntries });
    return reply(status, body);
  };
})();
