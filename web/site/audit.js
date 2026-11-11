// audit.js: acceptance probes for the board (criteria: web/notes/ACCEPTANCE-V11.md, written before the build).
// Open index.html?audit and run `await AUDIT()`. Every move is a PointerEvent dispatched at element coordinates, the target found with
// document.elementFromPoint at the pointer position, so Dragology's own press, move, drop targets and release run. A probe reads the
// DOM or the engine's files; it never sets state, never remounts, never edits storage. (`?audit` only names the draft storage apart from the real one.)
(() => {
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const $ = (id) => document.getElementById(id), $$ = (s, r = document) => [...r.querySelectorAll(s)];
const ctr = (el) => { const r = el.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; };
function fire(type, x, y) { const t = document.elementFromPoint(x, y) ?? document.body; t.dispatchEvent(new PointerEvent(type, { bubbles: true, cancelable: true, composed: true, clientX: x, clientY: y, pointerId: 1, pointerType: "mouse", isPrimary: true, button: 0, buttons: type === "pointerup" || type === "pointerover" ? 0 : 1 })); return t; }
async function press(el, to, { hold = false, steps = 10, settle = 90 } = {}) {
  await uncover(el);   // pointerdown on the element's centre, moves to `to` (element or [x,y]), then releases unless hold
  const [x0, y0] = ctr(el), [x1, y1] = Array.isArray(to) ? to : ctr(to);
  fire("pointerdown", x0, y0);
  for (let i = 1; i <= steps; i++) { fire("pointermove", x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps); await sleep(16); }
  await sleep(settle);
  if (hold) return { x: x1, y: y1 };
  fire("pointerup", x1, y1); await sleep(650); return { x: x1, y: y1 };
}
const release = async (p) => { fire("pointerup", p.x, p.y); await sleep(650); };
const uncover = async (el) => { const c = $("sel"); if (c && c.style.display !== "none") { const r = c.getBoundingClientRect(), [x, y] = ctr(el); if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) { document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); await sleep(160); } } };   // a user closes a card that covers what they want to press
const click = async (el) => { await uncover(el); const [x, y] = ctr(el); fire("pointerdown", x, y); await sleep(20); fire("pointerup", x, y); await sleep(250); };
const byK = (k) => document.querySelector(`#board [data-k="${k}"]`);
const places = () => $$("#board [data-role=place]").map((e) => `${e.dataset.place}=${e.querySelector("text")?.textContent ?? ""}|${e.dataset.kind}`).join(";");
const placeText = (id) => { const e = byK(id); return e ? [...e.querySelectorAll("text")].map((t) => t.textContent).join(" ") : null; };
const pick = async (i) => { window.AUDIT_AT = "pick " + i; $("pick").value = String(i); $("pick").dispatchEvent(new Event("change")); await sleep(300); };
const revert = async () => { const b = $("reset"); if (!b.disabled) { b.click(); await sleep(300); } };
const parseEngine = (t) => Model.parseEngine(t);
const farPoint = () => { const r = document.querySelector("#board svg").getBoundingClientRect(); return [r.left + 60, r.bottom - 14]; };
const out = []; let scoreN = 0, scoreD = 0;
const P = (id, ok, note, partial = false) => { scoreD++; const v = partial ? (ok ? 0.5 : 0) : (ok ? 1 : 0); scoreN += v; out.push(`${v === 1 ? "PASS" : v === 0.5 ? "HALF" : "FAIL"} ${id} ${note}`); };

