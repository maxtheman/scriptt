"use strict";
// Board 4. The message is the object. Every place (an open hole or a filled one) is a decision d1 made, and the user revisits it by
// dropping a value into it: words from the message, a member of the world, or another operation's result. The page computes no fit,
// validity or readiness: every drop is previewed by POST /edit and saved by POST /accept; it shows what the engine answered.
const $ = (s, r = document) => r.querySelector(s);
const el = (tag, props = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v === true) e.setAttribute(k, "");
    else if (v !== false && v != null) e.setAttribute(k, v);
  }
  e.append(...kids.flat().filter(x => x != null && x !== false));
  return e;
};
window.__net = [];
const api = async (path, body) => {
  window.__net.push({ path, body });
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  return r.json();
};
const FIXTURE = "stand-in fixture score";

const S = { lines: [], worlds: {}, log: [], id: null, base: null, pending: null, sel: null, span: null, anchor: null, focusEnd: null, held: null, hover: null, refused: null, note: "", rerun: null, cursor: 0 };
window.__S = S;

// ---- the engine's records ----
const latest = id => S.lines.filter(l => l.id === id).at(-1);
const snapshotsOf = id => S.lines.map((l, i) => ({ l, n: i + 1 })).filter(x => x.l.id === id);
const terms = r => r.phrases.flatMap(p => p.terms);
const termById = (r, id) => terms(r).find(t => String(t.id) === String(id));
const phraseOf = (r, id) => r.phrases.find(p => p.terms.some(t => String(t.id) === String(id)));
const world = () => S.worlds[S.base.world] || { types: {}, constructors: {}, functions: {} };
const view = () => (S.pending && okay(S.pending) && S.pending.draft) || S.base;
const leaves = (v, path) => v.fields ? Object.entries(v.fields).flatMap(([k, x]) => leaves(x, path + "." + k)) : [{ path, value: v }];
const places = t => Object.entries(t.arguments).flatMap(([k, v]) => leaves(v, k));
const constantsIn = v => v.constant !== undefined ? [v] : v.several ? v.several.flatMap(constantsIn) : v.fields ? Object.values(v.fields).flatMap(constantsIn) : [];
const declared = (op, path) => (op.parameters || {})[path.split(".")[0]] || "";
const pkey = (id, path) => `p:${id}:${path}`;
const say = (v, r) => v.constant !== undefined ? `“${v.constant}”` : v.ref !== undefined ? `the result of ${(termById(r, v.ref) || {}).function || "#" + v.ref}`
  : v.hole ? `open (${REASON[v.reason] ? REASON[v.reason].short : v.reason})` : v.empty ? `absent (${v.empty})` : v.several ? "[" + v.several.map(x => say(x, r)).join(", ") + "]"
  : v.fields ? "{" + Object.entries(v.fields).map(([k, x]) => `${k}: ${say(x, r)}`).join(", ") + "}" : JSON.stringify(v);
const REASON = {
  rejected: { short: "declined", long: "d1 looked at the candidates and declined every one" },
  "no candidate": { short: "nothing fits", long: "nothing in the message was a candidate for this place" },
  bounded: { short: "search stopped", long: "the search stopped at its bound before a candidate was chosen" },
  "invalid answer": { short: "bad answer", long: "d1's answer could not be read" },
  cleared: { short: "cleared", long: "you cleared this place" },
};
const reasonLong = x => (REASON[x] || { long: x }).long;
const readyWord = t => { const j = t.judgments || {}; return !j.valid ? "invalid" : !j.complete ? "incomplete" : j.ready ? "ready" : j.pending ? "waits" : ""; };
const correctionAt = (r, id, path) => r.corrections.find(c => String(c.operation) === String(id) && c.path === path);
const trim = (s, n) => s.length > n ? s.slice(0, n - 1) + "…" : s;
const brandAt = (r, pos) => (r.phrases.find(p => p.start <= pos && pos < p.end) || {}).brand || "Asked";

async function load() {
  const [lines, worlds, log] = await Promise.all(["/readings", "/worlds", "/log"].map(u => fetch(u).then(x => x.json())));
  Object.assign(S, { lines, worlds, log });
  if (!S.id) { const want = new URLSearchParams(location.search).get("r"); S.id = (want && lines.find(l => l.id.startsWith(want)) || lines.at(-1)).id; }
  S.base = latest(S.id);
  const ids = [...new Set(lines.map(l => l.id))], pick = $("#pick");
  pick.hidden = ids.length < 2;
  pick.replaceChildren(...ids.map(i => el("option", { value: i, selected: i === S.id }, `${latest(i).text.length} chars · ${trim(latest(i).text.replace(/\s+/g, " "), 44)}`)));
}

// ---- world declarations (shown, never used to decide fit; the engine decides) ----
function membersOf(name, seen = new Set()) {
  if (seen.has(name)) return []; seen.add(name);
  const w = world(), m = /^(\w+)\[(.+)\]$/.exec(name);
  if (m) return membersOf(m[2], seen);
  const t = w.types[name];
  if (!t || !t.sum) return [];
  return t.alternatives.flatMap(a => a.member ? [{ member: a.member, words: a.words, sum: name }] : a.sum ? membersOf(a.sum, seen) : []);
}
const memberValue = m => ({ constant: m.words, type: m.sum, at: [-1, -1] });
const sums = () => Object.entries(world().types).filter(([, t]) => t.sum).map(([n]) => n);

// ---- text layer: words, phrases, bricks ----
let W = [];  // word elements in text order: {el, s, e}
const wordAt = s => W.findIndex(w => w.s === s);
const tokens = text => text.split(/(\s+|[.,;:!?])/).filter(Boolean);

