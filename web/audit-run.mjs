// Runs web/site/audit.js in a headless Chrome over the Chrome DevTools Protocol, so every pointer and key event of the audit is a
// trusted browser input event (Input.dispatchMouseEvent / Input.dispatchKeyEvent), not a script-made event.
//   node web/audit-run.mjs [--accept] [--shots DIR] e6741406 f20003a1 ...
// The page calls window.cdpInput(json) (a Runtime binding); this script performs the gesture and resolves the page's promise.
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const args = process.argv.slice(2);
const accept = args.includes("--accept");
const shotsAt = args.includes("--shots") ? args[args.indexOf("--shots") + 1] : null;
const ids = args.filter((a, i) => !a.startsWith("--") && args[i - 1] !== "--shots" && args[i - 1] !== "--eval");
const evalFile = args.includes("--eval") ? args[args.indexOf("--eval") + 1] : null;
const URL0 = process.env.BOARD || "http://127.0.0.1:2801/index.html";
const PORT = 9337;
const chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const profile = join(process.env.TMPDIR || tmpdir(), "board5-chrome-" + Date.now());
const proc = spawn(chrome, ["--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, "--window-size=1440,900", "--no-first-run", "--hide-scrollbars", "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let ws, seq = 0;
const pending = new Map(), handlers = [];
async function connect() {
  for (let i = 0; i < 50; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json();
      const page = list.find((t) => t.type === "page");
      if (page) { ws = new WebSocket(page.webSocketDebuggerUrl); break; }
    } catch {}
    await sleep(200);
  }
  await new Promise((r) => ws.addEventListener("open", r, { once: true }));
  ws.addEventListener("message", (m) => {
    const j = JSON.parse(m.data);
    if (j.id && pending.has(j.id)) { pending.get(j.id)(j); pending.delete(j.id); }
    else for (const h of handlers) h(j);
  });
}
const send = (method, params = {}) => new Promise((r) => { const id = ++seq; pending.set(id, r); ws.send(JSON.stringify({ id, method, params })); });
const evaluate = async (expr) => { const r = await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true }); if (r.result && r.result.exceptionDetails) throw new Error(JSON.stringify(r.result.exceptionDetails).slice(0, 800)); return r.result && r.result.result && r.result.result.value; };
const KEYS = { Enter: [13, "\r"], Escape: [27], Tab: [9], ArrowRight: [39], ArrowLeft: [37], ArrowUp: [38], ArrowDown: [40], PageDown: [34], PageUp: [33], " ": [32, " "] };
let buttons = 0;
async function gesture(g) {
  if (g.type === "noop") return;
  if (g.type === "key") {
    const [code, text] = KEYS[g.key] || [g.key.toUpperCase().charCodeAt(0), g.key];
    const mods = g.shiftKey ? 8 : 0;
    await send("Input.dispatchKeyEvent", { type: text ? "keyDown" : "rawKeyDown", key: g.key, text, unmodifiedText: text, windowsVirtualKeyCode: code, modifiers: mods });
    await send("Input.dispatchKeyEvent", { type: "keyUp", key: g.key, windowsVirtualKeyCode: code, modifiers: mods });
    return;
  }
  if (g.type === "shot") { const r = await send("Page.captureScreenshot", { format: "png" }); if (shotsAt) { mkdirSync(shotsAt, { recursive: true }); writeFileSync(join(shotsAt, g.name + ".png"), Buffer.from(r.result.data, "base64")); } return; }
  const type = { pointerdown: "mousePressed", pointermove: "mouseMoved", pointerup: "mouseReleased" }[g.type];
  if (g.type === "pointerdown") buttons = 1;
  if (g.type === "pointerup") buttons = 0;
  await send("Input.dispatchMouseEvent", { type, x: g.x, y: g.y, button: g.type === "pointermove" ? (buttons ? "left" : "none") : "left", buttons, clickCount: g.type === "pointermove" ? 0 : 1 });
}
await connect();
await send("Runtime.enable");
await send("Page.enable");
await send("Emulation.setDeviceMetricsOverride", { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
await send("Runtime.addBinding", { name: "cdpInput" });
await send("Network.enable");
const net = []; // what the browser really sent to the engine, seen by Chrome (not the page's own log)
handlers.push((j) => { if (j.method === "Network.requestWillBeSent" && j.params.request.method === "POST") { const u = new URL(j.params.request.url); net.push({ path: u.pathname, body: j.params.request.postData ? JSON.parse(j.params.request.postData) : null }); } });
const logs = [];
handlers.push(async (j) => {
  if (j.method === "Runtime.bindingCalled" && j.params.name === "cdpInput") {
    const g = JSON.parse(j.params.payload);
    try { await gesture(g); } catch (e) { logs.push("gesture " + e); }
    await send("Runtime.evaluate", { expression: `window.__cdpNet = ${JSON.stringify(net)}; window.__cdpDone(${JSON.stringify(g.id)})` });
  }
  if (j.method === "Runtime.exceptionThrown") logs.push("exception " + JSON.stringify(j.params.exceptionDetails.exception && j.params.exceptionDetails.exception.description || j.params.exceptionDetails.text).slice(0, 400));
  if (j.method === "Runtime.consoleAPICalled" && j.params.type === "error") logs.push("console.error " + JSON.stringify(j.params.args.map((a) => a.value || a.description)).slice(0, 400));
});
await send("Page.navigate", { url: URL0 + "?r=" + (ids[0] || "") });
for (let i = 0; i < 120; i++) { await sleep(250); if (await evaluate("!!(window.S && S.base && document.querySelector('#board svg'))").catch(() => false)) break; }
await evaluate(`new Promise((res) => { const s = document.createElement("script"); s.src = "/audit.js?" + Date.now(); s.onload = res; document.head.appendChild(s); })`);
let out;
try {
  if (evalFile) out = await evaluate((await import("node:fs")).readFileSync(evalFile, "utf8"));
  else out = await evaluate(`audit5(${JSON.stringify(ids)}, ${JSON.stringify({ accept })})`);
} catch (e) { out = { error: String(e) }; }
console.log(JSON.stringify({ result: out, logs }, null, 1));
proc.kill();
process.exit(0);