window.AUDIT = async function () {
  out.length = 0; scoreN = 0; scoreD = 0; window.AUDIT_LOG = out; window.AUDIT_AT = "start";
  window.__errs = []; addEventListener("error", (e) => window.__errs.push(e.message)); addEventListener("unhandledrejection", (e) => window.__errs.push(String(e.reason)));
  { const ce = console.error.bind(console); console.error = (...a) => { window.__errs.push(a.map(String).join(" ").slice(0, 160)); ce(...a); }; }
  try { Object.keys(localStorage).filter((k) => k.startsWith("scriptt-audit:")).forEach((k) => localStorage.removeItem(k)); } catch {}   // only the audit's own draft namespace
  const eng = await (await fetch("engine/readings.json")).text().then(parseEngine), wor = await (await fetch("engine/worlds.json")).text().then(parseEngine);
  const B = window.BOARD, N = eng.length;
  const iSpec = eng.findIndex((r) => r.case === "C15 specimen"), iEdit = eng.findIndex((r) => /rebound/.test(r.case));
  await pick(iSpec); await revert();
  const world = (r) => wor[r.world], inner = (t) => (t.constructor === "Many" || t.constructor === "Maybe" || t.constructor === "Later" ? inner(t.of) : t);
  const nameOf = Model.nameOf;

  // ---- A data
  const res = performance.getEntriesByType("resource").map((e) => e.name);
  P("A01", res.some((n) => /engine\/readings\.json/.test(n)) && res.some((n) => /engine\/worlds\.json/.test(n)) && $$("#pick option").filter((o) => !/^STRESS/.test(o.text)).length === N && N >= 38 && $("pick").options[iSpec].text.includes("Redesign the mod. Then show it. Test the search too.") && iSpec === 0, `fetched both files; ${$$("#pick option").length} readings (file has ${N}); specimen first`);
  { // A02: every drawn token of every reading is in the data or the fixed UI list
    const UI = ["ready", "waits", "open", "none", "later", "wraps", "quoted"];
    const add = (set, v) => String(v ?? "").split(/[^\p{L}\d_]+/u).forEach((w) => w && set.add(w));
    const unknown = new Set();
    for (let i = 0; i < N; i++) {
      const r = eng[i], w = wor[r.world], allowed = new Set(UI);   // names come from: the message, the world's declarations (types, members, functions, parameters, fields, constructors, kinds), and the record's reasons
      add(allowed, r.text); r.phrases.forEach((p) => { add(allowed, p.unresolved?.reason); add(allowed, p.quotes); });
      const walk = (v) => { if (Array.isArray(v)) v.forEach(walk); else if (v && typeof v === "object") { if (v.reason !== undefined) add(allowed, v.reason); Object.values(v).forEach(walk); } };
      walk(r.phrases);
      for (const [n, t] of Object.entries(w.types)) { add(allowed, n); add(allowed, t.kind); const m = (x) => { if (!x) return; add(allowed, x.base); add(allowed, x.brand); add(allowed, x.sum); add(allowed, x.product); add(allowed, x.member); add(allowed, x.words); add(allowed, x["constructor"]); Object.keys(x.fields ?? {}).forEach((k) => add(allowed, k)); m(x.of); (x.alternatives ?? []).forEach(m); Object.values(x.fields ?? {}).forEach(m); }; m(t); }
      for (const [n, f] of Object.entries(w.functions)) { add(allowed, n); f.parameters.forEach(([p]) => add(allowed, p)); }
      for (const [c, d] of Object.entries(w.constructors)) { add(allowed, c); add(allowed, d.kind); }
      await pick(i); await revert(); $$("#board svg text").forEach((t) => (t.textContent.match(/[\p{L}\d_]+/gu) ?? []).forEach((x) => { if (!allowed.has(x) && !/^\d+$/.test(x)) unknown.add(`${i}:${x}`); }));
    }
    P("A02", unknown.size === 0, `fixed UI words: ${UI.join(", ")}; tokens not in the data: ${[...unknown].join(", ") || "none"}`);
  }
  { // A03
    const bad = [];
    for (let i = 0; i < N; i++) {
      await pick(i); await revert(); const r = eng[i];
      for (const p of r.phrases) for (const t of p.terms) if (!document.querySelector(`#board [data-op="${t.id}"]`)) bad.push(`${i}: op ${t.id}`);
      for (const c of r.constants) { const u = document.getElementById(`u-${c.at[0]}`); if (!u || u.dataset.text !== r.text.slice(c.at[0], c.at[1]) || u.dataset.role !== "value") bad.push(`${i}: ${c.constant}`); }
      { const buf = Array.from(r.text, (ch) => (/\s/.test(ch) ? " " : "\u0000")); $$("#board [data-role=word],#board [data-role=value]").forEach((u) => { const s0 = Number(u.dataset.k.slice(2)); [...u.dataset.text].forEach((ch, k) => { buf[s0 + k] = ch; }); }); if (buf.join("") !== r.text.replace(/\s/g, " ")) bad.push(`${i}: the message is not whole on the board`); }   // the board's units rebuild the message exactly
      r.phrases.forEach((p, pi) => (Array.isArray(p.unresolved) ? p.unresolved : p.unresolved ? [p.unresolved] : []).forEach((u, ix) => { if (!document.querySelector(`#board [data-k="un-${pi}-${ix}"]`)) bad.push(`${i}: unresolved ${pi}/${ix}`); }));
    }
    P("A03", bad.length === 0, `${N} readings; ${bad.length} missing ${bad.slice(0, 4).join(" | ")}`);
  }
  { // A04: four marks for four kinds of missing
    const found = {}, find = async (pred, key, sel) => { for (let i = 0; i < N && !found[key]; i++) if (pred(eng[i])) { await pick(i); await revert(); const e = document.querySelector(sel); if (e) found[key] = { i, e, dash: e.querySelector("rect.mark")?.getAttribute("stroke-dasharray") ?? null, txt: e.textContent }; } };
    const anyV = (r, f) => r.phrases.some((p) => p.terms.some((t) => JSON.stringify(t.arguments).includes(f)));
    await find((r) => anyV(r, '"hole"'), "hole", '#board [data-missing=hole]');
    await find((r) => anyV(r, '"empty"'), "empty", '#board [data-missing=empty]');
    await find((r) => anyV(r, '"several":[]'), "list", '#board [data-missing=list]');
    await find((r) => r.phrases.some((p) => (p.unresolved ?? []).length || (!Array.isArray(p.unresolved) && p.unresolved)), "unresolved", '#board [data-missing=unresolved]');
    const dashes = Object.values(found).map((f) => f.dash), reasons = found.hole && /rejected|no candidate|bounded|cleared|open/.test(found.hole.txt) && found.unresolved && /rejected|bounded|no candidate/.test(found.unresolved.txt);
    P("A04", Object.keys(found).length === 4 && new Set(dashes).size === 4 && !!reasons, `found ${Object.keys(found).join(",")} dashes ${JSON.stringify(dashes)} hole text "${found.hole?.txt}" unresolved "${found.unresolved?.txt}"`);
  }
  await pick(iSpec); await revert();

  // ---- B every piece draggable
  { const kinds = Object.create(null); const fails = [];
    for (const i of [0, 7, 10, 20]) {
      await pick(i); await revert();
      const els = $$("#board [data-grab]");
      for (const e of els) {
        e.scrollIntoView({ block: "center" }); await sleep(30); const [x, y] = ctr(e), role = e.dataset.role; kinds[role] = (kinds[role] ?? 0) + 1;
        if (e.getBoundingClientRect().width === 0) continue;
        fire("pointerdown", x, y); for (let k = 1; k <= 3; k++) { fire("pointermove", x + 8 * k, y + 5 * k); await sleep(10); } await sleep(40);
        const started = !!B.HELD && B.HELD.id === e.dataset.k;
        fire("pointerup", x + 24, y + 15); await sleep(220);
        if (!started) fails.push(`${i}:${e.dataset.k}`);
        if (B.HELD) fails.push(`${i}:${e.dataset.k} still held`);
      }
      await revert();
    }
    P("B01", fails.length === 0, `roles pressed: ${JSON.stringify(kinds)}; failed to start a drag: ${fails.slice(0, 5).join(" ") || "none"}`);
  }
  { let n = 0, bad = [];
    for (const i of [0, 7, 10, 20, 42]) { await pick(i); await revert(); $$("#board svg text").forEach((t) => { n++; if (!t.closest("[data-grab]")) bad.push(`${i}:${t.textContent}`); if (getComputedStyle(t).pointerEvents === "none") bad.push(`${i}:${t.textContent} no-pointer`); }); }
    P("B02", n > 50 && bad.length === 0, `${n} text elements in 5 readings; without a grab: ${bad.slice(0, 4).join(" ") || "none"}`);
  }
  await pick(iSpec); await revert();

  // ---- C dragging
  const snap0 = places();
  const unitMod = byK("u-9"), rect0 = unitMod.getBoundingClientRect();
  const textBefore = $$("#board [data-role=word],#board [data-role=value]").map((e) => e.dataset.text).join("");
  await press(unitMod, byK("pl-1-subject"));
  const r1 = byK("u-9").getBoundingClientRect(), textAfter = $$("#board [data-role=word],#board [data-role=value]").map((e) => e.dataset.text).join("");
  const afterMod = places();
  P("C01", Math.abs(r1.left - rect0.left) <= 1 && Math.abs(r1.top - rect0.top) <= 1 && textBefore === textAfter && afterMod !== snap0, `word at ${rect0.left.toFixed(1)},${rect0.top.toFixed(1)} → ${r1.left.toFixed(1)},${r1.top.toFixed(1)}; reading changed: ${afterMod !== snap0}`);
  // C02 against the engine's own edit result
  const eShow = eng[iEdit].phrases.flatMap((p) => p.terms).find((t) => t.function === "show"), a = eShow.arguments.subject, jd = eShow.judgments;
  const st1 = byK("st-1"), sd = st1.dataset;
  const placeShow = byK("pl-1-subject");
  P("C02", placeShow.dataset.kind === "const" && placeText("pl-1-subject").includes(a.constant) && sd.pending === String(jd.pending) && sd.ready === String(jd.ready) && sd.deferred === String(jd.deferred) && sd.complete === String(jd.complete), `dropped “the mod” on show.subject → place "${placeText("pl-1-subject")}", flags pending/ready/deferred/complete = ${sd.pending}/${sd.ready}/${sd.deferred}/${sd.complete}; engine edit (${eng[iEdit].case}): ${jd.pending}/${jd.ready}/${jd.deferred}/${jd.complete}, value "${a.constant}" at ${a.at}`);
  const dragResult = places();
  await revert();
  // C03: refused
  { const s0 = places(), h = await press(byK("u-37"), byK("pl-0-surface"), { hold: true });
    const ref = document.querySelector('[data-refused="pl-0-surface"]'), why = ref?.getAttribute("data-why") ?? "";
    const preview = places(); await release(h);
    P("C03", places() === s0 && preview === s0 && /Surface/.test(why) && /Code/.test(why), `reading unchanged after drop on redesign.surface; reason while held: "${why}"`); }
  // C04: pulled out far -> cleared hole
  { await revert(); await press(byK("u-37"), byK("pl-1-subject")); const [fx, fy] = farPoint(); await press(byK("pl-1-subject"), [fx, fy]);
    const e = byK("pl-1-subject");
    P("C04", e.dataset.missing === "hole" && /cleared/.test(e.textContent), `show.subject pulled far away: kind ${e.dataset.kind} "${e.textContent}"`); }
  // C05: hole -> word
  { await press(byK("pl-1-subject"), byK("u-9")); P("C05", byK("pl-1-subject").dataset.kind === "const" && placeText("pl-1-subject").includes("the mod"), `dragged the open place onto “the mod” → "${placeText("pl-1-subject")}"`); }
  // C06: op block -> place gives a reference to the same op; operation count unchanged
  { const n0 = $$("#board [data-role=op]").length; await press(byK("op-0"), byK("pl-1-subject"));
    const e = byK("pl-1-subject"), n1 = $$("#board [data-role=op]").length;
    P("C06", e.dataset.kind === "ref" && /0/.test(e.textContent) && n0 === n1 && !!document.querySelector('#board [data-arc="op-0"]'), `op 0 dropped on show.subject → kind ${e.dataset.kind} "${e.textContent}", ops ${n0} → ${n1}, arc to op-0 drawn`); }
  // C07: apply a function: new id, old ids intact, provisional
  { await revert(); const ids0 = $$("#board [data-role=op]").map((e) => e.dataset.op); await press(byK("fn-build"), byK("u-37"));
    const ids1 = $$("#board [data-role=op]").map((e) => e.dataset.op), nu = ids1.filter((x) => !ids0.includes(x));
    P("C07", nu.length === 1 && ids0.every((x) => ids1.includes(x)) && !!document.querySelector(`#board [data-k="st-${nu[0]}"][data-provisional="1"]`), `applied build to “the search”: ids ${ids0} → ${ids1}, new ${nu}, provisional mark on the new op's flags`); }
  await revert();

  // ---- D impact before commitment
  { const np = $$("#board [data-role=place]").length;
    const h1 = await press(byK("u-37"), [farPoint()[0], farPoint()[1]], { hold: true });
    const acc = $$("#board [data-accepts]").map((e) => e.dataset.accepts), no = $$("#board [data-refused]").map((e) => e.dataset.refused), whys = $$("#board [data-refused]").every((e) => (e.dataset.why ?? "").length > 5);
    const all = new Set([...acc, ...no]);
    await release(h1);
    P("D01", acc.length + no.length === np && all.size === np && whys && no.length >= 1 && acc.length >= 1, `holding “the search”: ${acc.length} accept [${acc}], ${no.length} refuse [${no}] of ${np} places; every refusal has a reason: ${whys}`); }
  { await revert(); const s0 = places();
    const [px, py] = ctr(byK("pl-1-subject")), h2 = await press(byK("u-9"), [px, py], { hold: true });
    const during = places(), flag = byK("st-1").dataset.ready, prov = byK("st-1").dataset.provisional, bar = $("bar").textContent;
    await release(h2); const final = places();
    P("D02", during !== s0 && during === final && /show\.subject/.test(bar) && /ready/.test(bar) && flag === "true" && prov === "1", `while held over show.subject: place "${during.split(";")[1]}", ready=${flag}, provisional=${prov}; bar: "${bar}"; the drop gives the same reading as the preview: ${during === final}`); }
  { await revert(); const s0 = places(); const [fx, fy] = farPoint(); const h3 = await press(byK("u-9"), [fx, fy], { hold: true }); const during = places(); await release(h3);
    P("D03", during === s0 && places() === s0, `held far from every place: reading shown equals the base; released: unchanged`); }
  { await revert(); const ys0 = Object.fromEntries($$("#board [data-role=function]").map((e) => [e.dataset.name, e.getBoundingClientRect().top]));
    const h4 = await press(byK("u-9"), [farPoint()[0], farPoint()[1]], { hold: true });
    const fns = $$("#board [data-role=function]"), takes = fns.filter((e) => e.dataset.takes), rest = fns.filter((e) => !e.dataset.takes);
    const maxT = Math.max(...takes.map((e) => e.getBoundingClientRect().top)), minR = Math.min(...rest.map((e) => e.getBoundingClientRect().top));
    const w = wor[eng[iSpec].world], occ = (t, n) => nameOf(t) === n || (t.constructor === "Many" || t.constructor === "Maybe" || t.constructor === "Later" ? occ(t.of, n) : t.sum ? t.alternatives.some((a) => !a.member && occ(a, n)) : false);
    const expect = Object.keys(w.functions).filter((f) => w.functions[f].parameters.some(([, t]) => occ(t, "Surface"))), got = takes.map((e) => e.dataset.name);
    await release(h4);
    const ys1 = Object.fromEntries($$("#board [data-role=function]").map((e) => [e.dataset.name, e.getBoundingClientRect().top]));
    P("D04", takes.length > 0 && rest.length > 0 && maxT < minR && JSON.stringify([...got].sort()) === JSON.stringify([...expect].sort()) && Object.keys(ys0).every((k) => Math.abs(ys0[k] - ys1[k]) < 1), `holding “the mod”: ${takes.length} functions that take it come first (${takes.map((e) => e.dataset.name)}); order restored on release; model says ${expect.length} take Surface`); }
  { await revert(); const w = wor[eng[iSpec].world];
    const h5 = await press(byK("ty-Surface"), [farPoint()[0], farPoint()[1]], { hold: true });
    const litFn = $$("#board [data-role=function][data-lit]").map((e) => e.dataset.name).sort(), litP = $$("#board [data-role=place][data-lit]").map((e) => e.dataset.place);
    const occurs = (t, n) => nameOf(t) === n || (t.constructor === "Many" || t.constructor === "Maybe" || t.constructor === "Later" ? occurs(t.of, n) : t.sum ? t.alternatives.some((a) => !a.member && occurs(a, n)) : false);
    const mention = Object.keys(w.functions).filter((f) => w.functions[f].parameters.some(([, t]) => occurs(t, "Surface")) || nameOf(inner(w.functions[f].result)) === "Surface").sort();
    const s0 = places(); await release(h5);
    P("D05", JSON.stringify(litFn) === JSON.stringify(mention) && litP.includes("0.surface") && places() === s0, `holding type Surface lights functions [${litFn}] (worlds.json: [${mention}]) and places [${litP}]; nothing changed on release`); }
  { await revert(); const h6 = await press(byK("fn-build"), [farPoint()[0], farPoint()[1]], { hold: true });
    const acc = $$("#board [data-accepts]").map((e) => e.dataset.accepts), no = $$("#board [data-refused]").map((e) => [e.dataset.refused, e.dataset.why]);
    await release(h6);
    P("D06", acc.includes("u-37") && no.some(([t, w]) => t === "u-9" && /Code/.test(w)), `holding function build: fits ${acc}; refuses ${JSON.stringify(no.slice(0, 3))}`); }

  // ---- E click
  const panel = () => $("sel").textContent;
  { await revert(); await click(byK("u-9")); const p = panel(), okc = $$("#sel .chip.ok").length;
    await click(byK("u-37")); const nos = $$("#sel .chip.no").map((e) => e.textContent + " " + e.nextElementSibling?.textContent);
    P("E01", /Surface/.test(p) && /redesign|0\.surface/.test(p) && okc === 3 && nos.some((x) => /0\.surface/.test(x) && /Surface/.test(x)) && /sum/.test(p) && p.includes("the page") && p.includes("the visualization") && /kind\s*\*/.test(p) && /bound in[^a-z]*(0\.surface)/.test(p.replace(/\s+/g, " ")), `“the mod”:${okc} accepted places, kind/definition shown; “the search” refused: ${nos[0]}`); }
  { await revert(); await click(byK("u-9")); const btn = $$("#sel button[data-act]").find((b) => b.parentElement.querySelector(".chip")?.textContent.includes("1.subject")) ?? $$("#sel .row").find((r) => r.textContent.includes("1.subject"))?.querySelector("button");
    const sPre = places(); btn.click(); await sleep(500); const viaButton = places(); await revert();
    await press(byK("u-9"), byK("pl-1-subject")); const viaDrag = places();
    P("E02", viaButton !== sPre && viaButton === viaDrag, `the panel's Apply and the drag give the same reading: ${viaButton === viaDrag}`); await revert(); }
  { await revert(); await click(byK("pl-1-subject")); const p = panel(), link = $("sel").querySelector('[data-go="op-0"]');
    const rebind = $$("#sel .row").find((r) => /“the mod”/.test(r.textContent) && r.querySelector("button")), j = eng[iSpec].phrases[1].terms[0].judgments;
    const rb = rebind?.querySelector("button"); if (rb) { rb.click(); await sleep(500); }
    const flags = byK("st-1").dataset, eng2 = eng[iEdit].phrases.flatMap((x) => x.terms).find((t) => t.function === "show").judgments;
    P("E03", !!link && /same operation/.test(p) && !!rb && flags.ready === String(eng2.ready) && flags.pending === String(eng2.pending), `reference panel links op 0 (${!!link}), offers rebind to “the mod” (${!!rb}); after rebinding flags ready/pending ${flags.ready}/${flags.pending} = engine edit ${eng2.ready}/${eng2.pending}`); await revert(); }
  { await pick(iSpec); await revert(); await click(byK("op-1")); const p = panel(), w = wor[eng[iSpec].world], j = eng[iSpec].phrases[1].terms[0].judgments, chips = $$("#sel .chip").map((e) => e.textContent);
    const flagsOk = chips.includes(j.complete ? "complete" : "open") && chips.includes(j.pending ? "pending" : "available") && chips.includes(j.ready ? "ready" : "waits") && chips.includes(j.deferred ? "deferred" : "") === !!j.deferred;
    P("E04", p.includes(w.functions.show.asks) && p.includes("subject: Subject") && p.includes("→ Subject") && flagsOk && /engine/.test(p) && /reads\s*[^a-z]*0/.test(p.replace(/\s+/g, " ")) , `operation panel: asks "${w.functions.show.asks}", signature, flags ${chips.slice(0, 5).join("/")} equal the engine's (${flagsOk}), flags named as the engine's, what it reads`); }
  { await click(byK("u-9")); const first = $("sel").querySelector("b").textContent; let n = 0;
    const heads = [first];
    for (const sel of ['[data-go="ty-Surface"]', '[data-go^="fn-"]', '[data-go^="ty-"]:not([data-go="ty-Surface"])']) { const a = $("sel").querySelector(sel); if (a) { a.click(); await sleep(200); n++; heads.push($("sel").querySelector("b")?.textContent); } }   // a real click on a panel link
    let backs = 0; const seen = []; while ($("sel").querySelector("[data-back]")) { $("sel").querySelector("[data-back]").click(); await sleep(200); backs++; seen.push($("sel").querySelector("b")?.textContent); if (backs > 6) break; }
    P("E05", n === 3 && new Set(heads).size === 4 && backs === 3 && JSON.stringify(seen) === JSON.stringify([heads[2], heads[1], heads[0]]) && $("sel").querySelector("b").textContent === first, `followed ${n} links, Back ${backs} times, back at "${$("sel").querySelector("b").textContent}"`); }
  { const i = eng.findIndex((r) => r.case === "C05 unresolved"); await pick(i); await revert(); const hole = $$("#board [data-missing=hole]")[0]; await click(hole);
    const p = panel(), okc = $$("#sel .chip.ok").length, dec = /decided/.test($("sel").textContent);
    P("E06", /rejected/.test(p) && okc >= 1 && dec, `hole panel: reason shown, ${okc} candidates that fit, decisions section ${dec}`); }
  await pick(iSpec); await revert();

  // ---- F interrelation
  { const bad = [];
    for (const wh of Object.keys(wor)) { const i = eng.findIndex((r) => r.world === wh); await pick(i); await revert(); const w = wor[wh];
      const ty = Object.keys(w.types), pe = Object.values(w.functions).reduce((n, f) => n + f.parameters.filter(([, t]) => ty.includes(nameOf(inner(t)))).length, 0), re = Object.values(w.functions).filter((f) => ty.includes(nameOf(inner(f.result)))).length;
      let st = 0; for (const [n, t] of Object.entries(w.types)) { const kids = t.brand && t.of ? [t.of] : t.sum ? t.alternatives.filter((a) => !a.member) : t.product ? Object.values(t.fields) : []; st += kids.filter((k) => ty.includes(nameOf(inner(k))) && nameOf(inner(k)) !== n).length; }
      const got = { param: $$("#board [data-edge=param]").length, result: $$("#board [data-edge=result]").length, struct: $$("#board [data-edge=of],#board [data-edge=alt],#board [data-edge=field]").length };
      if (got.param !== pe || got.result !== re || got.struct !== st) bad.push(`${wh}: ${JSON.stringify(got)} vs ${pe}/${re}/${st}`); }
    P("F01", bad.length === 0, `edges (param/result/structure) equal the count from worlds.json in ${Object.keys(wor).length} worlds ${bad.join(" | ")}`); }
  { await pick(iSpec); const w = wor[eng[iSpec].world], bad = [];
    for (const [f, d] of Object.entries(w.functions)) { const pe = $$(`#board [data-role=port][data-fn="${f}"]`); const ports = pe.length; const names = pe.map((e) => e.textContent.trim()); if (ports !== d.parameters.length || !d.parameters.every(([p, t]) => names.includes(`${p} : ${nameOf(t)}`))) bad.push(f); }
    P("F02", bad.length === 0, `${Object.keys(w.functions).length} function nodes show a port per parameter with its name and declared type; wrong: ${bad.join(",") || "none"}`); }
  { await pick(iSpec); const w = wor[eng[iSpec].world];
    await click(byK("ty-Surface")); const m1 = $$("#board [data-role=member]").length, s1 = /sum|one of/.test($("sel").textContent);
    await click(byK("ty-Asked")); const wraps = $$("#board [data-role=wraps]").length, inh = /inherits/.test($("sel").textContent) && /Words/.test($("sel").textContent);
    await click(byK("ct-Many")); const kd = /\* -> \*/.test($("sel").textContent) && $("sel").textContent.includes(w.constructors.Many.describes);
    const kindShown = !!byK("kd-Surface")?.textContent.includes("*") && !!byK("sm-Surface");   // the kind and the structure mark are their own pieces now
    P("F03", m1 === w.types.Surface.alternatives.length && s1 && wraps === 1 && inh && kd && kindShown, `Surface opens ${m1}/${w.types.Surface.alternatives.length} members (sum), Asked wraps ${wraps} (inherits Words ${inh}), Many kind+describes ${kd}, kind on node ${kindShown}`); }
  { await pick(iSpec); await revert(); const lit = () => new Set($$("#board [data-lit]").map((e) => e.dataset.k));
    const [x, y] = ctr(byK("pl-1-subject")); fire("pointerover", x, y); await sleep(250); const l1 = lit();
    const [x2, y2] = ctr(byK("u-9")); fire("pointerover", x2, y2); await sleep(250); const l2 = lit(); fire("pointerover", 5, 5); await sleep(150);
    P("F04", ["op-1", "ty-Subject", "op-0", "u-18"].every((k) => l1.has(k) || ![...document.querySelectorAll(`#board [data-k^="u-"]`)].length) && l1.has("op-1") && l1.has("ty-Subject") && l1.has("op-0") && [...l1].some((k) => k.startsWith("u-")) && l2.has("op-0") && l2.has("pl-0-surface") && l2.has("ty-Surface") && l2.has("pl-1-subject") === false, `hover show.subject lights ${[...l1].join(",")}; hover “the mod” lights ${[...l2].join(",")}`); }
  { const iRep = eng.findIndex((r) => r.case === "C17 identical_operations"); await pick(iRep); await revert(); const ops = $$("#board [data-role=op]").map((e) => [e.dataset.op, e.textContent]);
    await pick(iSpec); await revert();
    P("F05", ops.length >= 2 && new Set(ops.map((o) => o[0])).size === ops.length && ops.every((o) => /redesign/.test(o[1])) && !!document.querySelector('#board [data-arc="op-0"]'), `two operations of one function stay two (${ops.map((o) => o[0])}); the reference arc ends at the same op id`); }
  { const bad = []; let n = 0;
    for (let i = 0; i < N; i++) { await pick(i); await revert(); for (const p of eng[i].phrases) for (const t of p.terms) { n++; const d = byK(`st-${t.id}`)?.dataset, j = t.judgments; const word = byK(`st-${t.id}`)?.textContent ?? "", want = !j.complete ? "open" : !j.ready ? "waits" : "ready" + (j.deferred ? " · later" : ""), shape = byK(`rs-${t.id}`)?.querySelector("rect.mark")?.getAttribute("stroke-dasharray");   // what is drawn, against what the engine says
      if (!d || word.trim() !== want || (!!j.deferred) !== (shape === "5 3") || d.provisional) bad.push(`${i}:${t.id} drew "${word}" want "${want}"`); } }
    P("F06", n > 50 && bad.length === 0, `${n} operations in ${N} readings: marks equal the engine's judgments, none provisional; wrong: ${bad.slice(0, 4).join(" ") || "none"}`); }
  { await pick(iSpec); await click(byK("fn-show")); const a = /show or open something/.test($("sel").textContent); await click(byK("ty-Subject")); const b = /one of/.test($("sel").textContent) && /taken by/.test($("sel").textContent);
    P("F07", a && b, `function asks shown ${a}; type definition shown ${b}`); }

  // ---- G
  { await pick(iSpec); const ds = eng[iSpec].decisions, n = ds.length; const next = () => $("dec").querySelector('[data-step="1"]');
    for (let k = 0; k < n + 2; k++) { next().click(); await sleep(100); }
    const stayed = new RegExp(`${n} / ${n}`).test($("dec").textContent);
    await pick(iSpec); const k1 = ds.findIndex((d) => d.operation != null && d.path); for (let k = 0; k <= k1; k++) { next().click(); await sleep(150); } await sleep(300);
    const want = `pl-${ds[k1].operation}-${ds[k1].path}`, lit = $$("#board [data-lit]").map((e) => e.dataset.k);
    const shownQ = ds[k1].asked && Object.values(ds[k1].asked).some((a) => $("dec").textContent.includes(a.instructions.slice(0, 30)));
    const iRule = eng.findIndex((r) => r.decisions.some((d) => d.by === "rule")); await pick(iRule); const di = eng[iRule].decisions.findIndex((d) => d.by === "rule");
    for (let k = 0; k <= di; k++) { $("dec").querySelector('[data-step="1"]').click(); await sleep(80); }
    const ruleShown = $("dec").textContent.includes(eng[iRule].decisions[di].rule) && /rule/.test($("dec").textContent);
    P("G01", stayed && lit.includes(want) && !!shownQ && ruleShown, `stepped ${n} decisions (ends at ${n}/${n}: ${stayed}); decision ${k1 + 1} lights ${want}: ${lit.includes(want)} and shows its question: ${!!shownQ}; rule decision text shown: ${ruleShown}`); }
  { await pick(iSpec); await revert(); const s0 = places(); await press(byK("u-37"), byK("pl-1-subject")); const s1 = places();
    $("undo").click(); await sleep(400); const s2 = places(); $("redo").click(); await sleep(400); const s3 = places();
    P("G02", s1 !== s0 && s2 === s0 && s3 === s1 && !$("undo").hidden, `drop, Undo, Redo restore the readings (${s2 === s0}, ${s3 === s1})`); }
  // G03 (kept corrections survive a reload) runs in two calls: AUDIT_G03_BEFORE(), then location.reload(), then AUDIT_G03_AFTER()
  await revert();

  // ---- H
  { const bad = [], longest = [];
    for (const i of [0, 7, 10, 20, 42]) { await pick(i); await revert(); $$("#board svg text").forEach((t) => { const w = t.textContent.trim().split(/\s+/).filter(Boolean).length; if (w > 6) bad.push(t.textContent); }); }
    const chrome = [...document.querySelectorAll("header button, header select")].map((e) => e.textContent.trim()).filter((t) => t.split(/\s+/).length > 6 && !/·/.test(t));
    P("H01", bad.length === 0 && chrome.length === 0, `board text longer than 6 words: ${bad.length}; no explanatory prose on the main view`); }
  { const sizes = []; await pick(iSpec); const sc = document.querySelector("#board svg").getBoundingClientRect().width / 1200;
    $$("#board svg text").forEach((t) => sizes.push(parseFloat(t.getAttribute("font-size")) * sc)); const mn = Math.min(...sizes);
    P("H02", mn >= 12, `smallest rendered text ${mn.toFixed(1)}px at scale ${sc.toFixed(2)} (viewport ${innerWidth}px); drawn sizes ≥ 12 units: ${Math.min(...$$("#board svg text").map((t) => parseFloat(t.getAttribute("font-size")))) >= 12}`); }
  { const bad = []; await pick(iSpec); await revert();
    const ty = (e) => { const m = /translate\(\s*([-\d.]+)[ ,]+([-\d.]+)\s*\)/.exec(e.getAttribute("transform") ?? ""); return m ? Number(m[2]) : null; };
    const board = [...$$("#board [data-role=op]"), ...$$("#board [data-role=function]"), ...$$("#board [data-role=type]")];
    for (const e of board) { const y = ty(e); if (y === null || Math.abs(y % 8) > 0.01) bad.push(`${e.dataset.k}@${y}`); }
    P("H03", board.length > 10 && bad.length === 0, `${board.length} rows (operations, functions, types) sit on the 8 px grid; off-grid: ${bad.slice(0, 5).join(" ") || "none"}`); }
  { const bad = [];
    for (let i = 0; i < N; i++) { await pick(i); await revert(); const ts = $$("#board svg text").map((t) => ({ t: t.textContent, r: t.getBoundingClientRect() })).filter((x) => x.r.width > 0);
      for (let a = 0; a < ts.length; a++) for (let b = a + 1; b < ts.length; b++) { const A = ts[a].r, Bx = ts[b].r; if (Math.min(A.right, Bx.right) - Math.max(A.left, Bx.left) > 0.5 && Math.min(A.bottom, Bx.bottom) - Math.max(A.top, Bx.top) > 0.5) bad.push(`${i}: "${ts[a].t}" × "${ts[b].t}"`); } }
    P("H04", bad.length === 0, `text overlaps in ${N} readings: ${bad.length} ${bad.slice(0, 4).join(" | ")}`); }
  { const bad = []; for (const i of [iSpec, eng.findIndex((r) => r.case === "C14 bounded"), eng.findIndex((r) => r.case === "C14 too_many_operations")]) { await pick(i); await revert(); if (document.documentElement.scrollWidth > innerWidth + 1) bad.push(i); }
    P("H05", bad.length === 0, `no horizontal scroll at ${innerWidth}px for the long readings (scrollWidth ${document.documentElement.scrollWidth})`); }

  // ---- I honesty
  { await pick(iSpec); await revert(); await press(byK("u-9"), byK("pl-1-subject"));
    const edited = byK("st-1").dataset.provisional, untouched = byK("st-2").dataset.provisional, untouched0 = byK("st-0").dataset.provisional;
    P("I01", edited === "1" && !untouched && !untouched0, `edited show: provisional=${edited}; untouched test: ${untouched}; untouched redesign: ${untouched0}`); await revert(); }
  { const bad = []; const M = Model;
    for (let i = 0; i < N; i++) { const wx = M.indexWorld(wor[eng[i].world]), st = M.toDraft(eng[i]), rc = M.recompute(wx, structuredClone(st), { ops: {}, order: [] });
      for (const id of st.order) { const a = st.ops[id].judg, b = rc.ops[id].judg; if (a.complete !== b.complete || a.pending !== b.pending || !!a.deferred !== b.deferred || a.ready !== b.ready) bad.push(`${i}:${id}`); } }
    const wx = M.indexWorld(wor[eng[iSpec].world]), st = M.toDraft(eng[iSpec]), u = eng[iSpec].constants[0], mv = M.movesFor(wx, st, st, { k: "const", c: u }, [{ id: "u-9", c: u }]).ok.find((m) => m.target === "pl-1-subject");
    const e = M.toDraft(eng[iEdit]); const same = JSON.stringify(mv.state.ops["1"].args) === JSON.stringify(e.ops["1"].args) && ["complete", "pending", "deferred", "ready"].every((k) => mv.state.ops["1"].judg[k] === e.ops["1"].judg[k]);
    P("I02", bad.length === 0 && same, `provisional recompute equals the engine's flags on every operation of ${N} readings (mismatches ${bad.length}); the specimen rebind equals the engine's own edit reading: ${same}`); }
  { await pick(iSpec); await revert(); await click(byK("fn-build")); const a = /provisional|≈/.test($("sel").textContent); await click(byK("ty-Surface")); const b = /gated/.test($("sel").textContent);
    P("I03", a && b, `apply-to is marked provisional (${a}); world edits marked as separate and gated (${b})`); }

  // ---- J every case: for every movable piece of many readings, every accepted target (previewed, then dropped) and refused target (held, then dropped)
  { const cases = ["C15 specimen", "C17 shared_result", "C10 record", "C10 several", "C10 through_result", "C10 many_of_records", "C05 unresolved", "C06 absent_many", "C07 reshape_open", "C09 chain"];
    let drags = 0, okN = 0, noN = 0, bad = []; const snapAll = () => places() + "|" + $$("#board [data-role=op]").map((e) => e.dataset.op).join(",");
    for (const cs of cases) {
      const i = eng.findIndex((r) => r.case === cs); if (i < 0) { bad.push(`${cs}: missing`); continue; }
      await pick(i); await revert();
      const pieces = $$("#board [data-role=value],#board [data-role=op],#board [data-role=function],#board [data-role=label],#board [data-role=place],#board [data-role=word]").map((e) => e.dataset.k).filter((k, x, a) => a.indexOf(k) === x).slice(0, 8);
      for (const k of pieces) {
        const piece = () => byK(k); if (!piece()) continue;
        const h0 = await press(piece(), farPoint(), { hold: true }); const acc = $$("#board [data-accepts]").map((e) => e.dataset.accepts), no = $$("#board [data-refused]").map((e) => [e.dataset.refused, e.dataset.why]); await release(h0);
        for (const t of acc.slice(0, 2)) {
          await revert(); if (!piece() || !byK(t)) continue; const base = snapAll();
          const hh = await press(piece(), byK(t), { hold: true }); const prev = snapAll(); await release(hh); const fin = snapAll(); drags++; okN++;
          if (prev !== fin) bad.push(`${cs}: ${k}→${t} preview≠drop`); if (fin === base) bad.push(`${cs}: ${k}→${t} accepted but nothing changed`);
        }
        for (const [t, why] of no.slice(0, 1)) {
          await revert(); if (!piece() || !byK(t)) continue; const base = snapAll();
          const hh = await press(piece(), byK(t), { hold: true }); const prev = snapAll(); await release(hh); const fin = snapAll(); drags++; noN++;
          if (prev !== base || fin !== base || !why || why.length < 6) bad.push(`${cs}: ${k}→${t} refused but ${prev !== base ? "previewed" : fin !== base ? "committed" : "no reason"}`);
        }
        await revert();
      }
    }
    P("J01", drags > 100 && bad.length === 0, `${drags} real drags (${okN} to accepted targets, ${noN} to refused) over ${cases.length} readings: the preview equals the drop, refusals change nothing and say why; failures: ${bad.slice(0, 6).join(" | ") || "none"} (${bad.length})`); }
  // ---- L long markdown (v15 and later) and M the visual language, constructors, navigable marks, replay (criteria L01..L04, M01..M06 in ACCEPTANCE-V11.md)
  const VER = B.V ?? 15;
  if (VER >= 15) { try {
    const iSt = eng.length; await pick(iSt); await revert(); const r = B.READINGS[iSt], texts = $$("#board svg text").map((t) => ({ t: t.textContent, r: t.getBoundingClientRect() })).filter((x) => x.r.width > 0);
    const opsDrawn = $$("#board [data-role=op]").length, opsWanted = r.phrases.reduce((n, p) => n + p.terms.length, 0), tall = document.querySelector("#board svg").getBoundingClientRect().height;
    const bad = []; for (let a = 0; a < texts.length; a++) for (let b2 = a + 1; b2 < texts.length; b2++) { const A = texts[a].r, Bx = texts[b2].r; if (Math.min(A.right, Bx.right) - Math.max(A.left, Bx.left) > 0.5 && Math.min(A.bottom, Bx.bottom) - Math.max(A.top, Bx.top) > 0.5) bad.push(`${texts[a].t}×${texts[b2].t}`); }
    P("L01", opsDrawn === opsWanted && opsWanted >= 25 && r.text.length > 800 && bad.length === 0 && tall > innerHeight * 2, `long markdown (${r.text.length} chars, ${opsWanted} operations): ${opsDrawn} drawn, ${bad.length} text overlaps, board ${Math.round(tall)}px tall (viewport ${innerHeight}px)`);
    const heads = $$("#board [data-role=word]").filter((e) => /^#+$|^-$/.test(e.dataset.text)), lines = new Set(heads.map((e) => Math.round(e.getBoundingClientRect().top))), starts = heads.filter((e) => Math.abs(e.getBoundingClientRect().left - document.querySelector("#board svg").getBoundingClientRect().left) < 2).length;
    P("L02", heads.length >= 10 && lines.size >= 10 && starts === heads.length, `${heads.length} markdown markers (#, ##, -) are words of their own, each on its own line (${lines.size} lines) at the left edge (${starts})`);
    scrollTo(0, 2000); await sleep(1200); const world = byK("ty-Surface").getBoundingClientRect(), fnShow = byK("fn-show").getBoundingClientRect();
    P("L03", world.top >= 0 && world.top < innerHeight && fnShow.top >= 0 && fnShow.top < innerHeight && scrollY > 1500, `scrolled to ${Math.round(scrollY)}px: the world is still in view (type at ${Math.round(world.top)}px, function at ${Math.round(fnShow.top)}px)`);
    const mods = $$("#board [data-role=value]").filter((e) => e.dataset.text === "the mod" && e.getBoundingClientRect().top > 100 && e.getBoundingClientRect().bottom < innerHeight - 100), unit = mods[0];
    let dragOK = false, note = "no visible “the mod”";
    if (unit) { const targets = $$("#board [data-role=place]").filter((e) => e.dataset.declared === "Subject" && e.getBoundingClientRect().top > 0 && e.getBoundingClientRect().bottom < innerHeight), t = targets[0]; if (t) { const before = t.textContent; await press(unit, t); const after = byK(t.dataset.k).textContent; dragOK = after !== before && /the mod/.test(after); note = `“the mod” dropped on ${t.dataset.place}: "${before}" → "${after}"`; } else note = "no visible Subject place"; }
    P("L04", dragOK, `a real drag deep in the long message: ${note}`); scrollTo(0, 0); await sleep(500); await revert();
  } catch (e) { P("L01", false, "the L block crashed: " + e.message); }
  try {
    await pick(iSpec); await revert();
    // M01 constructors are applied to types by dragging; kinds decide what fits
    const hp = await press(byK("ct-Many"), byK("ty-Surface"), { hold: true }); const probe = document.querySelector("[data-probe]")?.dataset.probe, refusedC = $$("[data-refused]").filter((e) => /^ct-/.test(e.dataset.refused)).map((e) => e.dataset.why), accT = $$("[data-accepts]").filter((e) => /^ty-/.test(e.dataset.accepts)).length;
    await release(hp); await sleep(300); const card = $("sel").textContent.replace(/\s+/g, " ");
    P("M01", probe === "Many[Surface]" && refusedC.length === 2 && refusedC.every((w) => /kind \*/.test(w)) && accT === Object.keys(wor[eng[iSpec].world].types).length && /Many\[Surface\]/.test(card) && /type expression/.test(card) && B.RD.undo.length === 0, `Many held over Surface shows ${probe}; the other constructors refused with the kind rule (${refusedC.length}); ${accT} types accept it; releasing opens the expression card and changes nothing (history ${B.RD.undo.length})`);
    const iCmp = eng.findIndex((r2) => r2.case === "C16 compare_conjunction"); await pick(iCmp); await revert(); const hp2 = await press(byK("ct-Many"), byK("ty-Surface"), { hold: true }); const takers = $$("#board [data-role=function][data-takes]").map((e) => e.dataset.name); await release(hp2); await sleep(300);
    const wc = wor[eng[iCmp].world], expectT = Object.keys(wc.functions).filter((f) => wc.functions[f].parameters.some(([, t]) => nameOf(t) === "Many[Surface]")).sort(), links = [...$("sel").querySelectorAll("[data-go^=pt-]")].map((a) => a.dataset.go.slice(3)).sort();
    P("M02", JSON.stringify(takers.sort()) === JSON.stringify(expectT) && expectT.length > 0 && JSON.stringify(links) === JSON.stringify(expectT.map((f) => `${f}-${wc.functions[f].parameters.find(([, t]) => nameOf(t) === "Many[Surface]")[0]}`).sort()), `Many[Surface] in a world with compare: functions lit [${takers}] = worlds.json [${expectT}]; the card lists their parameters [${links}]`);
    await pick(iSpec); await revert();
    // M03 shape = structure, colour = what it is made of; functions look like nothing else
    const gl = (n) => document.querySelector(`#board [data-role=type][data-name="${n}"] path[data-type]`), d = (n) => gl(n)?.getAttribute("d"), f = (n) => gl(n)?.getAttribute("fill");
    const iCell = eng.findIndex((r2) => r2.case === "C10 record"); await pick(iCell); await revert();
    const sameFam = ["Words", "Asked", "Written", "Surface"].map(f), diffShape = new Set(["Words", "Surface", "Cell", "Path"].map(d)).size, famPath = f("Path"), famInt = f("int");
    const arrowD = document.querySelector("#board [data-role=function] path.mark")?.getAttribute("d"), typeDs = $$("#board [data-role=type] path[data-type]").map((p) => p.getAttribute("d"));
    P("M03", new Set(sameFam).size === 1 && sameFam[0] !== famPath && famPath !== famInt && d("Words") !== d("Surface") && d("Surface") !== d("Cell") && d("Words") === d("Asked") && diffShape === 3 && !typeDs.includes(arrowD), `str-made types share one colour (${[...new Set(sameFam)]}), Path ${famPath} and int ${famInt} differ; shapes: brand ≠ sum ≠ product (Words, Surface, Cell), base Path = ${d("Path") === d("Words") ? "same as brand (WRONG)" : "its own"}; functions are arrows that no type uses`);
    // M04 the marks are things: the port, the kind, the structure mark each open a card with data
    await pick(iCell); await revert(); await click(byK("pt-open_cell-cell")); const c1 = $("sel").textContent.replace(/\s+/g, " ");
    await click(byK("kd-Surface")); const c2 = $("sel").textContent.replace(/\s+/g, " "); await click(byK("sm-Subject")); const c3 = $("sel").textContent.replace(/\s+/g, " "); const wsub = wor[eng[iCell].world];
    P("M04", /open_cell\.cell/.test(c1) && /notebook/.test(c1) && /number/.test(c1) && /same kind/.test(c2) && /Many : \* -> \*/.test(c2) && /one of/.test(c3) && wsub.types.Subject.alternatives.every((a) => c3.includes(a.sum ?? a.words ?? nameOf(a))), `cell : Cell opens the record (fields notebook, number); the kind mark opens kinds and constructors; the sum mark lists the alternatives`);
    // M05 the outline appears only where something is missing
    await pick(iSpec); await revert(); const filled = byK("pl-0-surface").querySelector("rect.mark"), iHole = eng.findIndex((r2) => r2.case === "C05 unresolved"); await pick(iHole); await revert(); const hole = $$("#board [data-missing=hole]")[0].querySelector("rect.mark");
    P("M05", filled.getAttribute("stroke") === "none" && !filled.getAttribute("stroke-dasharray") && !!hole.getAttribute("stroke-dasharray") && hole.getAttribute("stroke") !== "none", `a filled place has no outline (${filled.getAttribute("stroke")}); a hole is outlined and dashed (${hole.getAttribute("stroke-dasharray")})`);
    // M06 replay: the recorded decisions in order; what is not decided yet is ghosted
    await pick(iSpec); await revert(); const nOps = $$("#board [data-role=op]").length; const rp = $("dec").querySelector("[data-play]"); rp.click(); await sleep(1500);
    const g1 = $$("#board [data-role=op][data-ghost]").length; await sleep(8200); const g2 = $$("#board [data-role=op][data-ghost]").length, n = $("dec").textContent; const stillPlaying = /Stop/.test(n);
    if (stillPlaying) { rp.click?.(); $("dec").querySelector("[data-play]")?.click(); }
    await sleep(500); const show = $("dec").querySelector('[data-step="0"]'); if (show) { show.click(); await sleep(300); }
    P("M06", nOps === 3 && g1 >= 2 && g2 < g1 && $$("#board [data-ghost]").length === 0, `replay: after the first decision ${g1} of ${nOps} operations are still ghosts; later ${g2}; “Show all” leaves ${$$("#board [data-ghost]").length} ghosts`);
  } catch (e) { P("M01", false, "the M block crashed: " + e.message); }
  } else out.push("N/A L01-L04, M01-M06 are claimed from v15 only");
  // ---- K the ten questions about one word, and the clicks it takes to answer each (criteria K01..K10 in ACCEPTANCE-V11.md)
  try { await pick(iSpec); await revert(); let clicks = 0; const w = wor[eng[iSpec].world];
    clicks++; await click(byK("u-9")); const card = $("sel"), txt = card.textContent.replace(/\s+/g, " "), r0 = eng[iSpec];
    const occ = (t, n) => nameOf(t) === n || (t.constructor === "Many" || t.constructor === "Maybe" || t.constructor === "Later" ? occ(t.of, n) : t.sum ? t.alternatives.some((a) => !a.member && occ(a, n)) : false);
    const dec = r0.decisions.find((d) => d.function === "redesign" && d.path === "surface"), pTop = Math.round(dec.answers.which.probabilities["0"] * 100), pNone = Math.round(dec.answers.which.probabilities.none * 100);
    const row = (label) => [...card.querySelectorAll(".row")].find((e) => e.querySelector(".k")?.textContent === label);
    const expectFns = Object.keys(w.functions).filter((f) => w.functions[f].parameters.some(([, t]) => occ(t, "Surface"))).sort(), gotFns = [...(row("taken by")?.querySelectorAll("[data-go]") ?? [])].map((a) => a.dataset.go.slice(3)).sort();
    const spans = [...card.querySelectorAll("details")].find((d) => d.querySelector("summary")?.textContent === "span");
    const K = { 1: !!card.querySelector('[data-go="ty-Surface"]') && /Surface\s*\*/.test(txt), 2: !!card.querySelector('[data-go="pl-0-surface"]') && !!card.querySelector('[data-go="op-0"]'), 3: /ready · later/.test(txt) && r0.phrases[0].terms[0].judgments.ready && r0.phrases[0].terms[0].judgments.deferred,
      4: txt.includes(`${pTop} 0`) && txt.includes(`${pNone} none`) && /offered 1/.test(txt), 5: $$("#board [data-role=member]").length === w.types.Surface.alternatives.length, 6: JSON.stringify(gotFns) === JSON.stringify(expectFns) && gotFns.length > 0,
      7: $$("#sel .chip.ok").length >= 3 && /Surface is accepted|Surface is accepted by|accepted by/.test(txt), 8: /only Surface has/.test(txt), 9: !!spans && [...spans.querySelectorAll(".chip.no")].length >= 3 && /is not a member of/.test(spans.textContent) };
    // 10: a word that is not yet a value ("too.") becomes one by adding it to a type: 2 clicks; then it binds by a real drag
    const tooEl = $$("#board [data-role=word]").find((e) => e.dataset.text === "too."); let k10 = false, k10note = "no word";
    if (tooEl) { let c2 = 0; c2++; await click(tooEl); const btn = [...$("sel").querySelectorAll("button[data-act]")].find((b) => /member of Code/.test(b.parentElement.textContent)); if (btn) { c2++; btn.click(); await sleep(600);
        const mem = $$("#board [data-role=member]").map((e) => e.textContent), isVal = $$("#board [data-role=value]").some((e) => e.dataset.text === "too.");
        await press(byK(`u-${tooEl.dataset.k.slice(2)}`), byK("pl-2-subject")); const bound = placeText("pl-2-subject");
        k10 = c2 <= 2 && mem.some((t) => /too\./.test(t) && /≈/.test(t)) && isVal && /too\./.test(bound); k10note = `clicks ${c2}; member shown ≈ ${mem.some((t) => /≈/.test(t))}; now a value ${isVal}; bound by drag: "${bound}"`; } else k10note = "no add button"; }
    K[10] = k10;
    for (let q = 1; q <= 10; q++) P(`K${String(q).padStart(2, "0")}`, !!K[q] && (q === 10 || clicks === 1), `question ${q}: answered by ${q === 10 ? "2" : clicks} click(s), ${K[q] ? "answer shown" : "answer MISSING"}${q === 10 ? " — " + k10note : ""}${q === 8 ? " (data has no word in two types: the retag action itself cannot be exercised on engine data)" : ""}${q === 9 ? " (engine data has no member that makes a longer span valid: only refusals are exercised)" : ""}`, q === 8 || q === 9);
  } catch (e) { P("K01", false, "the K block crashed: " + e.message); }
  await revert();
  P("J02", (window.__errs ?? []).length === 0, `script errors during the whole run: ${(window.__errs ?? []).length} ${(window.__errs ?? []).slice(0, 3).join(" | ")}`);
  await revert();
  const line = `SCORE ${scoreN}/${scoreD} (viewport ${innerWidth}px, ${N} readings, ${Object.keys(wor).length} worlds)`;
  const text = out.join("\n") + "\n" + line; window.AUDIT_OUT = text; return text;
};
// G03: a correction made on the page is listed (operation, path, value, status) and is still there after a reload
window.AUDIT_G03_BEFORE = async function () {
  const eng = BOARD.READINGS, iSpec = eng.findIndex((r) => r.case === "C15 specimen");
  await pick(iSpec); await revert(); await press(byK("u-37"), byK("pl-1-subject")); await sleep(300);
  const shown = $("dec").textContent; sessionStorage.setItem("audit-g03", JSON.stringify({ shown }));
  return `before reload: corrections list reads "${shown.replace(/\s+/g, " ").slice(-90)}" (${/1\.subject/.test(shown) && /the search/.test(shown) && /provisional/.test(shown) ? "listed" : "NOT listed"})`;
};
window.AUDIT_G03_AFTER = async function () {
  await sleep(800); const g = JSON.parse(sessionStorage.getItem("audit-g03") ?? "null"), now = $("dec").textContent, place = document.getElementById("pl-1-subject")?.textContent;
  const ok = !!g && /1\.subject/.test(now) && /the search/.test(now) && /provisional/.test(now) && place === "the search";
  return `${ok ? "PASS" : "FAIL"} G03 after reload the page shows show.subject = "${place}" and the corrections list "${now.replace(/\s+/g, " ").slice(-80)}"`;
};
})();