function render() {
  const r = view(), base = S.base, t = $("#text");
  t.replaceChildren(); W = [];
  const changed = S.pending && okay(S.pending) ? changedKeys(base, r) : new Set();
  const bound = new Map();  // char -> binds, to underline words that are some place's value
  const spansBound = [];
  for (const op of terms(r)) for (const p of places(op)) for (const c of constantsIn(p.value)) if (c.at && c.at[0] >= 0) spansBound.push({ a: c.at[0], b: c.at[1], op, path: p.path });
  S.bound = spansBound;
  const marks = [];
  for (const m of r.text.matchAll(/```[\s\S]*?```|`[^`\n]+`|^>.*$/gm)) marks.push([m.index, m.index + m[0].length, m[0][0] === ">" ? "pasted" : "code"]);
  const putWords = (parent, from, to) => {
    let pos = from;
    for (const piece of tokens(r.text.slice(from, to))) {
      if (/^(\s+|[.,;:!?])$/.test(piece)) { parent.append(piece); pos += piece.length; continue; }
      const mk = marks.find(m => pos >= m[0] && pos < m[1]);
      const b = spansBound.some(x => pos >= x.a && pos + piece.length <= x.b);
      const w = el("span", { class: "w" + (b ? " bnd" : "") + (mk ? " " + mk[2] : ""), "data-s": pos, "data-e": pos + piece.length, tabindex: -1 }, piece);
      W.push({ el: w, s: pos, e: pos + piece.length }); parent.append(w); pos += piece.length;
    }
  };
  let pos = 0;
  const gap = to => { if (to > pos) { const f = document.createDocumentFragment(); putWords(f, pos, to); t.append(f); } pos = Math.max(pos, to); };
  for (const p of r.phrases) {
    gap(p.start);
    const kind = p.terms.length ? "req" : p.unresolved.length ? "unres" : "none";
    const ph = el("span", { class: `ph ${kind}${p.quotes ? " quoted" : ""}`, "data-ph": p.start, "data-pe": p.end, title: p.terms.length ? "" : p.unresolved.length ? "d1 found a request here but could not make it an operation" : "no request: d1 found nothing to do in this phrase" });
    for (const op of p.terms) ph.append(brick(op, r, changed));
    for (const u of p.unresolved) ph.append(el("span", { class: "unres-chip", tabindex: 0, role: "button", "data-unres": u.id, "aria-label": `unresolved request: ${reasonLong(u.reason)}. Enter to inspect.` }, "? unresolved · " + (REASON[u.reason] ? REASON[u.reason].short : u.reason)));
    putWords(ph, p.start, p.end); t.append(ph); pos = p.end;
  }
  gap(r.text.length);
  tabStop(Math.min(S.cursor, W.length - 1));
  paintSpan(); paintNeeds(r); paintLegend(r); paintInsp(); paintWorld(); paintDock();
  $("#snap").textContent = snapLabel();
  $("#older").disabled = $("#rerun").disabled = !!S.pending;
  $("#how").replaceChildren(el("b", {}, "To revisit a decision, drop something into a place. "), "Click a word (then drag its ends, or Shift+←/→) to select words and drag them onto any place. Drag a world member or an operation from the side or the text onto a place. Drag a function onto a phrase to add an operation. Keyboard: Space picks up, Tab to a place, Enter drops, Esc cancels.");
}

function brick(op, r, changed) {
  const st = readyWord(op), k = pkey(op.id, "");
  const b = el("span", { class: "brick" + (changed.has(`o:${op.id}`) ? " chg" : ""), "data-brick": op.id });
  b.append(el("span", { class: "op" + (S.sel && S.sel.kind === "op" && S.sel.id === String(op.id) ? " sel" : ""), tabindex: 0, role: "button", "data-pick": "op", "data-op": op.id,
    "aria-label": `operation ${op.function} number ${op.id}, result ${op.type}${st ? ", " + st : ""}. Enter to inspect, Space to pick up its result and drop it on a place.` },
    op.function, el("span", { class: "ty" }, "→ " + op.type), st ? el("span", { class: "st " + st }, st) : null));
  for (const pl of places(op)) b.append(placeChip(op, pl, r, changed));
  return b;
}

function placeChip(op, pl, r, changed) {
  const v = pl.value, k = pkey(op.id, pl.path), c = correctionAt(r, op.id, pl.path);
  const cls = "pl" + (v.hole ? " hole" : v.constant !== undefined ? " filled" : v.ref !== undefined ? " ref" : "") + (changed.has(k) ? " chg" : "") + (S.sel && S.sel.key === k ? " sel" : "");
  const body = v.constant !== undefined ? [el("span", { class: "k" }, "← "), `“${trim(v.constant, 30)}”`] : v.ref !== undefined ? [el("span", { class: "k" }, "← "), `result of ${(termById(r, v.ref) || {}).function || "#" + v.ref}`]
    : v.hole ? [`open · ${(REASON[v.reason] || { short: v.reason }).short}`] : v.empty ? ["∅ none"] : v.several ? [`[${v.several.length} items]`] : [JSON.stringify(v)];
  const e = el("span", { class: cls, tabindex: 0, role: "button", "data-place": k, "data-op": op.id, "data-path": pl.path, "data-pick": v.constant !== undefined || v.ref !== undefined ? "place" : null,
    "aria-label": `place ${pl.path} of ${op.function}, declared ${declared(op, pl.path)}: ${say(v, r)}${c ? ", corrected by you" : ""}. Enter to inspect${v.constant !== undefined || v.ref !== undefined ? ", Space to pick its value up" : ""}. A value dropped here replaces d1's choice.` },
    el("span", { class: "k" }, pl.path + " "), ...body, c ? el("span", { class: "mark" }, c.status === "invalidated" ? " ✎✕" : " ✎") : null);
  return e;
}

const find = k => document.querySelector(`[data-place="${CSS.escape(k)}"]`);
function placeEls(op, path) { return find(pkey(op, path)); }
function tabStop(i) { W.forEach((w, j) => { w.el.tabIndex = j === i ? 0 : -1; w.el.classList.toggle("cur", j === i); }); S.cursor = i; }

// ---- selection: a span of words, with ends you can drag ----
function setSpan(a, b, opts = {}) {  // word indexes, inclusive
  if (a == null) { S.span = null; S.anchor = S.focusEnd = null; paintSpan(); return; }
  const lo = Math.min(a, b), hi = Math.max(a, b);
  S.span = { a: lo, b: hi }; S.anchor = opts.anchor ?? a; S.focusEnd = opts.focusEnd ?? b;
  paintSpan();
}
const spanText = () => S.span ? S.base.text.slice(W[S.span.a].s, W[S.span.b].e) : "";
const spanChars = () => S.span ? [W[S.span.a].s, W[S.span.b].e] : null;
function paintSpan() {
  document.querySelectorAll(".insel").forEach(e => e.classList.remove("insel"));
  document.querySelectorAll(".hdl").forEach(e => e.remove());
  if (!S.span || !W.length) return;
  for (let i = S.span.a; i <= S.span.b; i++) W[i].el.classList.add("insel");
  const n = S.span.b - S.span.a + 1;
  const h0 = el("span", { class: "hdl", "data-hdl": "start", tabindex: -1, role: "separator", "aria-label": "start of the selection: drag to change" }), h1 = el("span", { class: "hdl", "data-hdl": "end", tabindex: -1, role: "separator", "aria-label": "end of the selection: drag to change" });
  W[S.span.a].el.before(h0); W[S.span.b].el.after(h1);
}
function linkSpan(a, b, on) {
  for (const w of W) w.el.classList.toggle("link", on && w.s >= a && w.e <= b);
}

// ---- counts, needs, legend ----
function paintLegend(r) {
  const req = r.phrases.filter(p => p.terms.length).length, un = r.phrases.filter(p => !p.terms.length && p.unresolved.length).length, none = r.phrases.length - req - un;
  $("#legend").replaceChildren(...[el("span", {}, `${r.text.length.toLocaleString()} characters · ${r.phrases.length} phrases`),
    el("span", {}, el("i", { class: "sw" }), `${req} carry a request (operation bricks)`), el("span", {}, el("i", { class: "sw none" }), `${none} carry none (quiet text)`), un ? el("span", {}, el("i", { class: "sw unres" }), `${un} could not be made into an operation`) : null,
    el("span", {}, "Dashed pill = a place (a decision d1 made) · red dotted = open place")].filter(Boolean));
}
function openPlaces(r) {
  const out = [];
  for (const op of terms(r)) for (const p of places(op)) if (p.value.hole) out.push({ op, path: p.path, reason: p.value.reason });
  return out;
}
function paintNeeds(r) {
  const n = $("#needs"), open = openPlaces(r), un = r.phrases.flatMap(p => p.unresolved.map(u => ({ u, p })));
  n.replaceChildren();
  if (!open.length && !un.length) { n.append(el("span", { class: "lead" }, "No open places: every place holds a value.")); return; }
  n.append(el("span", { class: "lead" }, `Open places (${open.length}${un.length ? ", plus " + un.length + " unresolved" : ""}) — an open place is one d1 left without a value:`));
  for (const o of open) n.append(el("button", { "data-jump": pkey(o.op.id, o.path), onclick: () => { const e = find(pkey(o.op.id, o.path)); e.scrollIntoView({ block: "center" }); selectPlace(o.op.id, o.path, e); } }, `${o.op.function}#${o.op.id}.${o.path} · ${(REASON[o.reason] || { short: o.reason }).short}`));
  for (const x of un) n.append(el("button", { class: "u", onclick: () => { const e = document.querySelector(`[data-unres="${CSS.escape(String(x.u.id))}"]`); e.scrollIntoView({ block: "center" }); selectUnres(x.u.id, e); } }, `? #${x.u.id} · ${(REASON[x.u.reason] || { short: x.u.reason }).short}`));
}

