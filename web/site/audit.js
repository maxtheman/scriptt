// audit.js: acceptance probes for the board (criteria: web/notes/ACCEPTANCE-V11.md, written before the build).
// Open index.html?audit and run `await AUDIT()`. Every move is a PointerEvent dispatched at element coordinates, the target found with
// document.elementFromPoint at the pointer position, so Dragology's own press, move, drop targets and release run. A probe reads the
// DOM or the engine's files; it never sets state, never remounts, never edits storage. (`?audit` only names the draft storage apart from the real one.)
(() => {
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const $ = (id) => document.getElementById(id), $$ = (s, r = document) => [...r.querySelectorAll(s)];
const ctr = (el) => { const r = el.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; };
function fire(type, x, y) { const t = document.elementFromPoint(x, y) ?? document.body; t.dispatchEvent(new PointerEvent(type, { bubbles: true, cancelable: true, composed: true, clientX: x, clientY: y, pointerId: 1, pointerType: "mouse", isPrimary: true, button: 0, buttons: type === "pointerup" ? 0 : 1 })); return t; }
async function press(el, to, { hold = false, steps = 14, settle = 140 } = {}) {   // pointerdown on the element's centre, moves to `to` (element or [x,y]), then releases unless hold
  const [x0, y0] = ctr(el), [x1, y1] = Array.isArray(to) ? to : ctr(to);
  fire("pointerdown", x0, y0);
  for (let i = 1; i <= steps; i++) { fire("pointermove", x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps); await sleep(16); }
  await sleep(settle);
  if (hold) return { x: x1, y: y1 };
  fire("pointerup", x1, y1); await sleep(750); return { x: x1, y: y1 };
}
const release = async (p) => { fire("pointerup", p.x, p.y); await sleep(750); };
const click = async (el) => { const [x, y] = ctr(el); fire("pointerdown", x, y); await sleep(20); fire("pointerup", x, y); await sleep(250); };
const byK = (k) => document.querySelector(`#board [data-k="${k}"]`);
const places = () => $$("#board [data-role=place]").map((e) => `${e.dataset.place}=${e.querySelector("text")?.textContent ?? ""}|${e.dataset.kind}`).join(";");
const placeText = (id) => { const e = byK(id); return e ? [...e.querySelectorAll("text")].map((t) => t.textContent).join(" ") : null; };
const pick = async (i) => { window.AUDIT_AT = "pick " + i; $("pick").value = String(i); $("pick").dispatchEvent(new Event("change")); await sleep(500); };
const revert = async () => { const b = $("reset"); if (!b.disabled) { b.click(); await sleep(500); } };
const parseEngine = (t) => Model.parseEngine(t);
const farPoint = () => { const r = document.querySelector("#board svg").getBoundingClientRect(); return [r.left + 60, r.bottom - 14]; };
const out = []; let scoreN = 0, scoreD = 0;
const P = (id, ok, note, partial = false) => { scoreD++; const v = partial ? (ok ? 0.5 : 0) : (ok ? 1 : 0); scoreN += v; out.push(`${v === 1 ? "PASS" : v === 0.5 ? "HALF" : "FAIL"} ${id} ${note}`); };

window.AUDIT = async function () {
  out.length = 0; scoreN = 0; scoreD = 0; window.AUDIT_LOG = out; window.AUDIT_AT = "start";
  try { Object.keys(localStorage).filter((k) => k.startsWith("scriptt-audit:")).forEach((k) => localStorage.removeItem(k)); } catch {}   // only the audit's own draft namespace
  const eng = await (await fetch("engine/readings.json")).text().then(parseEngine), wor = await (await fetch("engine/worlds.json")).text().then(parseEngine);
  const B = window.BOARD, N = eng.length;
  const iSpec = eng.findIndex((r) => r.case === "C15 specimen"), iEdit = eng.findIndex((r) => /rebound/.test(r.case));
  await pick(iSpec); await revert();
  const world = (r) => wor[r.world], inner = (t) => (t.constructor === "Many" || t.constructor === "Maybe" || t.constructor === "Later" ? inner(t.of) : t);
  const nameOf = Model.nameOf;

  // ---- A data
  const res = performance.getEntriesByType("resource").map((e) => e.name);
  P("A01", res.some((n) => /engine\/readings\.json/.test(n)) && res.some((n) => /engine\/worlds\.json/.test(n)) && $$("#pick option").length === N && N >= 38 && $("pick").options[iSpec].text.includes("Redesign the mod. Then show it. Test the search too.") && iSpec === 0, `fetched both files; ${$$("#pick option").length} readings (file has ${N}); specimen first`);
  { // A02: every drawn token of every reading is in the data or the fixed UI list
    const UI = ["ready", "waits", "open", "none", "wraps"];
    const allowed = new Set(UI);
    const addStr = (v) => { if (typeof v === "string") v.split(/[^\p{L}\d_]+/u).forEach((w) => w && allowed.add(w)); else if (v && typeof v === "object") Object.entries(v).forEach(([k, x]) => { addStr(k); addStr(x); }); };
    addStr(eng); addStr(wor);
    const unknown = new Set();
    for (let i = 0; i < N; i++) { await pick(i); await revert(); $$("#board svg text").forEach((t) => (t.textContent.match(/[\p{L}\d_]+/gu) ?? []).forEach((w) => { if (!allowed.has(w) && !/^\d+$/.test(w)) unknown.add(w); })); }
    P("A02", unknown.size === 0, `fixed UI words: ${UI.join(", ")}; tokens not in the data: ${[...unknown].join(", ") || "none"}`);
  }
  { // A03
    const bad = [];
    for (let i = 0; i < N; i++) {
      await pick(i); await revert(); const r = eng[i];
      for (const p of r.phrases) for (const t of p.terms) if (!document.querySelector(`#board [data-op="${t.id}"]`)) bad.push(`${i}: op ${t.id}`);
      for (const c of r.constants) { const u = document.getElementById(`u-${c.at[0]}`); if (!u || u.dataset.text !== r.text.slice(c.at[0], c.at[1])) bad.push(`${i}: ${c.constant}`); }
      r.phrases.forEach((p, pi) => { if (p.unresolved && !document.querySelector(`#board [data-k="un-${pi}"]`)) bad.push(`${i}: unresolved phrase ${pi}`); });
    }
    P("A03", bad.length === 0, `${N} readings; ${bad.length} missing ${bad.slice(0, 4).join(" | ")}`);
  }
  { // A04: four marks for four kinds of missing
    const found = {}, find = async (pred, key, sel) => { for (let i = 0; i < N && !found[key]; i++) if (pred(eng[i])) { await pick(i); await revert(); const e = document.querySelector(sel); if (e) found[key] = { i, e, dash: e.querySelector("rect.mark")?.getAttribute("stroke-dasharray") ?? null, txt: e.textContent }; } };
    const anyV = (r, f) => r.phrases.some((p) => p.terms.some((t) => JSON.stringify(t.arguments).includes(f)));
    await find((r) => anyV(r, '"hole"'), "hole", '#board [data-missing=hole]');
    await find((r) => anyV(r, '"empty"'), "empty", '#board [data-missing=empty]');
    await find((r) => anyV(r, '"several":[]'), "list", '#board [data-missing=list]');
    await find((r) => r.phrases.some((p) => p.unresolved), "unresolved", '#board [data-missing=unresolved]');
    const dashes = Object.values(found).map((f) => f.dash), reasons = found.hole && /rejected|no candidate|bounded|cleared|open/.test(found.hole.txt) && found.unresolved && /rejected|bounded|no candidate/.test(found.unresolved.txt);
    P("A04", Object.keys(found).length === 4 && new Set(dashes).size === 4 && !!reasons, `found ${Object.keys(found).join(",")} dashes ${JSON.stringify(dashes)} hole text "${found.hole?.txt}" unresolved "${found.unresolved?.txt}"`);
  }
  await pick(iSpec); await revert();

  // ---- B every piece draggable
  { const kinds = {}; const fails = [];
    for (const i of [0, 7, 10, 20]) {
      await pick(i); await revert();
      const els = $$("#board [data-grab]");
      for (const e of els) {
        const [x, y] = ctr(e), role = e.dataset.role; kinds[role] = (kinds[role] ?? 0) + 1;
        if (e.getBoundingClientRect().width === 0) continue;
        fire("pointerdown", x, y); for (let k = 1; k <= 4; k++) { fire("pointermove", x + 6 * k, y + 4 * k); await sleep(16); } await sleep(60);
        const started = !!B.HELD && B.HELD.id === e.dataset.k;
        fire("pointerup", x + 24, y + 16); await sleep(400);
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
    const w = wor[eng[iSpec].world], expect = Object.keys(w.functions).filter((f) => w.functions[f].parameters.some(([, t]) => Model.takes(Model.indexWorld(w), t, "Surface")));
    await release(h4);
    const ys1 = Object.fromEntries($$("#board [data-role=function]").map((e) => [e.dataset.name, e.getBoundingClientRect().top]));
    P("D04", takes.length > 0 && rest.length > 0 && maxT < minR && Object.keys(ys0).every((k) => Math.abs(ys0[k] - ys1[k]) < 1), `holding “the mod”: ${takes.length} functions that take it come first (${takes.map((e) => e.dataset.name)}); order restored on release; model says ${expect.length} take Surface`); }
  { await revert(); const w = wor[eng[iSpec].world];
    const h5 = await press(byK("ty-Surface"), [farPoint()[0], farPoint()[1]], { hold: true });
    const litFn = $$("#board [data-role=function][data-lit]").map((e) => e.dataset.name).sort(), litP = $$("#board [data-role=place][data-lit]").map((e) => e.dataset.place);
    const mention = Object.keys(w.functions).filter((f) => w.functions[f].parameters.some(([, t]) => nameOf(inner(t)) === "Surface") || nameOf(inner(w.functions[f].result)) === "Surface").sort();
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
    P("E01", /Surface/.test(p) && /redesign|0\.surface/.test(p) && okc === 3 && nos.some((x) => /0\.surface/.test(x) && /Surface/.test(x)) && /Surface|kind|sum/.test(p), `“the mod”: ${okc} accepted places, kind/definition shown; “the search” refused: ${nos[0]}`); }
  { await revert(); await click(byK("u-9")); const btn = $$("#sel button[data-act]").find((b) => b.parentElement.querySelector(".chip")?.textContent.includes("1.subject")) ?? $$("#sel .row").find((r) => r.textContent.includes("1.subject"))?.querySelector("button");
    const sPre = places(); btn.click(); await sleep(500); const viaButton = places(); await revert();
    await press(byK("u-9"), byK("pl-1-subject")); const viaDrag = places();
    P("E02", viaButton !== sPre && viaButton === viaDrag, `the panel's Apply and the drag give the same reading: ${viaButton === viaDrag}`); await revert(); }
  { await revert(); await click(byK("pl-1-subject")); const p = panel(), link = $("sel").querySelector('[data-go="op-0"]');
    const rebind = $$("#sel .row").find((r) => /“the mod”/.test(r.textContent) && r.querySelector("button")), j = eng[iSpec].phrases[1].terms[0].judgments;
    const rb = rebind?.querySelector("button"); if (rb) { rb.click(); await sleep(500); }
    const flags = byK("st-1").dataset, eng2 = eng[iEdit].phrases.flatMap((x) => x.terms).find((t) => t.function === "show").judgments;
    P("E03", !!link && /same operation/.test(p) && !!rb && flags.ready === String(eng2.ready) && flags.pending === String(eng2.pending), `reference panel links op 0 (${!!link}), offers rebind to “the mod” (${!!rb}); after rebinding flags ready/pending ${flags.ready}/${flags.pending} = engine edit ${eng2.ready}/${eng2.pending}`); await revert(); }
  { await click(byK("op-1")); const p = panel(), w = wor[eng[iSpec].world];
    P("E04", p.includes(w.functions.show.asks) && /subject/.test(p) && /Subject/.test(p) && /pending|available/.test(p) && /engine/.test(p), `operation panel shows asks "${w.functions.show.asks}", signature, flags, source of flags`); }
  { await click(byK("u-9")); const first = $("sel").querySelector("b").textContent; let n = 0;
    for (const sel of ['[data-go="ty-Surface"]', '[data-go^="fn-"]', '[data-go^="ty-"]']) { const a = $("sel").querySelector(sel); if (a) { await click(a); n++; } }
    let backs = 0; while ($("sel").querySelector("[data-back]")) { await click($("sel").querySelector("[data-back]")); backs++; if (backs > 6) break; }
    P("E05", n === 3 && backs === 3 && $("sel").querySelector("b").textContent === first, `followed ${n} links, Back ${backs} times, back at "${$("sel").querySelector("b").textContent}"`); }
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
    for (const [f, d] of Object.entries(w.functions)) { const g = byK(`fn-${f}`); const ports = $$("circle", g).length; const names = [...g.querySelectorAll("text")].map((t) => t.textContent); if (ports !== d.parameters.length || !d.parameters.every(([p, t]) => names.includes(`${p} : ${nameOf(t)}`))) bad.push(f); }
    P("F02", bad.length === 0, `${Object.keys(w.functions).length} function nodes show a port per parameter with its name and declared type; wrong: ${bad.join(",") || "none"}`); }
  { await pick(iSpec); const w = wor[eng[iSpec].world];
    await click(byK("ty-Surface")); const m1 = $$("#board [data-role=member]").length, s1 = /sum|one of/.test($("sel").textContent);
    await click(byK("ty-Asked")); const wraps = $$("#board [data-role=wraps]").length, inh = /inherits/.test($("sel").textContent) && /Words/.test($("sel").textContent);
    await click(byK("ct-Many")); const kd = /\* -> \*/.test($("sel").textContent) && $("sel").textContent.includes(w.constructors.Many.describes);
    const kindShown = !!byK("ty-Surface").textContent.includes("*");
    P("F03", m1 === w.types.Surface.alternatives.length && s1 && wraps === 1 && inh && kd && kindShown, `Surface opens ${m1}/${w.types.Surface.alternatives.length} members (sum), Asked wraps ${wraps} (inherits Words ${inh}), Many kind+describes ${kd}, kind on node ${kindShown}`); }
  { await pick(iSpec); await revert(); const lit = () => new Set($$("#board [data-lit]").map((e) => e.dataset.k));
    const [x, y] = ctr(byK("pl-1-subject")); fire("pointerover", x, y); await sleep(250); const l1 = lit();
    const [x2, y2] = ctr(byK("u-9")); fire("pointerover", x2, y2); await sleep(250); const l2 = lit(); fire("pointerover", 5, 5); await sleep(150);
    P("F04", ["op-1", "ty-Subject", "op-0", "u-18"].every((k) => l1.has(k) || ![...document.querySelectorAll(`#board [data-k^="u-"]`)].length) && l1.has("op-1") && l1.has("ty-Subject") && l1.has("op-0") && [...l1].some((k) => k.startsWith("u-")) && l2.has("op-0") && l2.has("pl-0-surface") && l2.has("ty-Surface") && l2.has("pl-1-subject") === false, `hover show.subject lights ${[...l1].join(",")}; hover “the mod” lights ${[...l2].join(",")}`); }
  { const iRep = eng.findIndex((r) => r.case === "C17 identical_operations"); await pick(iRep); await revert(); const ops = $$("#board [data-role=op]").map((e) => [e.dataset.op, e.textContent]);
    await pick(iSpec); await revert();
    P("F05", ops.length >= 2 && new Set(ops.map((o) => o[0])).size === ops.length && ops.every((o) => /redesign/.test(o[1])) && !!document.querySelector('#board [data-arc="op-0"]'), `two operations of one function stay two (${ops.map((o) => o[0])}); the reference arc ends at the same op id`); }
  { const bad = []; let n = 0;
    for (let i = 0; i < N; i++) { await pick(i); await revert(); for (const p of eng[i].phrases) for (const t of p.terms) { n++; const d = byK(`st-${t.id}`)?.dataset, j = t.judgments; if (!d || d.complete !== String(j.complete) || d.pending !== String(j.pending) || d.deferred !== String(!!j.deferred) || d.ready !== String(j.ready) || d.provisional) bad.push(`${i}:${t.id}`); } }
    P("F06", n > 50 && bad.length === 0, `${n} operations in ${N} readings: marks equal the engine's judgments, none provisional; wrong: ${bad.slice(0, 4).join(" ") || "none"}`); }
  { await pick(iSpec); await click(byK("fn-show")); const a = /show or open something/.test($("sel").textContent); await click(byK("ty-Subject")); const b = /one of/.test($("sel").textContent) && /taken by/.test($("sel").textContent);
    P("F07", a && b, `function asks shown ${a}; type definition shown ${b}`); }

  // ---- G
  { await pick(iSpec); const n = eng[iSpec].decisions.length; let c = 0; const next = () => $("dec").querySelector('[data-step="1"]');
    for (let k = 0; k < n + 2; k++) { next().click(); await sleep(120); c++; }
    const chipTxt = $("dec").querySelector(".chip:nth-child(2)")?.textContent ?? $$("#dec .chip")[0]?.textContent, stayed = /9 \/ 9/.test($("dec").textContent);
    // a decision that names a place lights it
    $("dec").querySelector('[data-step="-1"]').click(); await sleep(100); for (let k = 0; k < n; k++) { $("dec").querySelector('[data-step="-1"]').click(); await sleep(80); }
    next().click(); await sleep(150); next().click(); await sleep(300);
    const lit = $$("#board [data-lit]").map((e) => e.dataset.k);
    const iRule = eng.findIndex((r) => r.decisions.some((d) => d.by === "rule")); await pick(iRule); const di = eng[iRule].decisions.findIndex((d) => d.by === "rule");
    for (let k = 0; k <= di; k++) { $("dec").querySelector('[data-step="1"]').click(); await sleep(80); }
    const ruleShown = $("dec").textContent.includes(eng[iRule].decisions[di].rule) && /rule/.test($("dec").textContent);
    P("G01", stayed && lit.some((k) => k.startsWith("pl-") || k.startsWith("op-")) && ruleShown, `stepped ${n} decisions (counter ends at ${n}/${n}: ${stayed}); a step lights ${lit.slice(0, 4)}; rule decision text shown: ${ruleShown}`); }
  { await pick(iSpec); await revert(); const s0 = places(); await press(byK("u-37"), byK("pl-1-subject")); const s1 = places();
    $("undo").click(); await sleep(400); const s2 = places(); $("redo").click(); await sleep(400); const s3 = places();
    P("G02", s1 !== s0 && s2 === s0 && s3 === s1 && !$("undo").hidden, `drop, Undo, Redo restore the readings (${s2 === s0}, ${s3 === s1})`); }
  { await pick(iSpec); await revert(); await press(byK("u-37"), byK("pl-1-subject")); const logged = (B.RD.st.log ?? []).length;
    sessionStorage.setItem("audit-g03", JSON.stringify({ expect: placeText("pl-1-subject"), logged }));
    P("G03", logged >= 1 && !!localStorage.getItem(`scriptt-audit:${eng[iSpec].id}:${eng[iSpec].case}`), `drop kept in the draft log (${logged} entry) and saved; the reload half runs in AUDIT_AFTER_RELOAD()`, true); }
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

  await revert();
  const line = `SCORE ${scoreN}/${scoreD} (viewport ${innerWidth}px, ${N} readings, ${Object.keys(wor).length} worlds)`;
  const text = out.join("\n") + "\n" + line; window.AUDIT_OUT = text; return text;
};
window.AUDIT_AFTER_RELOAD = async function () {   // second half of G03: after location.reload(), the draft is read again from storage
  const g = JSON.parse(sessionStorage.getItem("audit-g03") ?? "null"); await sleep(600);
  const eng = BOARD.READINGS, iSpec = eng.findIndex((r) => r.case === "C15 specimen");
  const now = (document.getElementById("pl-1-subject")?.textContent) ?? null, logged = (BOARD.RD.st.log ?? []).length;
  return `G03b after reload: show.subject "${now}" (expected "${g?.expect}"), log entries ${logged} (before ${g?.logged}): ${now === g?.expect && logged === g?.logged ? "PASS" : "FAIL"}`;
};
})();