// ---- what the engine's draft changed ----
function changedKeys(a, b) { const out = new Set(); for (const c of diff(a, b)) if (c.key) out.add(c.key); return out; }
const JUDGE = ["valid", "complete", "pending", "deferred", "ready"];
function diff(a, b) {
  const out = [], ta = new Map(terms(a).map(t => [String(t.id), t])), tb = new Map(terms(b).map(t => [String(t.id), t]));
  for (const [id, t] of tb) {
    if (!ta.has(id)) { out.push({ text: `new operation ${t.function}#${id}: ${places(t).map(p => p.path + " ← " + say(p.value, b)).join(", ")} (${readyWord(t) || "no state"})`, key: `o:${id}` }); continue; }
    const u = ta.get(id), pa = Object.fromEntries(places(u).map(p => [p.path, p.value])), pb = Object.fromEntries(places(t).map(p => [p.path, p.value]));
    for (const path of new Set([...Object.keys(pa), ...Object.keys(pb)])) {
      const x = pa[path] ? say(pa[path], a) : "(none)", y = pb[path] ? say(pb[path], b) : "(none)";
      if (x !== y) out.push({ text: `${t.function}#${id}.${path}`, was: x, now: y, key: pkey(id, path) });
    }
    for (const j of JUDGE) if ((u.judgments || {})[j] !== (t.judgments || {})[j]) out.push({ text: `${t.function}#${id} · ${j}`, was: String((u.judgments || {})[j]), now: String((t.judgments || {})[j]), key: `o:${id}` });
  }
  for (const [id, t] of ta) if (!tb.has(id)) out.push({ text: `operation ${t.function}#${id} removed` });
  if (a.fulfillment && !b.fulfillment) out.push({ text: "the earlier Stop check no longer applies (the engine clears it on any edit)" });
  return out;
}

// ---- the engine: one preview rule ----
const cache = new Map();
let busy = Promise.resolve();
async function ask(body) {
  const k = S.base.snapshot + JSON.stringify(body);
  if (cache.has(k)) return cache.get(k);
  const run = busy.then(async () => {
    let r; for (let tries = 0; ; tries++) { try { r = await api("/edit", body); break; } catch (e) { if (tries) { r = { error: "the engine did not answer: " + e.message }; break; } } }
    return { body, draft: r.draft || null, diagnostics: r.diagnostics || [], error: r.error };
  });
  busy = run.catch(() => 0);
  const p = run; cache.set(k, p); return p;
}
const okay = r => r && r.draft && !r.diagnostics.length && !r.error;
const RULE = { type: "its type does not fit this place", reference: "that operation is not in this reading", missing: "something it needs is missing" };
const diagWords = (d, r) => `${d[0] == null ? "new operation" : (termById(r || S.base, d[0]) || {}).function + "#" + d[0]}.${d[1]}: ${RULE[d[2]] || "engine rule “" + d[2] + "”"} [${JSON.stringify(d)}]`;
const refusalWords = (res, r) => res.error ? res.error : res.diagnostics.map(d => diagWords(d, r)).join("; ") || "refused";

// ---- what can be held ----
// kinds: words (the selected span), member (a world member), result (another operation's result), value (the value of a place, to retag),
//        fn (a world function, dropped on a phrase)
function heldWords() {
  const [a, b] = spanChars();
  return { kind: "words", label: `“${trim(spanText(), 60)}”`, value: { constant: S.base.text.slice(a, b), type: brandAt(S.base, a), at: [a, b] } };
}
const heldMember = m => ({ kind: "member", label: `${m.words} (${m.sum}.${m.member})`, value: memberValue(m) });
const heldResult = op => ({ kind: "result", label: `the result of ${op.function}#${op.id}`, value: { ref: String(op.id) }, from: null });
function heldPlace(op, pl) { const v = pl.value; return { kind: v.ref !== undefined ? "result" : "value", label: say(v, S.base), value: v, from: pkey(op.id, pl.path) }; }
const heldFn = (name, fn) => ({ kind: "fn", label: `${name}()`, fn: name, sig: fn });
function pickFrom(node) {
  const d = node.dataset;
  if (d.pick === "op") return heldResult(termById(S.base, d.op));
  if (d.pick === "place") { const op = termById(S.base, d.op), pl = places(op).find(p => p.path === d.path); return heldPlace(op, pl); }
  if (d.pick === "member") { const m = membersOf(d.sum).find(x => x.member === d.member); return heldMember(m); }
  if (d.pick === "fn") return heldFn(d.fn, world().functions[d.fn]);
  if (d.pick === "result") return heldResult(termById(S.base, d.op));
  return null;
}

// ---- targets: previewing a drop with the engine ----
function targetAt(node) {
  const p = node && node.closest && node.closest("[data-place]");
  if (p) return { kind: "place", el: p, key: p.dataset.place, op: p.dataset.op, path: p.dataset.path };
  const ph = node && node.closest && node.closest(".ph");
  if (ph && S.held && S.held.kind === "fn") return { kind: "phrase", el: ph, key: "ph:" + ph.dataset.ph, start: +ph.dataset.ph, end: +ph.dataset.pe };
  return null;
}
async function previewTarget(tg, held) {
  if (tg.kind === "place") {
    if (held.from === tg.key) return { here: true, what: "that is where it already is" };
    const op = termById(S.base, tg.op), cur = places(op).find(p => p.path === tg.path);
    const body = { reading: S.id, number: +tg.op, path: tg.path, value: held.value };
    const res = await ask(body);
    return { ...res, what: `${held.label} → ${op.function}#${op.id}.${tg.path}`, same: cur && JSON.stringify(cur.value) === JSON.stringify(held.value) };
  }
  // a function onto a phrase: the engine builds the new operation from the thing, in whichever parameter takes it
  const p = S.base.phrases.find(x => x.start === tg.start), a = S.span && S.span.a != null ? spanChars() : null;
  const at = a && a[0] >= p.start && a[1] <= p.end ? a : [p.start, p.end];
  const text = S.base.text.slice(at[0], at[1]).trim() || S.base.text.slice(p.start, p.end);
  const val = { constant: text, type: p.brand || "Asked", at: [S.base.text.indexOf(text, at[0]), S.base.text.indexOf(text, at[0]) + text.length] };
  const options = [];
  for (const [param] of held.sig.parameters) {
    const body = { reading: S.id, number: null, path: `${held.fn}.${param}`, value: val };
    options.push({ param, res: await ask(body), body });
  }
  const good = options.find(o => okay(o.res)), pick = good || options[0];
  return { ...pick.res, body: pick.body, options, what: `${held.fn}(${pick.param}) on “${trim(text, 40)}”`, fnPhrase: tg.start };
}

let hoverTimer = 0;
function hoverOn(tg) {
  const k = tg && tg.key;
  if (S.hover && S.hover.key === k) return;
  document.querySelectorAll(".hot").forEach(h => h.classList.remove("hot"));
  document.querySelectorAll("[data-fit]").forEach(h => h.removeAttribute("data-fit"));
  clearTimeout(hoverTimer);
  if (!tg || !S.held) { S.hover = null; return paintDock(); }
  tg.el.classList.add("hot");
  const h = S.hover = { key: k, tg, res: null };
  paintDock();
  hoverTimer = setTimeout(async () => {
    const res = await previewTarget(tg, S.held);
    if (S.hover === h) { h.res = res; if (!res.here) tg.el.dataset.fit = okay(res) ? "ok" : "no"; paintDock(); }
  }, 80);
}
function endHold(note) {
  S.held = null; S.hover = null; clearTimeout(hoverTimer); stopScroll();
  document.body.classList.remove("carrying");
  document.querySelectorAll(".hot").forEach(h => h.classList.remove("hot"));
  document.querySelectorAll("[data-fit]").forEach(h => h.removeAttribute("data-fit"));
  document.querySelectorAll(".ghost").forEach(g => g.remove());
  document.querySelectorAll(".chip.held").forEach(c => c.classList.remove("held"));
  if (note) S.note = note;
  paintDock();
}
function beginHold(h, from) {
  if (S.pending) return;
  S.held = h; S.refused = null; S.sel = S.sel; document.body.classList.add("carrying");
  S.note = ""; paintDock();
}
async function dropOn(tg) {
  const h = S.held; if (!h || !tg) return;
  const res = S.hover && S.hover.key === tg.key && S.hover.res ? S.hover.res : await previewTarget(tg, h);
  const anchor = tg.el;
  endHold();
  if (res.here || res.same) { S.note = "That is where it already is. Nothing changed."; return paintDock(); }
  stage(res, res.what, tg.key, anchor);
}

// ---- the transaction: preview -> consequence -> cancel or accept ----
function stage(res, what, anchorKey) {
  if (!okay(res)) { S.refused = { what, res, anchor: anchorKey }; S.pending = null; render(); return refocus(anchorKey); }
  S.pending = { body: res.body, draft: res.draft, diagnostics: res.diagnostics, what, anchor: anchorKey, failure: null };
  S.sel = null; S.refused = null; S.note = "";
  render();
  $("#accept") && $("#accept").focus();
}
function refocus(k) { if (!k) return; const e = k.startsWith("ph:") ? document.querySelector(`.ph[data-ph="${k.slice(3)}"] .w`) : find(k); if (e) { e.focus({ preventScroll: true }); } }
function cancel() { const a = S.pending && S.pending.anchor; S.pending = null; S.note = "Cancelled: the reading is back as it was. Nothing was saved."; render(); refocus(a); }
let accepting = false;
async function accept() {
  if (accepting || !S.pending) return; accepting = true;
  try { await accept1(); } catch (e) { if (S.pending) { S.pending.failure = "Not saved: " + e.message; paintDock(); } } finally { accepting = false; }
}
async function accept1() {
  const P = S.pending, fresh = await fetch("/readings").then(r => r.json()), now = fresh.filter(l => l.id === S.id).at(-1);
  if (now.snapshot !== S.base.snapshot) { P.failure = "Not saved: the store has a newer snapshot than the one this preview was made from. Your draft is kept; cancel, reload and redo it."; paintDock(); return; }
  const r = await api("/accept", P.body);
  if (r.error || (r.diagnostics || []).length || !r.saved) { P.failure = "Not saved: " + (r.error || (r.diagnostics || []).map(d => diagWords(d)).join("; ")); paintDock(); return; }
  const a = P.anchor; S.pending = null; cache.clear(); await load();
  S.note = `Accepted and saved as your correction (snapshot ${S.base.snapshot.slice(0, 6)}, ${S.base.corrections.length} correction${S.base.corrections.length === 1 ? "" : "s"}). A rerun keeps it or says why not.`; render(); refocus(a);
}
async function rerun() {
  S.note = "Rerunning: the engine reads the source again with d1…"; paintDock();
  const r = await api("/rerun", { reading: S.id });
  if (r.error) { S.note = "Rerun failed: " + r.error; return paintDock(); }
  cache.clear(); await load();
  S.sel = { kind: "rerun", data: { corrections: r.corrections || [], diagnostics: r.diagnostics || [], saved: !!r.saved } };
  S.note = r.saved ? `Rerun saved as snapshot ${S.base.snapshot.slice(0, 6)}.` : "Rerun not saved."; render();
}
async function restore(n) {
  const r = await api("/restore", { snapshot: n });
  cache.clear(); await load(); S.sel = null; S.note = r.saved ? `Restored snapshot #${n} as the latest.` : "Restore refused: " + JSON.stringify(r.diagnostics || r.error); render();
}
const snapLabel = () => { const all = snapshotsOf(S.id); return `snapshot ${all.findIndex(x => x.l === S.base) + 1} of ${all.length} · ${S.base.corrections.length} correction${S.base.corrections.length === 1 ? "" : "s"}${S.pending ? " · previewing" : ""}`; };

// ---- the dock ----
function consequence(res) {
  const ch = diff(S.base, res.draft), out = [];
  out.push(el("div", { class: "mute" }, `${ch.length} change${ch.length === 1 ? "" : "s"} in the engine's draft:`));
  for (const x of ch.slice(0, 7)) out.push(el("div", { class: "chgline" }, x.was !== undefined ? [el("strong", {}, x.text), ": ", el("span", { class: "was" }, x.was), " → ", x.now] : x.text));
  if (ch.length > 7) out.push(el("div", { class: "mute" }, `+${ch.length - 7} more`));
  if (!ch.length) out.push(el("div", { class: "mute" }, "the draft equals the reading: nothing would change."));
  return out;
}
function paintDock() {
  const d = $("#dock"), inn = el("div", { class: "in" });
  d.replaceChildren(inn);
  const P = S.pending;
  if (P) {
    d.className = "stage";
    inn.append(el("div", { class: "head" }, "Staged by the engine · nothing is saved until you accept"), el("div", { class: "mute" }, P.what), ...consequence(P));
    if (P.failure) inn.append(el("div", { class: "no", role: "alert" }, P.failure));
    inn.append(el("div", { class: "actions" }, el("button", { class: "primary", id: "accept", onclick: accept }, "Accept (saves as your correction)"), el("button", { id: "cancel", onclick: cancel }, "Cancel")));
    return;
  }
  if (S.held) {
    d.className = "";
    const H = S.hover;
    inn.append(el("div", { class: "head" }, `Holding ${S.held.label}`), el("div", { class: "mute" }, S.held.kind === "fn" ? "Move it over a phrase, release to add the operation. Esc cancels." : "Move it over a place (the dashed pills). The engine answers before you release. Esc cancels."));
    if (H) {
      if (!H.res) inn.append(el("div", {}, `Over ${H.tg.kind === "place" ? "place " + H.tg.path : "a phrase"}: asking the engine…`));
      else if (H.res.here || H.res.same) inn.append(el("div", { class: "mute" }, "That is where it already is."));
      else if (okay(H.res)) inn.append(el("div", { class: "ok" }, `Fits: ${H.res.what}. Release to stage it.`), ...consequence(H.res));
      else inn.append(el("div", { class: "no" }, `Refused by the engine: ${refusalWords(H.res)}.${H.tg.kind === "place" ? " This place is declared " + declared(termById(S.base, H.tg.op), H.tg.path) + "." : ""} Releasing here changes nothing.`));
      if (H.res && H.res.options && H.res.options.length > 1) inn.append(el("div", { class: "mute" }, "parameters tried: " + H.res.options.map(o => `${o.param} ${okay(o.res) ? "✓" : "✕"}`).join(", ")));
    }
    return;
  }
  if (S.refused) {
    d.className = "refuse";
    const R = S.refused;
    inn.append(el("div", { class: "head no" }, "The engine refused that drop"), el("div", {}, R.what), el("div", { class: "no" }, refusalWords(R.res)), el("div", { class: "mute" }, "The reading is unchanged. Try another value, or open the place to see what d1 was offered."),
      el("div", { class: "actions" }, el("button", { id: "dismiss", onclick: () => { S.refused = null; paintDock(); refocus(R.anchor); } }, "Dismiss")));
    return;
  }
  d.className = "idle";
  inn.append(S.note || "Nothing held. Select words, pick up a world member, or pick up an operation; then drop it on a place. Every drop is previewed by the engine first.");
}

// ---- the inspector ----
function closeInsp() { const s = S.sel; S.sel = null; paintInsp(); document.querySelectorAll(".sel").forEach(e => e.classList.remove("sel")); if (s && s.origin) s.origin.focus(); }
function selectPlace(opId, path, origin) {
  S.sel = { kind: "place", key: pkey(opId, path), op: String(opId), path, origin };
  const op = termById(S.base, opId), pl = places(op).find(p => p.path === path);
  if (pl && pl.value.constant !== undefined && pl.value.at[0] >= 0) { const a = wordAt(W.find(w => w.s >= pl.value.at[0])?.s), b = W.map(w => w.e).lastIndexOf(pl.value.at[1]); if (a >= 0 && b >= a) setSpan(a, b); }
  document.querySelectorAll(".sel").forEach(e => e.classList.remove("sel")); origin && origin.classList.add("sel");
  paintInsp(true);
}
function selectUnres(id, origin) { S.sel = { kind: "unres", id: String(id), origin }; paintInsp(true); }
function selectOp(id, origin) { S.sel = { kind: "op", id: String(id), origin }; document.querySelectorAll(".sel").forEach(e => e.classList.remove("sel")); origin && origin.classList.add("sel"); paintInsp(true); }
function selectWord(origin) { S.sel = { kind: "word", origin }; paintInsp(true); }

const tname = n => el("button", { class: "link", onclick: () => { S.sel = { ...S.sel, typeView: n }; paintInsp(true); } }, n);
const go = (label, fn) => el("button", { class: "link", onclick: fn }, label);

function scoreBlock(d) {
  const out = [];
  for (const [q, spec] of Object.entries(d.asked || {})) {
    const ans = (d.answers || {})[q] || {}, p = ans.probabilities || {}, entries = Object.entries(p).sort((x, y) => y[1] - x[1]);
    const standIn = entries.length > 2 && Math.abs(entries[0][1] - 0.9) < 1e-9 && entries.slice(2).every(e => Math.abs(e[1] - entries[1][1]) < 1e-9);
    out.push(el("div", { class: "q" }, spec.instructions));
    const optDesc = id => ((spec.options || []).find(o => String(o.id) === String(id)) || {}).description;
    const win = entries[0] && entries[0][0];
    for (const [id, v] of entries.slice(0, 8)) {
      const desc = optDesc(id);
      out.push(el("div", { class: "opt" + (id === win ? " chosen" : "") }, el("span", { class: "bar", style: `width:${Math.max(2, Math.round(v * 70))}px` }), `${(v * 100).toFixed(v < .01 ? 1 : 0)}% `, el("span", { class: "t" }, id), desc && id !== desc ? " " + trim(desc, 90) : "", id === win ? (id === "none" || id.startsWith("(") ? "  ← d1's answer: none of the above" : "  ← d1's answer") : ""));
    }
    if (entries.length > 8) out.push(el("div", { class: "mute" }, `+${entries.length - 8} more options`));
    out.push(el("div", { class: "prov" }, standIn ? `${FIXTURE}? These numbers have the stand-in shape (0.9 for the pick, the rest equal); the record does not name its source. Not a confidence.` : "recorded d1 score; the record does not say whether it was live or stand-in. Not a confidence."));
  }
  if ((d.offered || []).length) out.push(el("div", { class: "mute" }, "d1 was offered: " + d.offered.map(offeredWords).join(", ") + ((d.cut || []).length ? `; cut before asking: ${d.cut.length}` : "")));
  return out;
}
const offeredWords = o => o.constant !== undefined ? `“${trim(o.constant, 50)}”` : o.ref !== undefined ? `the result of #${o.ref}` : o.function ? `a new ${o.function} operation` : JSON.stringify(o);
const decisionsFor = (r, pred) => r.decisions.filter(pred);

function candidatesFor(op, path) {
  const r = S.base, ty = declared(op, path), out = [];
  const seen = new Set();
  const add = (group, label, value, sub) => { const k = JSON.stringify(value); if (seen.has(group + k)) return; seen.add(group + k); out.push({ group, label, value, sub }); };
  for (const d of decisionsFor(r, d => String(d.operation) === String(op.id) && d.path === path)) for (const o of d.offered || []) {
    if (o.constant !== undefined) add("d1 was offered", `“${trim(o.constant, 60)}”`, o); else if (o.ref !== undefined) add("d1 was offered", `the result of #${o.ref}`, o);
  }
  const ph = phraseOf(r, op.id);
  if (ph) { const raw = r.text.slice(ph.start, ph.end), lead = raw.length - raw.trimStart().length, txt = raw.trim(); if (txt) add("words of its own phrase", `“${trim(txt.replace(/\s+/g, " "), 60)}”`, { constant: txt, type: ph.brand || "Asked", at: [ph.start + lead, ph.start + lead + txt.length] }, `characters ${ph.start + lead}–${ph.start + lead + txt.length}`); }
  if (S.span) { const [a, b] = spanChars(); add("your selection", `“${trim(spanText(), 60)}”`, heldWords().value, `characters ${a}–${b}`); }
  for (const m of membersOf(ty)) add("members of " + (m.sum), `${m.words}`, memberValue(m), m.member);
  for (const t of terms(r)) if (String(t.id) !== String(op.id)) add("results of other operations", `${t.function}#${t.id} → ${t.type}`, { ref: String(t.id) });
  return out;
}

async function candidateList(box, op, path, group) {
  const list = candidatesFor(op, path).filter(c => c.group === group || (group === "members" && c.group.startsWith("members of")));
  for (const c of list) {
    const row = el("div", { class: "item" });
    const b = el("button", { class: "chip", "data-cand": c.label, onclick: async () => { const res = await ask({ reading: S.id, number: +op.id, path, value: c.value }); stage({ ...res }, `${c.label} → ${op.function}#${op.id}.${path}`, pkey(op.id, path)); } }, c.label);
    const v = el("span", { class: "verdict mute" }, c.sub || "");
    row.append(b, v); box.append(row);
    if (group !== "results of other operations") ask({ reading: S.id, number: +op.id, path, value: c.value }).then(res => { v.className = "verdict " + (okay(res) ? "ok" : "no"); v.textContent = (c.sub ? c.sub + " · " : "") + (okay(res) ? "fits" : "engine: " + refusalWords(res).replace(/ \[.*$/, "")); });
  }
}

function paintInsp(focus) {
  const c = $("#insp"), sel = S.sel;
  c.replaceChildren();
  if (!sel) { c.hidden = true; return; }
  c.hidden = false;
  const r = S.base;
  c.append(el("button", { class: "x", "aria-label": "close the inspector", onclick: closeInsp }, "×"));
  if (sel.typeView) { typePanel(c, sel.typeView); return focus && ($(".x", c) || c).focus(); }
  if (sel.kind === "history") {
    c.append(el("h2", {}, "Snapshots of this reading"), el("p", { class: "sub" }, "The store keeps every saved snapshot. Restore makes one the latest."));
    for (const { l, n } of snapshotsOf(S.id).reverse().slice(0, 40)) c.append(el("div", { class: "item" }, `#${n} · ${l.snapshot.slice(0, 6)} · ${l.corrections.length} corrections${l.fulfillment ? " · checked" : ""} `, el("button", { class: "link", disabled: l === r, onclick: () => restore(n) }, l === r ? "latest" : "Restore")));
  } else if (sel.kind === "rerun") {
    c.append(el("h2", {}, "Rerun with d1"), el("p", { class: "sub" }, "the source was read again; your corrections were applied to the new reading:"));
    if (!sel.data.corrections.length) c.append(el("div", { class: "mute" }, "no corrections to apply."));
    for (const k of sel.data.corrections) c.append(el("div", { class: "chgline" }, `${k.function || "op " + k.operation}.${k.path}: `, el("strong", { class: k.status === "retained" ? "ok" : "no" }, k.status), k.reason ? ` — ${k.reason}` : ""));
    c.append(el("p", { class: "prov" }, "Scores in the new reading come from the d1 service the harness is configured with; they are recorded as written, not graded."));
  } else if (sel.kind === "word") {
    wordPanel(c);
  } else if (sel.kind === "unres") {
    const u = r.phrases.flatMap(p => p.unresolved).find(u => String(u.id) === sel.id); if (!u) return closeInsp();
    c.append(el("h2", {}, "A request that is not an operation"), el("p", { class: "sub" }, `d1 found a request in this phrase, then ${reasonLong(u.reason)}. It stays visible as owed work.`));
    c.append(el("p", {}, "To give it a meaning, drag a function from the world (right) onto the phrase's words."));
    for (const d of decisionsFor(r, d => String(d.operation) === String(u.id))) c.append(...scoreBlock(d));
  } else if (sel.kind === "op") {
    opPanel(c);
  } else if (sel.kind === "place") {
    placePanel(c);
  }
  if (focus) { const f = $("button.chip", c) || $(".x", c); f && f.focus({ preventScroll: true }); }
}

function placePanel(c) {
  const r = S.base, op = termById(r, S.sel.op), pl = op && places(op).find(p => p.path === S.sel.path);
  if (!pl) return closeInsp();
  const v = pl.value, ty = declared(op, pl.path), cor = correctionAt(r, op.id, pl.path), ph = phraseOf(r, op.id);
  c.append(el("h2", {}, `${op.function}#${op.id} · ${pl.path}`));
  c.append(el("p", { class: "sub" }, "declared type ", tname(ty), cor ? ` · ✎ your correction: ${cor.status}${cor.reason ? " — " + cor.reason : ""}` : ""));
  if (v.hole) c.append(el("p", { class: "no" }, `Open: ${reasonLong(v.reason)}.`));
  else c.append(el("p", {}, "d1 chose: ", el("strong", {}, say(v, r))));
  if (v.constant !== undefined && v.at[0] >= 0) {
    c.append(el("h3", {}, "Adjust its words"));
    const adj = (label, a, b) => { const A = Math.max(0, a), B = Math.min(r.text.length, b); return el("button", { "data-adj": label, disabled: A >= B, onclick: () => adjust(op, pl, a, b) }, label); };
    const i0 = W.findIndex(w => w.s >= v.at[0]), i1 = W.map(w => w.e).lastIndexOf(v.at[1]);
    const prev = W[i0 - 1], next = W[i1 + 1];
    c.append(el("div", { class: "actions" },
      adjust1("+ word before", prev ? [prev.s, v.at[1]] : null, op, pl), adjust1("− first word", i1 > i0 ? [W[i0 + 1].s, v.at[1]] : null, op, pl),
      adjust1("− last word", i1 > i0 ? [v.at[0], W[i1 - 1].e] : null, op, pl), adjust1("+ word after", next ? [v.at[0], next.e] : null, op, pl)));
  }
  const ds = decisionsFor(r, d => String(d.operation) === String(op.id) && d.path === pl.path);
  c.append(el("h3", {}, "What d1 was asked here"));
  if (!ds.length) c.append(el("p", { class: "mute" }, "No decision is recorded for this place (a correction or a value from another place)."));
  ds.forEach((d, i) => c.append(el("details", { open: i === 0 }, el("summary", {}, `d1's question about this place${ds.length > 1 ? " " + (i + 1) : ""}`), ...scoreBlock(d))));
  c.append(el("h3", {}, "Put something here"));
  c.append(el("p", { class: "sub" }, "Drag from the text or the world onto this place — or choose below. The engine checks each one."));
  const groups = [...new Set(candidatesFor(op, pl.path).map(x => x.group))];
  for (const g of groups) {
    const box = el("div"), isRes = g === "results of other operations";
    const cnt = candidatesFor(op, pl.path).filter(x => x.group === g).length;
    const det = el("details", { open: !isRes }, el("summary", {}, `${g} (${cnt})`), box);
    c.append(det);
    if (!isRes) candidateList(box, op, pl.path, g);
    else det.addEventListener("toggle", () => { if (det.open && !box.childNodes.length) candidateList(box, op, pl.path, g); });
  }
  if (!S.span) c.append(el("p", { class: "mute" }, "Select words in the text to offer them here."));
  c.append(el("div", { class: "actions" }, el("button", { "data-clear": 1, disabled: v.hole !== undefined, onclick: async () => stage(await ask({ reading: S.id, number: +op.id, path: pl.path, value: null }), `Clear ${op.function}#${op.id}.${pl.path}`, pkey(op.id, pl.path)) }, "Clear this place")));
}
function adjust1(label, ab, op, pl) { return el("button", { "data-adj": label, disabled: !ab, onclick: () => adjust(op, pl, ab[0], ab[1]) }, label); }
async function adjust(op, pl, a, b) {
  const value = { constant: S.base.text.slice(a, b), type: pl.value.type, at: [a, b] };
  stage(await ask({ reading: S.id, number: +op.id, path: pl.path, value }), `Change the words at ${op.function}#${op.id}.${pl.path} to “${trim(value.constant, 50)}”`, pkey(op.id, pl.path));
}

function wordPanel(c) {
  const r = S.base;
  if (!S.span) { c.append(el("h2", {}, "Nothing selected")); return; }
  const [a, b] = spanChars(), p = r.phrases.find(p => p.start <= a && a < p.end);
  c.append(el("h2", {}, `“${trim(spanText(), 70)}”`), el("p", { class: "sub" }, `${S.span.b - S.span.a + 1} word${S.span.b > S.span.a ? "s" : ""} · characters ${a}–${b} · ${p && p.quotes ? "quoted: the engine matched it to an earlier reply in the log" : "counted as your words (the engine marks quoted text only when the log holds that reply)"}`));
  if (p) {
    const reads = p.terms.length ? `read as ${p.terms.map(t => t.function + "#" + t.id).join(" + ")}` : p.unresolved.length ? "a request d1 could not name" : "no request: d1 found nothing to do here";
    c.append(el("p", {}, `Its phrase (characters ${p.start}–${p.end}) is ${reads}. The engine reads whole phrases, not single words.`));
    for (const t of p.terms) c.append(el("div", {}, go(`inspect ${t.function}#${t.id}`, () => selectOp(t.id, document.querySelector(`.op[data-op="${t.id}"]`)))));
  }
  c.append(el("h3", {}, "Use these words at"));
  c.append(el("p", { class: "sub" }, "Drag the selection onto a place (grab it by any highlighted word), or choose an open place:"));
  const open = openPlaces(r);
  if (!open.length) c.append(el("p", { class: "mute" }, "No open places. Drop them on a filled place to change what d1 chose."));
  for (const o of open.slice(0, 12)) c.append(el("div", { class: "item" }, el("button", { class: "chip", "data-use": pkey(o.op.id, o.path), onclick: async () => { const h = heldWords(); stage(await ask({ reading: S.id, number: +o.op.id, path: o.path, value: h.value }), `${h.label} → ${o.op.function}#${o.op.id}.${o.path}`, pkey(o.op.id, o.path)); } }, `${o.op.function}#${o.op.id}.${o.path}`), el("span", { class: "verdict mute" }, (REASON[o.reason] || { short: o.reason }).short)));
  if (open.length > 12) c.append(el("p", { class: "mute" }, `+${open.length - 12} more open places (use the strip above the text)`));
  c.append(el("p", { class: "mute" }, "Keyboard: Space picks the selection up; Tab to a place; Enter drops; Esc cancels."));
}

function opPanel(c) {
  const r = S.base, op = termById(r, S.sel.id); if (!op) return closeInsp();
  const p = phraseOf(r, op.id), fn = world().functions[op.function], j = op.judgments || {};
  c.append(el("h2", {}, `${op.function}#${op.id}`), el("p", { class: "sub" }, `read from the phrase “${trim(r.text.slice(p.start, p.end).replace(/\s+/g, " "), 60)}” · result `, tname(op.type)));
  if (fn) { c.append(el("p", {}, fn.asks)); for (const [n] of fn.parameters) c.append(el("div", {}, el("span", { class: "t" }, n), " : ", tname(op.parameters[n] || "?"))); }
  c.append(el("p", {}, `valid ${j.valid} · complete ${j.complete} · ready ${j.ready} · pending ${j.pending}`));
  for (const d of j.diagnostics || []) c.append(el("p", { class: "no" }, diagWords(d, r)));
  c.append(el("p", { class: "mute" }, "Drag it (the brick's name) onto a place to use its result there."));
  const ds = decisionsFor(r, d => String(d.operation) === String(op.id) && d.path == null && d.function == null);
  if (ds.length) c.append(el("details", {}, el("summary", {}, "why d1 made this operation"), ...ds.flatMap(scoreBlock)));
  c.append(el("h3", {}, "Places"));
  for (const pl of places(op)) c.append(el("div", {}, go(`${pl.path}: ${say(pl.value, r)}`, () => { const e = find(pkey(op.id, pl.path)); selectPlace(op.id, pl.path, e); })));
}

function typePanel(c, name) {
  const w = world(), m = /^(\w+)\[(.+)\]$/.exec(name), t = w.types[name];
  c.append(el("button", { class: "link", onclick: () => { S.sel = { ...S.sel, typeView: null }; paintInsp(true); } }, "← back"), el("h2", {}, name), el("p", { class: "sub" }, t ? `kind ${t.kind}` : m ? "a constructed type" : "not declared in this world"));
  if (m) { const k = w.constructors[m[1]]; c.append(el("p", {}, el("span", { class: "t" }, m[1]), `: ${k ? k.kind + ", " + k.describes : "(not declared)"}`), el("p", {}, "of ", tname(m[2]))); }
  if (t) {
    if (t.sum) c.append(el("p", {}, "a sum of: ", t.alternatives.map(a => a.member ? `${a.member}=“${a.words}”` : a.sum ? a.sum : "?").join(" | ")));
    else if (t.brand) c.append(el("p", {}, "a brand over ", tname(t.of.brand || t.of.base || "?"), "; the brand is a nominal label."));
    else if (t.base) c.append(el("p", {}, `the base type ${t.base}`));
  }
  const holders = terms(S.base).flatMap(op => places(op).filter(p => declared(op, p.path) === name).map(p => `${op.function}#${op.id}.${p.path}`));
  c.append(el("p", {}, holders.length ? `places declared with exactly this type here: ${holders.slice(0, 12).join(", ")}${holders.length > 12 ? "…" : ""}` : "no place declared with exactly this type in this message."));
}

// ---- the world: what can be carried ----
function paintWorld() {
  const w = $("#world"), w0 = world(), open = w.querySelector("details[open]");
  const keep = new Set([...w.querySelectorAll("details[open]")].map(d => d.dataset.k));
  w.replaceChildren(el("h2", {}, "The world"), el("p", { class: "sub" }, "Nothing here is new: these are what this world already has. Drag (or click, then click a place) to use one."));
  const det = (k, title, ...kids) => { const d = el("details", { "data-k": k }, el("summary", {}, title), ...kids); if (keep.has(k)) d.open = true; return d; };
  w.append(det("members", `Members (${sums().reduce((n, s) => n + membersOf(s).length, 0)})`, ...sums().map(s => el("div", { class: "tyrow" }, el("div", { class: "tn" }, s), el("div", { class: "item" }, ...membersOf(s).map(m => el("button", { class: "chip", "data-pick": "member", "data-sum": s, "data-member": m.member, title: `${s}.${m.member}`, "aria-label": `world member ${m.words}, of ${s}. Space or Enter to pick up, then Tab to a place and Enter.` }, m.words)))))));
  w.append(det("fns", `Functions (${Object.keys(w0.functions).length})`, el("p", { class: "mute" }, "Drag one onto a phrase of the text to add an operation there."), ...Object.entries(w0.functions).map(([n, f]) => el("div", { class: "item" }, el("button", { class: "chip fn", "data-pick": "fn", "data-fn": n, "aria-label": `function ${n}: ${f.asks}. Space or Enter to pick up, then move to a word and press Enter to add it to that phrase.` }, n + "(" + f.parameters.map(p => p[0]).join(", ") + ")"), el("span", { class: "verdict mute" }, trim(f.asks, 48))))));
  const ops = terms(S.base);
  w.append(det("results", `Results in this message (${ops.length})`, ...ops.map(op => el("div", { class: "item" }, el("button", { class: "chip", "data-pick": "result", "data-op": op.id, "aria-label": `the result of ${op.function} number ${op.id}. Space or Enter to pick up.` }, `${op.function}#${op.id}`), el("span", { class: "verdict mute" }, `→ ${op.type}`)))));
}

// ---- auto-scroll while carrying: a long message has to be reachable mid-drag ----
let scrollRaf = 0, lastY = 0;
function scrollLoop() { const h = innerHeight; const dy = lastY < 90 ? -Math.ceil((90 - lastY) / 4) : lastY > h - 200 ? Math.ceil((lastY - (h - 200)) / 4) : 0; if (dy) scrollBy(0, dy); scrollRaf = S.held || ptr ? requestAnimationFrame(scrollLoop) : 0; }
function stopScroll() { cancelAnimationFrame(scrollRaf); scrollRaf = 0; }

// ---- pointer ----
let ptr = null, swallowClick = false;
const wordIndexOf = n => { const w = n && n.closest && n.closest(".w"); return w ? W.findIndex(x => x.el === w) : -1; };
document.addEventListener("pointerdown", e => {
  if (e.button !== 0 || S.pending) return;
  if (S.held && S.held.clickHeld) return;  // click-click mode: the click handler drops
  const t = e.target;
  if (t.closest("#insp, #dock, header, #needs")) return;
  const hdl = t.closest(".hdl");
  if (hdl) { e.preventDefault(); ptr = { mode: "handle", which: hdl.dataset.hdl, x: e.clientX, y: e.clientY, moved: false }; return; }
  const pick = t.closest("[data-pick]");
  if (pick) { e.preventDefault(); ptr = { mode: "carry", pick, x: e.clientX, y: e.clientY, started: false }; return; }
  const wi = wordIndexOf(t);
  if (wi >= 0) {
    e.preventDefault();
    if (S.span && wi >= S.span.a && wi <= S.span.b && !e.shiftKey) ptr = { mode: "carry-sel", x: e.clientX, y: e.clientY, started: false, wi };
    else ptr = { mode: "select", from: e.shiftKey && S.anchor != null ? S.anchor : wi, x: e.clientX, y: e.clientY, moved: false, wi };
  }
});
document.addEventListener("pointermove", e => {
  if (!ptr) { if (S.held && S.held.clickHeld) hoverFollow(e); return; }
  lastY = e.clientY;
  const far = Math.hypot(e.clientX - ptr.x, e.clientY - ptr.y) >= 5;
  if (ptr.mode === "carry" || ptr.mode === "carry-sel") {
    if (!ptr.started) {
      if (!far) return;
      let h; try { h = ptr.mode === "carry" ? pickFrom(ptr.pick) : heldWords(); } catch { h = null; }
      if (!h) { ptr = null; return; }
      ptr.started = true; beginHold(h); if (!S.held) { ptr = null; return; }
      ptr.ghost = el("div", { class: "ghost" }, h.label); document.body.append(ptr.ghost);
      if (!scrollRaf) scrollRaf = requestAnimationFrame(scrollLoop);
    }
    ptr.ghost.style.left = e.clientX + 14 + "px"; ptr.ghost.style.top = e.clientY + 14 + "px";
    hoverFollow(e);
  } else if (ptr.mode === "select" || ptr.mode === "handle") {
    if (!far && !ptr.moved) return; ptr.moved = true;
    const wi = wordIndexOf(document.elementFromPoint(e.clientX, e.clientY));
    if (wi < 0) return;
    if (ptr.mode === "select") setSpan(ptr.from, wi, { anchor: ptr.from, focusEnd: wi });
    else { const other = ptr.which === "start" ? S.span.b : S.span.a; setSpan(other, wi, { anchor: other, focusEnd: wi }); }
    if (!scrollRaf) scrollRaf = requestAnimationFrame(scrollLoop);
  }
});
function hoverFollow(e) { const stack = document.elementsFromPoint(e.clientX, e.clientY); const tg = stack.map(x => targetAt(x)).find(Boolean); hoverOn(tg || null); }
document.addEventListener("pointerup", async e => {
  if (!ptr) return;
  const p = ptr; ptr = null; stopScroll();
  if (p.mode === "carry" || p.mode === "carry-sel") {
    if (!p.started) { if (p.mode === "carry-sel") { setSpan(p.wi, p.wi); tabStop(p.wi); } return; }  // a click: the click handler inspects
    p.ghost.remove(); swallowClick = true; setTimeout(() => { swallowClick = false; }, 0);
    const stack = document.elementsFromPoint(e.clientX, e.clientY), tg = stack.map(x => targetAt(x)).find(Boolean);
    if (tg) { if (!S.hover || S.hover.key !== tg.key) hoverOn(tg); await dropOn(tg); }
    else { endHold("Dropped outside any place: nothing changed."); }
  } else if (p.mode === "select") {
    swallowClick = true; setTimeout(() => { swallowClick = false; }, 0);
    if (!p.moved) setSpan(p.from === p.wi ? p.wi : Math.min(p.from, p.wi), p.from === p.wi ? p.wi : Math.max(p.from, p.wi), { anchor: p.from === p.wi ? p.wi : p.from, focusEnd: p.wi });
    tabStop(S.focusEnd ?? p.wi); W[S.cursor].el.focus({ preventScroll: true });
    selectWord(W[S.cursor].el); S.note = `Selected “${trim(spanText(), 50)}”. Drag it onto a place, or press Space to pick it up.`; paintDock();
  } else if (p.mode === "handle") {
    swallowClick = true; setTimeout(() => { swallowClick = false; }, 0); selectWord(W[S.focusEnd].el); S.note = `Selection is now “${trim(spanText(), 50)}”.`; paintDock();
  }
});
addEventListener("pointercancel", () => { if (ptr && ptr.ghost) ptr.ghost.remove(); if (ptr && ptr.started) endHold("Drag cancelled: nothing changed."); ptr = null; stopScroll(); });

// click: inspect (no drag happened); or, in click-click mode, drop
document.addEventListener("click", e => {
  if (swallowClick) return;
  const t = e.target;
  if (S.held && S.held.clickHeld) {
    const tg = targetAt(t); if (tg) { if (!S.hover || S.hover.key !== tg.key) hoverOn(tg); return void dropOn(tg); }
    if (!t.closest("[data-pick]")) return void endHold("Cancelled: nothing changed.");
  }
  if (t.closest("#insp, #dock, header, #needs")) return;
  const pl = t.closest("[data-place]"); if (pl) { if (S.pending) return; return selectPlace(pl.dataset.op, pl.dataset.path, pl); }
  const un = t.closest("[data-unres]"); if (un) return selectUnres(un.dataset.unres, un);
  const op = t.closest(".op[data-op]"); if (op) return selectOp(op.dataset.op, op);
  const pk = t.closest("#world [data-pick]"); if (pk && !S.pending) { const h = pickFrom(pk); beginHold(h); S.held.clickHeld = true; pk.classList.add("chip", "held"); S.note = ""; paintDock(); return; }
});

// ---- keyboard ----
function focusWord(i, extend, moveAnchor) {
  i = Math.max(0, Math.min(W.length - 1, i));
  if (extend) { if (!S.span) { S.anchor = S.cursor; S.focusEnd = S.cursor; } if (moveAnchor) S.anchor = i; else S.focusEnd = i; setSpan(S.anchor, S.focusEnd, { anchor: S.anchor, focusEnd: S.focusEnd }); S.note = `Selection: “${trim(spanText(), 60)}” (${S.span.b - S.span.a + 1} word${S.span.b > S.span.a ? "s" : ""}). Space picks it up.`; paintDock(); }
  tabStop(i); W[i].el.focus(); W[i].el.scrollIntoView({ block: "nearest" });
  if (S.held && S.held.kind === "fn") hoverOn(targetAt(W[i].el));
}
const phraseStarts = () => [...document.querySelectorAll(".ph")].map(p => wordAt(+(p.querySelector(".w") || { dataset: { s: -1 } }).dataset.s)).filter(i => i >= 0);
addEventListener("keydown", e => {
  const t = e.target;
  if (e.key === "Escape") {
    if (S.held) { const h = S.held; endHold("Cancelled: nothing changed."); return; }
    if (S.pending) return cancel();
    if (S.refused) { S.refused = null; return paintDock(); }
    if (S.sel && S.sel.typeView) { S.sel = { ...S.sel, typeView: null }; return paintInsp(true); }
    if (S.sel) return closeInsp();
    if (S.span) { setSpan(null); return; }
    return;
  }
  if (t.closest && t.closest("#insp, #dock, header, #needs") && !S.held) return;
  const inWord = t.classList && t.classList.contains("w");
  if (S.held && (e.key === "o" || e.key === "O") && !e.metaKey && !e.ctrlKey) {  // jump to the next open place
    const all = [...document.querySelectorAll(".pl.hole")]; if (!all.length) return;
    const i = all.indexOf(document.activeElement); e.preventDefault(); const n = all[(i + 1) % all.length]; n.focus(); n.scrollIntoView({ block: "center" }); hoverOn(targetAt(n)); return;
  }
  if (inWord) {
    const i = W.findIndex(w => w.el === t);
    if (i !== S.cursor) tabStop(i);
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") { e.preventDefault(); focusWord(i + (e.key === "ArrowRight" ? 1 : -1), e.shiftKey, e.altKey); return; }
    if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); const ps = phraseStarts(), cur = ps.filter(x => x <= i).at(-1) ?? 0, k = ps.indexOf(cur); focusWord(e.key === "ArrowDown" ? ps[Math.min(ps.length - 1, k + 1)] : (i > cur ? cur : ps[Math.max(0, k - 1)]), e.shiftKey); return; }
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      if (S.held) { const tg = targetAt(t); if (tg) { if (!S.hover || S.hover.key !== tg.key) hoverOn(tg); return void dropOn(tg); } S.note = "That word is not a place to drop on. Tab to a place, or for a function press Enter on a word of the phrase."; return paintDock(); }
      if (!S.span || i < S.span.a || i > S.span.b) setSpan(i, i);
      if (e.key === "Enter") { selectWord(t); S.note = `Selected “${trim(spanText(), 50)}”. Shift+←/→ extends it (Alt+Shift moves the other end). Space picks it up.`; paintDock(); $("#insp button.chip") && 0; return; }
      const h = heldWords(); beginHold(h); S.note = ""; placeCursorOnFirstPlace(); return;
    }
    return;
  }
  const pick = t.closest && t.closest("[data-pick]");
  const plc = t.closest && t.closest("[data-place]"), un = t.closest && t.closest("[data-unres]");
  if (e.key === "Enter" || e.key === " ") {
    if (S.held && plc) { e.preventDefault(); const tg = targetAt(plc); if (!S.hover || S.hover.key !== tg.key) hoverOn(tg); return void dropOn(tg); }
    if (S.held) return;
    if (e.key === " " && pick && !S.pending) { e.preventDefault(); const h = pickFrom(pick); beginHold(h); S.note = ""; if (pick.closest("#world")) { pick.classList.add("held"); placeCursorOnFirstPlace(); } return; }
    if (e.key === "Enter" && !S.pending) {
      if (plc) { e.preventDefault(); return selectPlace(plc.dataset.op, plc.dataset.path, plc); }
      if (un) { e.preventDefault(); return selectUnres(un.dataset.unres, un); }
      const op = t.closest(".op[data-op]"); if (op) { e.preventDefault(); return selectOp(op.dataset.op, op); }
      if (pick && pick.closest("#world")) { e.preventDefault(); const h = pickFrom(pick); beginHold(h); pick.classList.add("held"); placeCursorOnFirstPlace(); return; }
    }
  }
});
function placeCursorOnFirstPlace() {
  if (S.held && S.held.kind === "fn") { const f = W[S.cursor]; f && f.el.focus(); S.note = "Holding a function: move to a word of the phrase (←/→, ↑/↓ jump phrases) and press Enter to add it there."; paintDock(); return; }
  const p = document.querySelector(".pl.hole") || document.querySelector(".pl"); if (p) { p.focus(); p.scrollIntoView({ block: "center" }); hoverOn(targetAt(p)); }
}
document.addEventListener("focusin", e => {
  if (e.target.classList && e.target.classList.contains("w")) { const i = W.findIndex(w => w.el === e.target); if (i >= 0 && i !== S.cursor) tabStop(i); }
  if (!S.held || ptr) return;
  const tg = targetAt(e.target);
  if (tg) hoverOn(tg);
});

// a place and its words are one thing: hovering or focusing the place lights the words it holds, and a ref lights the operation it points at
const linkFor = (n, on) => {
  const pl = n.closest && n.closest("[data-place]"); if (!pl) return;
  const op = termById(view(), pl.dataset.op), p = op && places(op).find(x => x.path === pl.dataset.path); if (!p) return;
  if (p.value.constant !== undefined && p.value.at[0] >= 0) linkSpan(p.value.at[0], p.value.at[1], on);
  if (p.value.ref !== undefined) { const b = document.querySelector(`.brick[data-brick="${CSS.escape(String(p.value.ref))}"]`); b && b.classList.toggle("link", on); }
};
document.addEventListener("mouseover", e => linkFor(e.target, true)); document.addEventListener("mouseout", e => linkFor(e.target, false));
document.addEventListener("focusin", e => linkFor(e.target, true)); document.addEventListener("focusout", e => linkFor(e.target, false));
$("#rerun").addEventListener("click", rerun);
$("#older").addEventListener("click", () => { S.pending = null; S.sel = { kind: "history" }; render(); $("#insp .x").focus(); });
$("#pick").addEventListener("change", async e => { S.id = e.target.value; S.sel = S.pending = null; S.span = null; S.cursor = 0; cache.clear(); await load(); render(); });

load().then(() => { render(); S.note = "The engine's reading, from /readings. Scores are recorded inputs; the record does not say whether a live or a stand-in d1 wrote them."; paintDock(); });
