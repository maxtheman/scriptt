"use strict";
// The board. The message is one wiki page over the world: every piece of `pieces` is a piped link to its kind, every operation is a
// function span over its phrase with its places inside it. Every drag is a Dragology drag spec over candidate states; each
// candidate state is an engine request (/edit), and the state drawn under the pointer is the engine's draft for it (the `drafted`
// modifier below). Nothing here decides what fits: the engine's diagnostics do.
const DG = window.Dragology;
const { React, createRoot, DraggableRenderer, translate } = DG;
const h = React.createElement;
const $ = (id) => document.getElementById(id);

// ---------- records ----------
let LINES = [], LATEST = new Map(), IDX = new Map(), WORLDS = {};
const S = { id: null, base: null, staged: null, open: null, scroll: 0, pscroll: 0, focus: null, zone: "text", hold: null, undo: [], note: null, more: {} };
async function post(path, body) {
  try { return await (await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })).json(); }
  catch (x) { return { error: String(x) }; }
}
async function loadAll() {
  const [lines, worlds] = await Promise.all([fetch("/readings").then((r) => r.json()), fetch("/worlds").then((r) => r.json())]);
  LINES = lines; WORLDS = worlds; LATEST = new Map(); IDX = new Map();
  lines.forEach((l, i) => { LATEST.set(l.id, l); IDX.set(l.snapshot, i + 1); });
}

// ---------- the engine queue: one request at a time (the server is single threaded), the one under the pointer first ----------
const DRAFTS = new Map();
let Q = [], BUSY = false, DV = 0, DRAGGING = false, PENDING = false, HELD = null;
const bkey = (b) => S.base.snapshot + "|" + JSON.stringify(b);
let HOLDN = 0;
function newHold() { // verdicts still queued for an earlier hold are dropped (asked again if needed)
  HOLDN++;
  Q = Q.filter((e) => !(e.batch && e.hold !== HOLDN));
}
// The engine's verdict for many places at once: POST /edits with drafts: false (diagnostics only), one loaded snapshot.
const VERD = new Map();
function verdicts(bodies) {
  const todo = bodies.filter((b) => { const k = bkey(b), e = DRAFTS.get(k); return !(e && e.done) && !VERD.has(k); });
  if (!todo.length) return;
  Q.unshift({ batch: todo, snap: S.base.snapshot, hold: HOLDN }); // before previews: the rail needs it at once
  pump();
}
function ask(body, front, bg) {
  const k = bkey(body);
  let e = DRAFTS.get(k);
  if (!e) { e = { k, body, done: false, snap: S.base.snapshot, bg: !!bg, hold: HOLDN }; DRAFTS.set(k, e); Q.push(e); }
  if (!bg) e.bg = false;
  if (front && !e.done) { // the state under the pointer (or the key) now: previews queued for earlier ones are dropped
    Q = Q.filter((x) => { if (x !== e && x.preview && !x.batch) { DRAFTS.delete(x.k); return false; } return x !== e; });
    e.preview = true;
    Q.unshift(e);
  }
  pump();
  return e;
}
async function pump() {
  if (BUSY) return;
  BUSY = true;
  while (Q.length) {
    const e = Q.shift();
    if (e.snap !== S.base.snapshot) { if (e.k) DRAFTS.delete(e.k); continue; }
    if (e.batch) {
      const r = await post("/edits", { reading: S.id, edits: e.batch, drafts: false });
      if (r.snapshot && r.snapshot !== S.base.snapshot) S.stale = r.snapshot; // the engine answered for a newer snapshot than the one drawn
      else (r.results || []).forEach((x, i) => VERD.set(bkey(e.batch[i]), x.diagnostics || []));
      DV++;
      if (!DRAGGING && !PENDING) paint();
      continue;
    }
    const r = await post("/edit", { reading: S.id, ...e.body });
    Object.assign(e, { draft: r.draft || null, diag: r.diagnostics || [], error: r.error || null, done: true });
    DV++;
    if (!DRAGGING && !PENDING) paint();
  }
  BUSY = false;
}
const verdict = (e) => (!e || !e.done ? "wait" : e.error || (e.diag && e.diag.length) || !e.draft ? "no" : "ok");
const peek = (body) => DRAFTS.get(bkey(body));
const vOf = (body) => { const e = peek(body); if (e && e.done) return verdict(e); const v = VERD.get(bkey(body)); return v ? (v.length ? "no" : "ok") : "wait"; };
const codes = (e) => (e.error ? [e.error.split(":")[0]] : (e.diag || []).map((d) => d.filter((x) => x != null).join(" · ")));

// ---------- the world ----------
const world = () => WORLDS[S.base.world] || Object.values(WORLDS)[0];
function tname(t) {
  if (!t) return "?";
  if (t.constructor && typeof t.constructor === "string") return `${t.constructor}[${tname(t.of)}]`;
  if (t.sum) return t.sum;
  if (t.brand) return t.brand;
  if (t.product) return t.product;
  if (t.base) return t.base;
  if (t.member) return t.member;
  return "?";
}
const parseT = (n) => { const m = /^(\w+)\[(.+)\]$/.exec(n || ""); return m ? { con: m[1], arg: m[2] } : null; };
const isFn = (k) => !!(k && world().functions[k]);
const cat = (k) => (k == null ? "null" : k === "(none)" ? "none" : isFn(k) ? "fn" : parseT(k) ? "con" : "type");
const inner = (n) => { let p = parseT(n); while (p) { n = p.arg; p = parseT(n); } return n; };
const mentions = (t, name) => !!t && (tname(t) === name || mentions(t.of, name) || (t.alternatives || []).some((a) => !a.member && mentions(a, name)));
function members(t) { return (t.alternatives || []).flatMap((a) => (a.member ? [{ ...a, of: t.sum }] : members(a))); }
// each type's docstring: world_record's `describes` (older worlds: the description d1 was given for its option)
function docOf(name) {
  const t = world().types[name];
  if (t && t.describes != null) return t.describes || null;
  for (const d of S.base.decisions) if (d.path === "kind") for (const q of Object.values(d.asked || {})) for (const o of q.options || []) if (o.id === name) return o.description;
  return null;
}

// ---------- the reading ----------
const allTerms = (rec) => rec.phrases.flatMap((p, pi) => p.terms.map((t) => ({ t, p, pi })));
function placesOf(t) {
  const out = [], seen = new Set();
  const walk = (args, pre, params) => {
    for (const [k, v] of Object.entries(args || {})) {
      const path = pre ? pre + "." + k : k;
      seen.add(path);
      if (v && v.fields) walk(v.fields, path, {});
      else out.push({ t, path, v, declared: (params || {})[k] || (v && (v.hole || v.empty || v.type)) || "?" });
    }
  };
  walk(t.arguments, "", t.parameters);
  for (const [k, d] of Object.entries(t.parameters || {})) if (!seen.has(k)) out.push({ t, path: k, v: null, declared: d });
  return out;
}
const pkey = (t, path) => `${t.id}-${path.replace(/\./g, "_")}`;
function kindWords(rec) { // the words of each kind question, found in order in the phrase's text
  if (rec.__kw) return rec.__kw;
  const out = [];
  for (const d of rec.decisions) {
    if (d.path !== "kind" || !d.phrase) continue;
    let at = d.phrase[0];
    for (const [w, q] of Object.entries(d.asked || {})) {
      const m = /the words "(.*)" are part/.exec(q.instructions || "");
      if (!m) continue;
      const i = rec.text.indexOf(m[1], at);
      if (i < 0 || i > d.phrase[1]) continue;
      out.push({ s: i, e: i + m[1].length, w, q, a: (d.answers || {})[w], d });
      at = i + m[1].length;
    }
  }
  Object.defineProperty(rec, "__kw", { value: out, enumerable: false });
  return out;
}

// ---------- measures ----------
const SANS = '"IBM Plex Sans", system-ui, sans-serif', MONO = '"IBM Plex Mono", ui-monospace, Menlo, monospace';
const F = { text: `16px ${SANS}`, it: `italic 16px ${SANS}`, code: `13.5px ${MONO}`, mono: `12px ${MONO}`, monoB: `600 12px ${MONO}`, small: `12px ${MONO}`, head: `600 13px ${SANS}` };
const CTX = document.createElement("canvas").getContext("2d");
const MW = new Map();
const tw = (s, f) => { const k = f + "\u0000" + s; let w = MW.get(k); if (w == null) { CTX.font = f; w = CTX.measureText(s).width; MW.set(k, w); } return w; };
const LH = 46, TOP = 14, X0 = 28;
let BW = 1200, BH = 800, TW = 720, PX = 800, PW = 380, C = {};
function sizes() {
  const b = $("board");
  BW = Math.max(900, b.clientWidth); BH = Math.max(400, b.clientHeight);
  TW = Math.min(760, Math.round(BW * 0.58) - X0); PX = X0 + TW + 56; PW = BW - PX - 16;
  const cs = getComputedStyle(document.documentElement), v = (n) => cs.getPropertyValue(n).trim();
  C = { ink: v("--ink"), mute: v("--mute"), faint: v("--faint"), rule: v("--rule"), bg: v("--bg"), card: v("--card"), tint: v("--tint"), type: v("--type"), typeBg: v("--type-bg"), fn: v("--fn"), fnBg: v("--fn-bg"), con: v("--con"), conBg: v("--con-bg"), acc: v("--accent"), accBg: v("--accent-bg"), no: v("--no"), noBg: v("--no-bg"), paste: v("--paste") };
}
const colorOf = (k) => ({ type: C.type, con: C.con, fn: C.fn, none: C.mute, null: C.no })[cat(k)];
const visLines = () => Math.floor((BH - TOP - 52) / LH);

// ---------- layout: words, then the function spans after their phrase, wrapped ----------
const LAY = new WeakMap();
function layout(rec) {
  let L = LAY.get(rec);
  if (L && L.tw === TW) return L;
  const text = rec.text, words = [], chunks = [];
  // pasted text: lines that start with ">" and lines inside ``` fences, and phrases that are not the user's own words
  const style = new Uint8Array(text.length + 1);
  let off = 0, fence = false, pasted = false;
  for (const line of text.split("\n")) {
    const tl = line.trim();
    if (/<pasted_content\b/.test(tl)) pasted = true;
    const inPaste = pasted;
    if (/<\/pasted_content>/.test(tl)) pasted = false;
    if (tl.startsWith("```")) { style.fill(2, off, off + line.length); fence = !fence; }
    else if (inPaste && !fence) style.fill(1, off, off + line.length);
    else if (fence) style.fill(2, off, off + line.length);
    else if (tl.startsWith(">")) style.fill(1, off, off + line.length);
    off += line.length + 1;
  }
  for (const p of rec.phrases) if (p.brand && p.brand !== "Asked") for (let i = p.start; i < p.end; i++) style[i] = style[i] || 1;
  const pieces = (rec.pieces || []).slice().sort((a, b) => a.start - b.start);
  let pi = 0;
  // the engine's words (scriptt16.places): runs of letters and digits, a sign between two of them joining the word, and every
  // other sign on its own. Each is drawn as its own text, inside the run between white space that wraps as one.
  for (const m of text.matchAll(/\S+/g)) {
    const cs = m.index, ce = cs + m[0].length, st = style[cs], f = st === 2 ? F.code : st === 1 ? F.it : F.text;
    const chunk = [];
    for (const [s, e] of places(text, cs, ce)) {
      while (pi < pieces.length && pieces[pi].end <= s) pi++;
      const p = pieces[pi] && pieces[pi].start <= s && e <= pieces[pi].end ? pieces[pi] : null;
      chunk.push({ s, e, str: text.slice(s, e), piece: p, st, f, dx: tw(text.slice(cs, s), f), w: tw(text.slice(s, e), f) });
    }
    chunk.cw = tw(m[0], f); chunk.cs = cs; chunk.ce = ce;
    for (const w of chunk) words.push(w);
    chunks.push(chunk);
  }
  // chips: after the last word of each phrase that asks for something
  const after = new Map();
  for (const ph of rec.phrases) {
    if (!ph.terms.length && !ph.unresolved.length) continue;
    let last = -1;
    for (let i = 0; i < chunks.length; i++) if (chunks[i].cs >= ph.start && chunks[i].cs < ph.end) last = i;
    if (last < 0) continue;
    const list = after.get(last) || [];
    for (const t of ph.terms) { const c = opChip(t, ph); measureOp(c, rec); list.push(c); }
    for (const u of ph.unresolved) list.push(unChip(u, ph));
    after.set(last, list);
  }
  const lines = [{ items: [] }];
  let x = 0, prevEnd = 0;
  const put = (it, gap) => {
    if (x > 0 && x + gap + it.w > TW) { lines.push({ items: [] }); x = 0; gap = 0; }
    x += gap; it.x = x; it.line = lines.length - 1; lines[lines.length - 1].items.push(it); x += it.w;
  };
  const SP = tw(" ", F.text);
  chunks.forEach((ch, i) => {
    const nl = (text.slice(prevEnd, ch.cs).match(/\n/g) || []).length;
    if (i > 0 && nl) { lines.push({ items: [] }); x = 0; if (nl > 1) lines.push({ items: [] }); }
    const box = { k: "chunk", w: ch.cw };
    put(box, x > 0 ? SP : 0);
    for (const w of ch) { w.k = "w"; w.x = box.x + w.dx; w.line = box.line; lines[box.line].items.push(w); }
    for (const c of after.get(i) || []) put(c, 10);
    prevEnd = ch.ce;
  });
  L = { tw: TW, words, lines, ops: [...after.values()].flat() };
  LAY.set(rec, L);
  return L;
}
function places(text, a = 0, b = text.length) { // scriptt16.places over text[a:b]
  const out = [], an = (c) => /[\p{L}\p{N}]/u.test(c);
  let ws = null;
  for (let i = a; i < b; i++) {
    const c = text[i];
    const joins = ws != null && "-'’._".includes(c) && i + 1 < text.length && an(text[i + 1]);
    if (an(c) || joins) { if (ws == null) ws = i; continue; }
    if (ws != null) { out.push([ws, i]); ws = null; }
    if (!/\s/.test(c)) out.push([i, i + 1]);
  }
  if (ws != null) out.push([ws, b]);
  return out;
}
function slotOf(pl, rec) {
  const v = pl.v;
  if (!v) return { g: "∅", tone: "no", f: F.mono };
  if (v.hole) return { g: `▢ ${pl.declared} · ${v.reason}`, tone: "hole", f: F.mono };
  if (v.empty) return { g: `∅ ${v.empty}`, tone: "empty", f: F.mono };
  if (v.ref != null) { const r = allTerms(rec).find((x) => x.t.id === String(v.ref)); return { g: `↩ ${r ? r.t.function : v.ref}`, tone: "ref", f: F.mono }; }
  if (v.several) return { g: `[${v.several.length}]`, tone: "val", f: F.mono };
  if (v.at && v.at[0] >= 0) return { g: "⇠", tone: "val", f: F.mono };
  return { g: String(v.constant), tone: "val", f: F.mono };
}
function opChip(t, ph) {
  const parts = [{ k: "name", str: t.function + "(", f: F.monoB }];
  for (const pl of placesOf(t)) {
    parts.push({ k: "path", str: pl.path + ":", f: F.mono, pl });
    parts.push({ k: "slot", pl });
  }
  parts.push({ k: "close", str: ") → " + (t.type === "NoneType" ? "None" : t.type), f: F.mono });
  return { k: "op", t, ph, parts, w: 0, measure: true };
}
const unChip = (u, ph) => ({ k: "un", u, ph, str: `ƒ ▢ ${u.reason}`, w: tw(`ƒ ▢ ${u.reason}`, F.mono) + 12 });
function measureOp(c, rec) {
  let x = 6;
  for (const p of c.parts) {
    if (p.k === "slot") { const sl = slotOf(p.pl, rec); p.sl = sl; p.w = tw(sl.g, sl.f) + 10; }
    else p.w = tw(p.str, p.f);
    p.x = x; x += p.w + (p.k === "path" ? 3 : p.k === "slot" ? 6 : 0);
  }
  c.w = x + 6;
}

// ---------- the states ----------
// A state: the record drawn (`r`), the engine request it stands for (`change`, a /edit body), and view things.
const base = () => ({ r: S.base, change: null, scroll: S.scroll });
const cur = () => (S.staged ? { ...base(), r: S.staged.e.draft || S.base, change: S.staged.body, staged: true } : base());
function stateFor(body, extra) { return { ...base(), change: body, ...extra }; }
function withDraft(st) {
  if (!st.change) return st;
  const pre = VERD.get(bkey(st.change));
  if (pre && pre.length) return { ...st, r: S.base, change: null, refused: { body: st.change, codes: codes({ diag: pre }), diag: pre, target: st.target }, wait: false };
  const e = ask(st.change, false), v = verdict(e);
  if (v === "ok") return { ...st, r: e.draft, wait: false };
  if (v === "no") return { ...st, r: S.base, change: null, refused: { body: st.change, codes: codes(e), diag: e.diag, error: e.error, target: st.target }, wait: false };
  return { ...st, wait: true };
}
// The modifier: whatever state the spec under it chose, draw the engine's draft for it, and redraw when an answer arrives.
class Drafted extends DG.Modifier {
  constructor(ctx, innerSpec) { super(ctx, innerSpec); this.name = "drafted"; this.cache = new Map(); }
  frame(frame) {
    const r = this.inner.run(frame), st = r.dropState;
    if (!st || !st.change) { // no request here: redraw only when a verdict arrived (the rail and the marks)
      LIVE = st; paintDock(st);
      if (this.dv0 == null) this.dv0 = DV;
      if (DV === this.dv0) return r;
      let c = this.cache.get("·");
      if (!c || c.dv !== DV) { c = { dv: DV, preview: DG.renderStateReadOnly(this.ctx, st) }; this.cache.set("·", c); }
      return { ...r, preview: () => c.preview };
    }
    const pre = VERD.get(bkey(st.change));
    const e = pre && pre.length ? { k: bkey(st.change) } : ask(st.change, true);
    let c = this.cache.get(e.k);
    if (!c || c.dv !== DV) { const next = withDraft(st); c = { dv: DV, next, preview: DG.renderStateReadOnly(this.ctx, next) }; this.cache.set(e.k, c); }
    LIVE = c.next; paintDock(c.next);
    return { ...r, preview: () => c.preview, dropState: c.next };
  }
}
const drafted = DG.modifier(Drafted);
let LIVE = null;

// ---------- what a held thing can do: each option is a target element and an engine request ----------
let DRAWN = new Map(); // id -> box, from the last drawing of the current state
const visible = (id) => DRAWN.has(id);
function piecesVisible() { return [...DRAWN.keys()].filter((k) => k.startsWith("pc-")).map((k) => DRAWN.get(k).piece).filter(Boolean); }
const retag = (a, b, kind) => ({ path: "kind", at: [a, b], value: kind });
function wordsValue(p, pl) { // the words as their own kind when it is a type of the world, else as the place's declared type; the engine checks
  const ty = p.kind && p.kind !== "(none)" && world().types[inner(p.kind)] ? p.kind : inner(pl.declared);
  return { constant: S.base.text.slice(p.start, p.end), type: ty, at: [p.start, p.end] };
}
function allPlaces(rec) { return allTerms(rec).flatMap(({ t }) => placesOf(t)); }
function placeOptions(valueOf, skip) {
  const out = [];
  for (const pl of allPlaces(S.base)) {
    if (skip && skip(pl)) continue;
    const v = valueOf(pl);
    if (v === undefined) continue;
    const body = { number: +pl.t.id, path: pl.path, value: v }, id = "pl-" + pkey(pl.t, pl.path);
    out.push({ target: id, body, pl, open: !pl.v || !!pl.v.hole });
  }
  return out;
}
function options(th) {
  const P = piecesVisible(), out = [];
  const onPieces = (kindOf, skip) => { for (const q of P) { if (skip && skip(q)) continue; const k = kindOf(q); if (k) out.push({ target: "pc-" + q.start, body: retag(q.start, q.end, k), piece: q }); } };
  let places = [];
  switch (th.t) {
    case "piece": {
      const p = th.p, ph = S.base.phrases.find((x) => x.start <= p.start && p.end <= x.end);
      out.push({ target: "pc-" + p.start, body: null, self: true });
      if (p.kind != null) for (const q of P) {
        if (q.start === p.start) continue;
        const near = ph && ph.start <= q.start && q.end <= ph.end && !(S.base.pieces || []).some((o) => o !== p && o !== q && o.start >= Math.min(p.end, q.end) && o.end <= Math.max(p.start, q.start));
        out.push({ target: "pc-" + q.start, body: near ? retag(Math.min(p.start, q.start), Math.max(p.end, q.end), p.kind) : retag(q.start, q.end, p.kind), piece: q });
      }
      places = placeOptions((pl) => wordsValue(p, pl));
      break;
    }
    case "type": onPieces((q) => (q.kind === th.name ? null : th.name)); break;
    case "con": onPieces((q) => (cat(q.kind) === "type" ? `${th.con}[${q.kind}]` : null)); break;
    case "opt": onPieces((q) => (q.kind === th.kind ? null : th.kind)); break;
    case "fn": {
      onPieces((q) => (q.kind === th.name ? null : th.name));
      const [param, tree] = world().functions[th.name].parameters[0] || [];
      if (param) for (const ph of S.base.phrases) for (const u of ph.unresolved) {
        const id = "un-" + u.id;
        if (!visible(id) && !RAIL_IDS.has(id)) continue;
        const a = ph.start + (S.base.text.slice(ph.start, ph.end).length - S.base.text.slice(ph.start, ph.end).trimStart().length), said = S.base.text.slice(a, ph.end).trimEnd();
        out.push({ target: id, body: { number: null, path: `${th.name}.${param}`, value: { constant: said, type: inner(tname(tree)), at: [a, a + said.length] } }, un: u });
      }
      break;
    }
    case "member": places = placeOptions(() => ({ constant: th.words, type: th.type, at: [-1, -1] })); break;
    case "op": places = placeOptions(() => ({ ref: th.term.id }), (pl) => pl.t.id === th.term.id); break;
    case "val": places = placeOptions(() => th.pl.v, (pl) => pl.t.id === th.pl.t.id && pl.path === th.pl.path); break;
  }
  newHold(); // the verdicts are asked when a drag really starts (status) or a key picks the thing up (holdOf), not on a click
  return { out, places };
}
function far(th) {
  if (th.t === "piece" && th.p.kind !== "(none)") return retag(th.p.start, th.p.end, "(none)");
  if (th.t === "val") return { number: +th.pl.t.id, path: th.pl.path, value: { hole: th.pl.declared, reason: "cleared" } };
  return null;
}
// places brought near: every place of the reading that the engine has not refused, in a rail at the bottom of the view
let RAIL_IDS = new Set();
// The rail: while a thing is held, the places of the whole reading that the engine accepts it in, ✓ first, on up to two rows at
// the bottom of the view; the refused ones are counted (✕ n), not offered. It is laid out once the engine has answered for every
// place (one /edits request), and stays put while the pointer moves.
const RAILW = () => X0 + TW + 40;
const known = (th) => !!th && !!th.places && th.places.every((o) => vOf(o.body) !== "wait");
function railItems() {
  const held = HELD || (S.hold && S.hold.th);
  if (!held || !held.places || !held.places.length) return [];
  if (held.rail) return held.rail.map((r) => (r.o ? { ...r, v: vOf(r.o.body) } : r));
  const out = [], y0 = BH - 44;
  if (!known(held)) return [{ id: "rl-wait", label: "… " + held.places.length, x: X0, y: y0, w: tw("… " + held.places.length, F.mono) + 16, v: "wait", info: true }];
  const okP = held.places.filter((o) => vOf(o.body) === "ok").sort((a, b) => b.open - a.open), noN = held.places.length - okP.length;
  // every accepted place, each named by its operation (#id) and declared type; rows grow upward, up to half the view
  const maxRows = Math.max(2, Math.floor((BH * 0.5) / 32));
  let x = X0, row = 0;
  const tail = `✕ ${noN}`, tw0 = tw(tail, F.mono) + 16;
  for (const o of okP) {
    const label = `${o.pl.t.function} #${o.pl.t.id}.${o.pl.path} : ${o.pl.declared}`, w = tw("✓ " + label, F.mono) + 16;
    if (x + w > RAILW()) { if (row + 1 >= maxRows) break; row++; x = X0; }
    out.push({ id: "rl-" + pkey(o.pl.t, o.pl.path), o, label, x, row, w, v: "ok" });
    x += w + 6;
  }
  const more = okP.length - out.length;
  const info = (more ? `+${more}  ` : "") + tail;
  if (x + tw0 > RAILW() && row + 1 < maxRows) { row++; x = X0; }
  out.push({ id: "rl-info", label: info, x: Math.min(x, RAILW() - tw(info, F.mono) - 16), row, w: tw(info, F.mono) + 16, v: "no", info: true });
  for (const r of out) r.y = y0 - (row - r.row) * 32; // the first row on top, the last at the bottom of the view
  return out;
}
function spec(th, d) {
  try { return spec1(th, d); } catch (e) { console.error("spec", e && e.stack); return d.fixed(base()); }
}
function spec1(th, d) {
  const start = cur();
  HELD = th; RAIL_IDS = new Set();
  const { out, places } = options(th);
  th.places = places; delete th.rail;
  th.retags = out.filter((o) => o.body && o.body.path === "kind");
  const fb = far(th), farState = fb ? stateFor(fb, { pull: true }) : base();
  // the targets are built again once the engine has answered for every place (d.reactTo): refused places stop being targets
  const build = () => {
    const drawnNow = idsOf(draggable({ state: start, d, draggedId: null })); // DRAWN must be the state the drag starts from: a link opened by the same press, or a staged change, reflows the text
    delete th.rail; th.rail = railItems();
    RAIL_IDS = new Set(th.rail.filter((r) => !r.info).map((r) => r.id));
    const segs = (o) => (o.target.startsWith("pc-") ? [...DRAWN.entries()].filter(([, b]) => b.seg && "pc-" + b.start === o.target).map(([id]) => ({ ...o, target: id })) : [o]);
    const railTop = th.rail.length ? Math.min(...th.rail.map((r) => r.y)) - 8 : Infinity; // what lies under the rail is hidden, so not a target
    const clear = (id) => { const b = DRAWN.get(id); return b && b.y + (b.h || 0) < railTop; };
    const opts = [...th.rail.filter((r) => !r.info).map((r) => ({ ...r.o, target: r.id })), ...places.filter((o) => clear(o.target) && vOf(o.body) !== "no"), ...out.flatMap(segs).filter((o) => (o.target.startsWith("pt-") ? clear(o.target) : visible(o.target)))];
    // a target missing from the start drawing would stop the renderer: only targets drawn now
    const targets = opts.filter((o) => drawnNow.has(o.target)).map((o) => d.dropTarget(o.target, o.body ? stateFor(o.body, { target: o.target }) : base(), { boundsState: start }));
    return targets.length ? d.closest(targets).whenFar(farState) : d.fixed(farState);
  };
  return d.reactTo(() => known(th), build).with(drafted()).withFloating();
}
function idsOf(el, out = new Set()) { // every id in a drawing (a React element tree)
  if (!el || typeof el !== "object") return out;
  if (Array.isArray(el)) { for (const c of el) idsOf(c, out); return out; }
  if (el.props) { if (el.props.id != null) out.add(el.props.id); idsOf(el.props.children, out); }
  return out;
}
// widen or narrow a link: the handle snaps to each word boundary near it; each boundary is a retag
function handleStates(p, side) {
  const L = layout(S.base), ws = L.words, i0 = ws.findIndex((w) => w.s === p.start), i1 = ws.findIndex((w) => w.e === p.end);
  const out = [];
  if (i0 < 0 || i1 < 0) return out;
  for (let j = Math.max(0, (side === "e" ? i0 : i0 - 12)); j <= Math.min(ws.length - 1, side === "e" ? i1 + 12 : i1); j++) {
    let body = null, s = p.start, e = p.end;
    if (side === "e") { e = ws[j].e; if (e > p.end) body = retag(p.start, e, p.kind); else if (e < p.end) body = retag(ws[j + 1].s, p.end, "(none)"); }
    else { s = ws[j].s; if (s < p.start) body = retag(s, p.end, p.kind); else if (s > p.start) body = retag(p.start, ws[j - 1].e, "(none)"); }
    out.push({ ...base(), change: body, handle: { p: p.start, side, at: side === "e" ? e : s }, prop: { s, e, kind: p.kind } });
  }
  return out;
}
function handleSpec(p, side, d) {
  HELD = { t: "handle", p };
  const st = handleStates(p, side);
  return d.closest(st).with(drafted());
}

// ---------- drawing ----------
// Dragology blends a state into the next one (springs, d.between). Children are paired by dragologyKey, so each child gets a key
// that changes whenever something that cannot be blended changes (its type, font, dash, text): a retagged word's label fades
// out and the new one fades in, instead of being blended.
const NOKEY = new Set(["transform", "fill", "stroke", "opacity", "width", "height", "rx", "r", "strokeWidth", "strokeOpacity", "fillOpacity", "d", "id", "className", "role", "tabIndex"]);
function sig(c) {
  let s = typeof c.type === "string" ? c.type : "c";
  for (const k in c.props) {
    const v = c.props[k];
    if (k === "children") { if (typeof v === "string" || typeof v === "number") s += "|" + v; else if (Array.isArray(v) && v.every((x) => typeof x === "string")) s += "|" + v.join(""); continue; }
    if (NOKEY.has(k) || k.startsWith("on") || k.startsWith("dragology") || k.startsWith("data-") || v == null) continue;
    s += "|" + k + "=" + (typeof v === "object" ? JSON.stringify(v) : v);
  }
  return s;
}
function hash(s) { let x = 2166136261; for (let i = 0; i < s.length; i++) { x ^= s.charCodeAt(i); x = Math.imul(x, 16777619); } return "k" + (x >>> 0).toString(36) + s.length.toString(36); }
function keyAll(el) {
  if (!el || typeof el !== "object" || !el.props) return el;
  const ch = el.props.children;
  if (ch == null || typeof ch !== "object") return el;
  const arr = (Array.isArray(ch) ? ch.flat(Infinity) : [ch]).filter((c) => c != null && c !== false);
  if (arr.every((c) => typeof c !== "object")) return el;
  const seen = new Map();
  const out = arr.map((c) => {
    if (!c || typeof c !== "object" || !c.props) return c;
    c = keyAll(c);
    if (c.props.id != null || c.props.dragologyKey != null) return c;
    const k = hash(sig(c)), n = seen.get(k) || 0;
    seen.set(k, n + 1);
    return React.cloneElement(c, { dragologyKey: k + "-" + n });
  });
  return React.cloneElement(el, { children: out });
}
const txt = (x, y, s, f, fill, extra = {}) => h("text", { transform: translate(x, y), style: { font: f }, fill, ...extra }, s);
let FOC = [];
function draggable({ state: st, d, draggedId }) {
  const display = (!st.change || st.staged) && !st.prop && !st.refused && !st.pull; // the base, or the staged change: what is on screen
  const rec = st.r, L = layout(rec), scroll = st.scroll ?? S.scroll, n = visLines();
  const first = Math.max(0, Math.floor(scroll)), last = Math.min(L.lines.length - 1, first + n);
  const Y = (li) => TOP + (li - scroll) * LH;
  const drawn = new Map(), foc = [];
  const changed = st.change ? new Set((rec.pieces || []).filter((p) => !(S.base.pieces || []).some((b) => b.start === p.start && b.end === p.end && b.kind === p.kind)).map((p) => p.start)) : new Set();
  const openP = S.open && S.open.t === "piece" ? S.open.p : null;
  const bg = [], words = [], links = [], ops = [], over = [];
  // the words, once, in reading order
  const segs = new Map();
  for (let li = first; li <= last; li++) {
    const line = L.lines[li], y = Y(li);
    for (const it of line.items) {
      if (it.k === "w") {
        if (it.st) bg.push(h("rect", { transform: translate(X0 + it.x - 3, y + 12), width: it.w + 6 + 4, height: 26, fill: C.paste }));
        words.push(txt(X0 + it.x, y + 31, it.str, it.f, C.ink, { "data-s": it.s, "data-e": it.e, className: "w" }));
        if (it.piece) { const k = it.piece.start; const a = segs.get(k) || { p: it.piece, parts: [] }; const lp = a.parts[a.parts.length - 1]; if (lp && lp.li === li) lp.x1 = X0 + it.x + it.w; else a.parts.push({ li, y, x0: X0 + it.x, x1: X0 + it.x + it.w }); segs.set(k, a); }
      }
    }
  }
  // the links: one per piece, piped to its kind
  const labelEnd = new Map();
  for (const [k, a] of segs) {
    const p = a.p, col = colorOf(p.kind), c = cat(p.kind), id = "pc-" + k, isOpen = openP && openP.start === p.start, ch = changed.has(p.start);
    const kids = [];
    a.parts.forEach((s, i) => { kids.push(h("rect", { id: `pt-${k}-${i}`, transform: translate(s.x0 - 2, s.y + 2), width: s.x1 - s.x0 + 4, height: 38, fill: "transparent", pointerEvents: "none" })); drawn.set(`pt-${k}-${i}`, { seg: true, start: k, x: s.x0, y: s.y, w: s.x1 - s.x0, h: 40 }); });
    for (const s of a.parts) {
      if (ch) bg.push(h("rect", { transform: translate(s.x0 - 3, s.y + 12), width: s.x1 - s.x0 + 6, height: 26, rx: 3, fill: C.accBg }));
      kids.push(h("rect", { transform: translate(s.x0 - 2, s.y + 2), width: s.x1 - s.x0 + 4, height: 38, fill: "transparent" }));
      if (c !== "none") kids.push(h("rect", { transform: translate(s.x0, s.y + 35), width: s.x1 - s.x0, height: p.sure || p.by === "user" ? 2 : 1.25, fill: ch ? C.acc : col, opacity: c === "null" ? 0.9 : 1, ...(c === "con" || c === "null" ? { style: { strokeDasharray: "3 2" } } : {}) }));
      else kids.push(h("rect", { transform: translate(s.x0, s.y + 36), width: s.x1 - s.x0, height: 0.75, fill: C.faint, opacity: 0.6 }));
    }
    const s0 = a.parts[0], label = p.kind == null ? "null" : p.kind;
    const lw = tw(label, F.small);
    const room = (labelEnd.get(s0.li) ?? -1e9) <= s0.x0 - 4;
    if (c !== "none" && room && (lw <= s0.x1 - s0.x0 + 14 || isOpen || ch || draggedId === id)) { labelEnd.set(s0.li, s0.x0 + lw); kids.push(txt(s0.x0, s0.y + 11, label, F.small, ch ? C.acc : col, { fontWeight: p.by === "user" ? 700 : 400 })); }
    else if (c !== "none") kids.push(h("circle", { transform: translate(s0.x0 + 2, s0.y + 8), r: 2, fill: col }));
    if (draggedId === id) { const lw2 = tw(label, F.mono) + 12; kids.push(h("g", { transform: translate(s0.x0, s0.y - 6), opacity: 0.7 }, h("rect", { width: lw2, height: 18, rx: 9, fill: C.card, stroke: col, strokeWidth: 1.25 }), txt(6, 13, label, F.mono, col))); }
    const hh = HELD || (S.hold && S.hold.th), rt = hh && hh.retags && hh.retags.find((o) => o.piece && o.piece.start === p.start), rv = rt ? vOf(rt.body) : null;
    if (rv && rv !== "wait" && draggedId !== id) for (const s of a.parts) kids.push(h("rect", { transform: translate(s.x0 - 3, s.y + 10), width: s.x1 - s.x0 + 6, height: 30, rx: 4, fill: "none", stroke: rv === "ok" ? C.fn : C.no, strokeWidth: 1, strokeDasharray: "2 2", opacity: 0.8 }));
    if (isOpen) for (const s of a.parts) kids.push(h("rect", { transform: translate(s.x0 - 3, s.y + 1), width: s.x1 - s.x0 + 6, height: 40, rx: 4, fill: "none", stroke: col, strokeWidth: 1.5 }));
    const th = { t: "piece", p };
    kids.unshift(h("title", null, `${label} | ${clip(rec.text.slice(p.start, p.end))}`));
    links.push(h("g", { id, "data-kind": label, "data-start": p.start, "data-end": p.end, role: "link", "data-label": label, className: "pc", dragologyZIndex: draggedId === id ? "/1" : false,
      dragologyOnDrag: () => spec(th, d), onClick: () => openThing(th) }, ...kids));
    drawn.set(id, { piece: p, x: s0.x0, y: s0.y, w: s0.x1 - s0.x0, h: 40 });
    foc.push({ id, th, zone: "text", x: s0.x0, li: s0.li });
  }
  // a proposal the engine has not answered yet: drawn dashed, with its kind
  if (st.prop && st.wait) {
    for (let li = first; li <= last; li++) for (const it of L.lines[li].items) if (it.k === "w" && it.s >= st.prop.s && it.e <= st.prop.e) over.push(h("rect", { transform: translate(X0 + it.x - 2, Y(li) + 12), width: it.w + 6, height: 27, fill: "none", stroke: C.acc, strokeWidth: 1, strokeDasharray: "3 2" }));
  }
  // handles of the open link
  const hp = openP && (S.base.pieces || []).find((p) => p.start === openP.start);
  if (hp && !st.refused) {
    const hl = st.handle && st.handle.p === hp.start ? st.handle : null;
    for (const side of ["s", "e"]) {
      const at = hl && hl.side === side ? hl.at : side === "s" ? hp.start : hp.end;
      let it = null, li0 = -1;
      for (let li = first; li <= last && !it; li++) for (const x of L.lines[li].items) if (x.k === "w" && (side === "s" ? x.s === at : x.e === at)) { it = x; li0 = li; break; }
      if (!it) continue;
      const hx = X0 + it.x + (side === "e" ? it.w + 2 : -4), id = "hd-" + side;
      over.push(h("g", { id, transform: translate(hx, Y(li0) + 6), role: "slider", "data-label": side === "s" ? "start" : "end", dragologyOnDrag: () => handleSpec(hp, side, d) },
        h("rect", { transform: translate(-5, 0), width: 12, height: 36, fill: "transparent" }), h("rect", { width: 2.5, height: 34, rx: 1, fill: C.acc }), h("circle", { transform: translate(1.25, side === "s" ? 0 : 34), r: 3.5, fill: C.acc })));
      drawn.set(id, { x: hx, y: Y(li0), w: 4, h: 36 });
    }
  }
  // function spans: a bracket under the phrase, and the function with its places after it
  const terms = allTerms(rec);
  for (let li = first; li <= last; li++) {
    const y = Y(li);
    for (const it of L.lines[li].items) {
      if (it.k === "op") {
        ops.push(drawOp(it, X0 + it.x, y, rec, d, draggedId, drawn, foc, li));
      } else if (it.k === "un") {
        const id = "un-" + it.u.id, x = X0 + it.x;
        const pr = st.refused && st.refused.target === id;
        ops.push(h("g", { id, transform: translate(x, y + 14), className: "un", role: "button", "data-label": `ƒ ${it.u.reason}`, onClick: () => openThing({ t: "un", u: it.u, ph: it.ph }) },
          h("rect", { width: it.w, height: 24, rx: 4, fill: pr ? C.noBg : C.card, stroke: pr ? C.no : C.fn, strokeDasharray: "4 3" }), txt(6, 16, it.str, F.mono, C.fn)));
        drawn.set(id, { x, y: y + 14, w: it.w, h: 24 });
        foc.push({ id, th: { t: "un", u: it.u, ph: it.ph }, zone: "text", x, li });
      }
    }
  }
  for (const { t, p } of terms) { // the bracket of each operation under the words of its phrase
    for (let li = first; li <= last; li++) {
      const ws = L.lines[li].items.filter((x) => x.k === "w" && x.s >= p.start && x.e <= p.end);
      if (!ws.length) continue;
      const a = X0 + ws[0].x, b = X0 + ws[ws.length - 1].x + ws[ws.length - 1].w, y = Y(li) + 41;
      bg.push(h("rect", { transform: translate(a, y), width: b - a, height: 1.5, fill: C.fn, opacity: 0.55 }));
      if (ws[0].s <= p.start + 2) bg.push(h("rect", { transform: translate(a, y - 4), width: 1.5, height: 5.5, fill: C.fn, opacity: 0.55 }));
    }
  }
  // the page of the open thing, or the world
  const page = drawPage(st, d, draggedId, drawn, foc);
  // the rail: places that take what is held, brought near
  const rail = [];
  const ri = railItems();
  if (ri.length) {
    const top = Math.min(...ri.map((r) => r.y));
    rail.push(h("rect", { transform: translate(0, top - 8), width: X0 + TW + 48, height: BH - top + 8, fill: C.card, opacity: 0.97 }));
    rail.push(h("rect", { transform: translate(0, top - 8), width: X0 + TW + 48, height: 1, fill: C.rule }));
    for (const r of ri) {
      const hit = st.target === r.id || (S.hold && S.hold.opts[S.hold.i] && S.hold.opts[S.hold.i].target === r.id);
      const glyph = r.info ? "" : ({ ok: "✓ ", no: "✕ ", wait: "… " })[r.v];
      const name = r.info ? r.label : `${r.label} ${r.v === "ok" ? "✓" : r.v === "no" ? "✕" : "…"}`;
      rail.push(h("g", { id: r.id, transform: translate(r.x, r.y), className: "rail", role: r.info ? "note" : "button", "data-verdict": r.v, "data-open": r.o && r.o.open ? "1" : "0" },
        h("title", null, name),
        h("rect", { width: r.w, height: 28, rx: 5, fill: r.info ? "none" : r.v === "no" ? C.noBg : hit ? C.accBg : r.o && r.o.open ? C.card : C.tint, stroke: r.info ? C.rule : r.v === "no" ? C.no : hit ? C.acc : C.fn, strokeDasharray: r.o && r.o.open ? "4 3" : "", strokeWidth: 1.25 }),
        txt(8, 18, glyph + r.label, F.mono, r.v === "ok" ? C.fn : r.v === "no" ? C.no : C.mute)));
      drawn.set(r.id, { x: r.x, y: r.y, w: r.w, h: 28 });
    }
  }
  // the keyboard's target
  if (S.hold && display === false) {
    const o = S.hold.opts[S.hold.i], b = o && DRAWN.get(o.target);
    if (b) over.push(h("rect", { transform: translate(b.x - 4, b.y - 1), width: b.w + 8, height: b.h + 2, rx: 5, fill: "none", stroke: C.acc, strokeWidth: 2 }));
  }
  const fb = S.focus && (drawn.get(S.focus) || DRAWN.get(S.focus));
  if (fb && !draggedId) over.push(h("rect", { transform: translate(fb.x - 4, fb.y - 2), width: fb.w + 8, height: fb.h + 4, rx: 5, fill: "none", stroke: C.acc, strokeWidth: 2, strokeDasharray: "2 2" }));
  // the scroll bar, dragged through the library (d.vary on the scroll position)
  const total = Math.max(1, L.lines.length - n), trackH = BH - TOP * 2 - 52;
  const thumbH = Math.max(30, trackH * Math.min(1, n / Math.max(1, L.lines.length)));
  const sb = L.lines.length > n ? h("g", { id: "sb", transform: translate(X0 + TW + 30, TOP + (trackH - thumbH) * Math.min(1, Math.max(0, scroll / total))),
    dragologyOnDrag: () => d.vary({ ...st, scroll }, DG.param("scroll"), { constraint: (s) => DG.inOrder([0, s.scroll, total]) }) },
    h("rect", { transform: translate(-5, 0), width: 14, height: thumbH, fill: "transparent" }), h("rect", { width: 4, height: thumbH, rx: 2, fill: C.rule })) : null;
  if (display) { DRAWN = drawn; FOC = foc; }
  return keyAll(h("g", { id: "root" },
    h("rect", { id: "paper", width: BW, height: BH, fill: C.bg }),
    h("g", { id: "bg" }, ...bg), h("g", { id: "words" }, ...words), h("g", { id: "ops" }, ...ops), h("g", { id: "links" }, ...links),
    h("g", { id: "page-" + pageKey() }, ...page), h("g", { id: "over" }, ...over), sb, rail.length ? h("g", { id: "railg", dragologyZIndex: 10 }, ...rail) : null));
}
function pageKey() { const o = S.open; if (!o) return "world"; return o.t + "-" + (o.p ? o.p.start + "-" + o.p.end : o.name || (o.term ? o.term.id : "") || (o.pl ? pkey(o.pl.t, o.pl.path) : "") || (o.u ? o.u.id : "")).toString().replace(/\W/g, "_"); }
function drawOp(c, x, y, rec, d, draggedId, drawn, foc, li) {
  const t = c.t, id = "op-" + t.id, kids = [], j = t.judgments || {};
  kids.push(h("rect", { width: c.w, height: 26, rx: 4, fill: C.fnBg, opacity: 0.6 }));
  for (const p of c.parts) {
    if (p.k === "slot") {
      const pid = "pl-" + pkey(t, p.pl.path), sl = p.sl, hole = sl.tone === "hole" || sl.tone === "no";
      const hh = HELD || (S.hold && S.hold.th), ho = hh && hh.places && hh.places.find((o) => o.target === pid), heldV = ho ? vOf(ho.body) : null; // the engine's verdict for what is held
      const th = { t: "val", pl: p.pl };
      kids.push(h("g", { id: pid, transform: translate(p.x, 3), role: "button", "data-label": `${t.function}.${p.pl.path}`, "data-place": `${t.id}.${p.pl.path}`, "data-op": t.id, "data-hole": hole ? "1" : "0",
        ...(sl.tone !== "hole" && sl.tone !== "no" ? { dragologyOnDrag: () => spec(th, d), dragologyZIndex: draggedId === pid ? "/1" : false } : {}),
        onClick: (ev) => { ev.stopPropagation(); openThing({ t: "place", pl: p.pl }); } },
        h("title", null, `${t.function}.${p.pl.path} : ${p.pl.declared} ${sl.g}` + (heldV ? " " + ({ ok: "✓", no: "✕", wait: "…" })[heldV] : "")),
        heldV && heldV !== "wait" ? txt(p.w - 9, -3, heldV === "ok" ? "✓" : "✕", F.monoB, heldV === "ok" ? C.fn : C.no) : null,
        h("rect", { width: p.w, height: 20, rx: 3, fill: heldV === "ok" ? C.fnBg : hole ? C.card : C.bg, stroke: heldV === "ok" ? C.fn : heldV === "no" ? C.no : hole ? C.no : C.type, strokeWidth: heldV === "ok" ? 2 : 1, strokeDasharray: hole ? "3 2" : "" }),
        txt(5, 14, sl.g, sl.f, hole ? C.no : sl.tone === "ref" ? C.fn : C.type)));
      drawn.set(pid, { x: x + p.x, y: y + 17, w: p.w, h: 20, pl: p.pl });
      foc.push({ id: pid, th: { t: "place", pl: p.pl }, drag: th, zone: "text", x: x + p.x, li });
    } else kids.push(txt(p.x, 17, p.str, p.f, p.k === "name" ? C.fn : C.mute));
  }
  kids.unshift(h("title", null, `${t.function} #${t.id} → ${t.type}` + (j.complete === false ? " ● complete ✕" : "")));
  if (j.pending || j.deferred) kids.push(txt(c.w + 3, 10, j.pending ? "⧗" : "⏲", F.small, C.mute));
  if (j.complete === false) kids.push(h("circle", { transform: translate(c.w - 2, 2), r: 3, fill: C.no }));
  if (draggedId === id) { // held: the result itself, not the whole operation
    const lab = `↩ ${t.function}`, w = tw(lab, F.monoB) + 14;
    return h("g", { id, transform: translate(x, y + 14), className: "op", role: "button", "data-label": t.function, "data-op": t.id, dragologyOnDrag: () => spec({ t: "op", term: t }, d), dragologyZIndex: "/1" },
      h("rect", { width: w, height: 22, rx: 11, fill: C.card, stroke: C.fn, strokeWidth: 1.25 }), txt(7, 15, lab, F.monoB, C.fn));
  }
  drawn.set(id, { x, y: y + 14, w: c.w, h: 26, t });
  foc.push({ id, th: { t: "op", term: t }, zone: "text", x, li });
  return h("g", { id, transform: translate(x, y + 14), className: "op", role: "button", "data-label": t.function, "data-op": t.id, dragologyOnDrag: () => spec({ t: "op", term: t }, d), dragologyZIndex: draggedId === id ? "/1" : false, onClick: () => openThing({ t: "op", term: t }) }, ...kids);
}

// ---------- the page of a thing (the right column): its world page and its d1 data ----------
function drawPage(st, d, draggedId, drawn, foc) {
  const els = [], x0 = PX, w = PW;
  let y = TOP + 4 - S.pscroll;
  const head = (s, col) => { els.push(txt(x0, y + 12, s, F.head, col || C.mute)); y += 22; };
  const chipEl = (id, x, label, col, bgc, th, opts = {}) => {
    const cw = tw(label, opts.f || F.mono) + 14;
    const g = h("g", { id, transform: translate(x, y), role: "button", "data-label": label, className: "chip", dragologyZIndex: draggedId === id ? "/1" : false, opacity: draggedId === id ? 0.6 : 1,
      ...(opts.drag !== false && th && th.t !== "none" ? { dragologyOnDrag: () => spec(th, d) } : {}), onClick: () => opts.open ? openThing(opts.open) : th && openThing(th) },
      h("rect", { width: cw, height: 22, rx: 4, fill: bgc || C.card, stroke: col, strokeWidth: 1, strokeDasharray: opts.dash ? "3 2" : "" }), txt(7, 15, label, opts.f || F.mono, col));
    drawn.set(id, { x, y, w: cw, h: 22 });
    foc.push({ id, th: opts.open || th, drag: th, zone: "page", x, li: y });
    els.push(g);
    return cw;
  };
  const row = (items) => { let x = x0; for (const it of items) { if (x + tw(it[1], F.mono) + 14 > x0 + w && x > x0) { x = x0; y += 28; } x += chipEl(...[it[0], x, ...it.slice(1)]) + 6; } y += 30; };
  const para = (s, col, f = F.mono) => { for (const ln of wrap(s, f, w)) { els.push(txt(x0, y + 12, ln, f, col || C.mute)); y += 16; } y += 6; };
  const typeChip = (name, idp) => [idp + "-" + name.replace(/\W/g, "_"), name, colorOf(name), cat(name) === "con" ? C.conBg : C.typeBg, cat(name) === "fn" ? { t: "fn", name } : { t: "type", name }, { dash: cat(name) === "con", open: { t: cat(name) === "fn" ? "fn" : "type", name } }];
  const o = S.open;
  if (!o) return els; // no permanent world panel: the world is reached from the thing in hand
  // the link target
  const target = o.t === "piece" ? o.p.kind : o.t === "type" || o.t === "fn" ? o.name : o.t === "op" ? o.term.function : o.t === "place" ? o.pl.declared : o.t === "un" ? null : null;
  els.push(h("g", { id: "pg-close", transform: translate(x0 + w - 18, y), role: "button", "data-label": "close", onClick: () => openThing(null) }, h("rect", { width: 18, height: 18, fill: "transparent" }), txt(4, 13, "×", F.head, C.mute)));
  if (o.t === "un") {
    head(`ƒ ▢ · ${o.u.reason}`, C.fn);
    const ds = S.base.decisions.filter((x) => String(x.operation) === String(o.u.id));
    drawDecisions(ds, els, () => y, (v) => (y = v), para);
    head("ƒ", C.fn);
    row(Object.keys(world().functions).map((f) => ["pg-f-" + f, f, C.fn, C.fnBg, { t: "fn", name: f }, { open: { t: "fn", name: f } }]));
    return els;
  }
  if (target != null && target !== "(none)") {
    if (isFn(target)) drawFnPage(target, head, row, para, typeChip);
    else drawTypePage(target, head, row, para, typeChip);
  } else if (target === "(none)") head("(none)", C.mute);
  // the d1 data for what is open
  if (o.t === "piece") {
    head(`share ${o.p.share == null ? "—" : o.p.share.toFixed(2)} · sure ${o.p.sure} · by ${o.p.by}`, C.mute);
    const kw = kindWords(S.base).filter((k) => k.s >= o.p.start && k.e <= o.p.end);
    if (kw.length) {
      head("d1 · kind", C.ink);
      for (const k of kw) {
        els.push(txt(x0, y + 12, `${k.w}  “${k.str || S.base.text.slice(k.s, k.e)}”`, F.mono, C.mute)); y += 18;
        const pr = Object.entries((k.a && k.a.probabilities) || {}).sort((a, b) => b[1] - a[1]);
        const show = S.more[k.s] ? pr : pr.slice(0, 4);
        for (const [opt, pv] of show) {
          const id = `pg-o-${k.s}-${opt.replace(/\W/g, "_")}`, col = colorOf(opt), bw = Math.max(2, (w - 150) * pv), chosen = k.a && k.a.value === opt;
          els.push(h("g", { id, transform: translate(x0, y), role: "button", "data-label": `${opt} ${pv.toFixed(2)}`, dragologyOnDrag: () => spec({ t: "opt", kind: opt }, d), dragologyZIndex: draggedId === id ? "/1" : false,
            onClick: () => stageBody(retag(o.p.start, o.p.end, opt)) },
            h("rect", { width: w, height: 18, fill: "transparent" }), txt(0, 13, (chosen ? "● " : "  ") + opt, F.mono, col), h("rect", { transform: translate(120, 5), width: bw, height: 8, rx: 2, fill: col, opacity: 0.7 }), txt(124 + bw, 13, pv.toFixed(2), F.small, C.mute)));
          drawn.set(id, { x: x0, y, w, h: 18 }); foc.push({ id, th: { t: "opt", kind: opt }, zone: "page", x: x0, li: y, act: () => stageBody(retag(o.p.start, o.p.end, opt)) });
          y += 19;
        }
        if (pr.length > 4) { const id = `pg-x-${k.s}`; els.push(h("g", { id, transform: translate(x0, y), role: "button", onClick: () => { S.more[k.s] = !S.more[k.s]; paint(); } }, h("rect", { width: 60, height: 16, fill: "transparent" }), txt(0, 12, S.more[k.s] ? "−" : `+${pr.length - 4}`, F.mono, C.mute))); drawn.set(id, { x: x0, y, w: 60, h: 16 }); foc.push({ id, zone: "page", x: x0, li: y, act: () => { S.more[k.s] = !S.more[k.s]; paint(); } }); y += 18; }
        y += 4;
      }
      const d0 = kw[0].d, sid = `pg-st-${d0.phrase[0]}`;
      els.push(h("g", { id: sid, transform: translate(x0, y), role: "button", onClick: () => { S.more["st" + d0.phrase[0]] = !S.more["st" + d0.phrase[0]]; paint(); } }, h("rect", { width: 80, height: 16, fill: "transparent" }), txt(0, 12, (S.more["st" + d0.phrase[0]] ? "▾" : "▸") + " state", F.mono, C.mute)));
      drawn.set(sid, { x: x0, y, w: 80, h: 16 }); foc.push({ id: sid, zone: "page", x: x0, li: y, act: () => { S.more["st" + d0.phrase[0]] = !S.more["st" + d0.phrase[0]]; paint(); } });
      y += 20;
      if (S.more["st" + d0.phrase[0]]) { para(d0.state, C.mute); para(kw[0].q.instructions, C.mute); }
    }
  }
  if (o.t === "op" || o.t === "place") {
    const t = o.t === "op" ? o.term : o.pl.t, j = t.judgments || {};
    head(`#${t.id} · ` + ["valid", "complete", "pending", "deferred", "ready"].map((k) => `${k} ${j[k] ? "✓" : "✕"}`).join("  "), C.mute);
    for (const pl of o.t === "op" ? placesOf(t) : [o.pl]) {
      const sl = slotOf(pl, S.base);
      head(`${t.function}.${pl.path} : ${pl.declared}   ${sl.g}`, C.ink);
      if (pl.v && pl.v.at && pl.v.at[0] >= 0) para(`at ${pl.v.at.join("–")}`, C.mute);
      drawDecisions(S.base.decisions.filter((x) => String(x.operation) === String(t.id) && (x.path == null || x.path === pl.path)), els, () => y, (v) => (y = v), para);
    }
  }
  // world editing is not built in the engine: its place, marked
  els.push(h("g", { id: "pg-edit", transform: translate(x0, y + 4), "data-label": "world edit ⊘" }, h("rect", { width: 70, height: 22, rx: 4, fill: "none", stroke: C.faint, strokeDasharray: "2 3" }), txt(8, 15, "＋ ⊘", F.mono, C.mute)));
  return els;
  function drawTypePage(name, head, row, para, typeChip) {
    const ty = world().types[name], pc = parseT(name);
    if (pc) {
      const con = world().constructors[pc.con] || {};
      head(`${name} : *`, C.con);
      head(`${pc.con} : ${con.kind || "?"}`, C.con);
      if (con.describes) para(con.describes, C.mute);
      row([typeChip(pc.arg, "pg-a")]);
      return;
    }
    if (!ty) { head(name, C.no); return; }
    head(`${name} : ${ty.kind}`, colorOf(name));
    const doc = docOf(name);
    if (doc && doc !== name) para(doc, C.mute);
    if (ty.brand) { const chain = []; let t = ty.of; while (t) { chain.push(tname(t)); t = t.of; } head(`${name} ⊂ ${chain.join(" ⊂ ")}`, C.mute); row(chain.map((c) => typeChip(c, "pg-b"))); }
    if (ty.sum) {
      const alts = ty.alternatives || [];
      const tys = alts.filter((a) => !a.member).map((a) => tname(a));
      if (tys.length) { head(tys.join(" | "), C.mute); row(tys.map((c) => typeChip(c, "pg-u"))); }
      const ms = members(ty);
      if (ms.length) { head(`∋ ${ms.length}`, C.mute); row(ms.map((m) => [`pg-m-${m.of}-${m.member}`, m.words, C.type, C.card, { t: "member", type: m.of, words: m.words }, { open: { t: "type", name: m.of } }])); }
    }
    row(Object.keys(world().constructors).map((c) => typeChip(`${c}[${name}]`, "pg-c")));
    const fs = Object.entries(world().functions);
    const takes = fs.filter(([, f]) => f.parameters.some(([, t]) => mentions(t, name)));
    const gives = fs.filter(([, f]) => mentions(f.result, name));
    if (takes.length) { head(`→ ƒ`, C.fn); row(takes.map(([f, fd]) => [`pg-t-${f}`, `${f}(${fd.parameters.map(([p, t]) => p + ": " + tname(t)).join(", ")})`, C.fn, C.fnBg, { t: "fn", name: f }, { open: { t: "fn", name: f } }])); }
    if (gives.length) { head(`ƒ →`, C.fn); row(gives.map(([f, fd]) => [`pg-g-${f}`, `${f} → ${tname(fd.result)}`, C.fn, C.fnBg, { t: "fn", name: f }, { open: { t: "fn", name: f } }])); }
    // its relations as a graph, from the world record: what it is part of (⊂ brand, | sum) → it → the functions that take it → their results
    const parents = [...(ty.brand && ty.of ? [[tname(ty.of), "⊂"]] : []), ...Object.entries(world().types).filter(([, t]) => (t.alternatives || []).some((a) => !a.member && tname(a) === name)).map(([n]) => [n, "|"])];
    if (parents.length || takes.length) {
      head("⟷", C.mute);
      const y0 = y, colA = x0, colB = x0 + Math.min(130, w * 0.28), colC = x0 + Math.min(250, w * 0.5), colD = x0 + Math.min(390, w * 0.72), rowH = 28;
      const rows = Math.max(parents.length, takes.length, 1), mid = y0 + ((rows - 1) * rowH) / 2;
      const edge = (x1, y1, x2, y2, mark) => { els.push(h("path", { d: `M${x1},${y1} C${(x1 + x2) / 2},${y1} ${(x1 + x2) / 2},${y2} ${x2},${y2}`, fill: "none", stroke: C.mute, strokeOpacity: 0.6, strokeWidth: 1 })); if (mark) els.push(txt((x1 + x2) / 2 - 4, (y1 + y2) / 2 - 3, mark, F.mono, C.mute)); };
      parents.forEach(([n, mark], i) => { y = y0 + i * rowH; const cw = chipEl(`pg-gr-p-${n}`, colA, n, colorOf(n), C.typeBg, { t: "type", name: n }, { open: { t: "type", name: n } }); edge(colA + cw, y + 11, colB, mid + 11, mark); });
      y = mid; const cwB = chipEl(`pg-gr-me-${name.replace(/\W/g, "_")}`, colB, name, colorOf(name), C.typeBg, { t: "type", name }, { open: { t: "type", name } });
      takes.forEach(([f, fd], i) => {
        y = y0 + i * rowH;
        edge(colB + cwB, mid + 11, colC, y + 11, "→");
        const cw = chipEl(`pg-gr-f-${f}`, colC, f, C.fn, C.fnBg, { t: "fn", name: f }, { open: { t: "fn", name: f } });
        const r = tname(fd.result); edge(colC + cw, y + 11, colD, y + 11, "");
        chipEl(`pg-gr-r-${f}`, colD, r, colorOf(r), cat(r) === "con" ? C.conBg : C.typeBg, cat(r) === "fn" ? { t: "fn", name: r } : { t: "type", name: r }, { dash: cat(r) === "con", open: { t: "type", name: r } });
      });
      y = y0 + rows * rowH + 6;
    }
  }
  function drawFnPage(name, head, row, para, typeChip) {
    const f = world().functions[name];
    head(`ƒ ${name}(${f.parameters.map(([p, t]) => p + ": " + tname(t)).join(", ")}) → ${tname(f.result)}`, C.fn);
    para(f.asks, C.mute);
    row([...f.parameters.map(([, t]) => typeChip(tname(t), "pg-p")), typeChip(tname(f.result), "pg-r")]);
    const uses = allTerms(S.base).filter((x) => x.t.function === name);
    if (uses.length) row(uses.map(({ t }) => [`pg-u-${t.id}`, `#${t.id}`, C.fn, C.card, { t: "op", term: t }, { open: { t: "op", term: t } }]));
  }
}
function termLabel(t) { // a term as the record writes it, in the page's notation
  if (!t) return "∅";
  if (t.function) return `${t.function}(${Object.entries(t.arguments || {}).map(([k, v]) => k + ": " + termLabel(v)).join(", ")}) → ${t.type}`;
  if (t.ref != null) return "↩ " + t.ref;
  if (t.hole) return `▢ ${t.hole}${t.reason ? " · " + t.reason : ""}`;
  if (t.empty) return "∅ " + t.empty;
  if (t.several) return `[${t.several.map(termLabel).join(", ")}]`;
  if (t.constant != null) return `${t.at && t.at[0] >= 0 ? "“" + clip(t.constant) + "”" : t.constant} : ${t.type}`;
  return JSON.stringify(t).slice(0, 60);
}
function drawDecisions(ds, els, gy, sy, para) { // every decision for what is open, every option with its probability, every offered and cut term
  let y = gy();
  for (const dc of ds) {
    els.push(txt(PX, y + 12, `d1 · ${dc.by}${dc.rule ? " · " + dc.rule : ""}${dc.path ? " · " + dc.path : ""}`, F.head, C.ink)); y += 20;
    const label = (opt) => (/^\d+$/.test(opt) && dc.offered && dc.offered[+opt] ? `${opt}: ${termLabel(dc.offered[+opt])}` : opt);
    for (const [, a] of Object.entries(dc.answers || {})) {
      const pr = Object.entries(a.probabilities || {}).sort((x, z) => z[1] - x[1]);
      for (const [opt, pv] of pr) {
        const bw = Math.max(2, 80 * pv), lab = (String(a.value) === opt ? "● " : "  ") + label(opt);
        els.push(h("rect", { transform: translate(PX, y + 4), width: bw, height: 8, rx: 2, fill: C.fn, opacity: 0.6 }));
        els.push(txt(PX + 86, y + 12, pv.toFixed(2), F.small, C.mute));
        let first = true;
        for (const ln of wrap(lab, F.mono, PW - 130)) { els.push(txt(PX + 124, y + 12, (first ? "" : "  ") + ln, F.mono, C.ink)); y += 16; first = false; }
        y += 1;
      }
    }
    if (dc.offered && dc.offered.length) { els.push(txt(PX, y + 12, `offered ${dc.offered.length}`, F.mono, C.mute)); y += 17; dc.offered.forEach((o, i) => { for (const ln of wrap(`${i}: ${termLabel(o)}`, F.mono, PW - 16)) { els.push(txt(PX + 12, y + 12, ln, F.mono, C.ink)); y += 16; } }); }
    if (dc.cut && dc.cut.length) { els.push(txt(PX, y + 12, `cut ${dc.cut.length}`, F.mono, C.mute)); y += 17; dc.cut.forEach((o) => { for (const ln of wrap(termLabel(o), F.mono, PW - 16)) { els.push(txt(PX + 12, y + 12, ln, F.mono, C.ink)); y += 16; } }); }
    if (dc.state) { sy(y); para("state  " + dc.state, C.mute); y = gy(); }
    y += 6;
  }
  sy(y);
}
function wrap(s, f, w) {
  const out = []; let line = "";
  for (const word of String(s).split(/\s+/)) { const t = line ? line + " " + word : word; if (tw(t, f) > w && line) { out.push(line); line = word; } else line = t; }
  if (line) out.push(line);
  return out;
}

// ---------- the dock: the change under the pointer, before → after, and its confirm ----------
function strip(st) {
  const out = [];
  if (st.refused) { // the engine's rule, the place and the type it declares, and what was offered
    const b = st.refused.body || {};
    out.push(["no", "✕ " + st.refused.codes.map((c) => c.split(" · ").pop()).filter((c, i, a) => a.indexOf(c) === i).join(" ")]);
    if (b.number != null) {
      const t = allTerms(S.base).find((x) => String(x.t.id) === String(b.number)), pl = t && placesOf(t.t).find((p) => p.path === b.path);
      out.push(["was", `${t ? t.t.function : b.number}.${b.path} : ${pl ? pl.declared : "?"}`]);
      out.push(["sep", "⟵"]);
      const ht = heldType(b.value);
      out.push(["now", pl && b.value && b.value.type === pl.declared ? ht.replace(/ : [^:]+$/, "") : ht]);
    } else if (b.path === "kind") out.push(["was", `${b.value}|${clip(S.base.text.slice(b.at[0], b.at[1]))}`]);
    else if (b.number === null) out.push(["was", `+ ${b.path} ⟵ ${heldType(b.value)}`]);
    return out;
  }
  if (!st.change) return out;
  const b = st.change;
  if (b.path === "kind") {
    const bp = S.base.pieces || [], dp = (st.r.pieces || []);
    const gone = bp.filter((p) => p.end > b.at[0] && p.start < b.at[1] && !dp.some((q) => q.start === p.start && q.end === p.end && q.kind === p.kind));
    const added = dp.filter((p) => !bp.some((q) => q.start === p.start && q.end === p.end && q.kind === p.kind));
    for (const p of gone) out.push(["was", `${p.kind}|${clip(S.base.text.slice(p.start, p.end))}`]);
    out.push(["sep", "→"]);
    for (const p of added) out.push(["now", `${p.kind}|${clip(S.base.text.slice(p.start, p.end))}`]);
    if (st.wait) out.push(["sep", "…"]);
  } else {
    const t = allTerms(S.base).find((x) => String(x.t.id) === String(b.number));
    const pl = t && placesOf(t.t).find((p) => p.path === b.path);
    if (b.number == null) out.push(["now", `+ ${b.path.split(".")[0]}(${b.path.split(".")[1]}=${valLabel(b.value)})`]);
    else { out.push(["was", `${t ? t.t.function : b.number}.${b.path}=${pl ? slotOf(pl, S.base).g : "?"}`]); out.push(["sep", "→"]); out.push(["now", `${t ? t.t.function : b.number}.${b.path}=${valLabel(b.value)}`]); }
    if (b.value && b.value.ref != null) { const r = allTerms(S.base).find((x) => x.t.id === String(b.value.ref)); const j = r && r.t.judgments || {}; if (j.complete === false) out.push(["no", "● " + r.t.function + " complete ✕"]); if (j.pending) out.push(["no", "⧗"]); }
    if (st.wait) out.push(["sep", "…"]);
  }
  return out;
}
function heldType(v) { // the type of what was offered, from the request itself or the operation it refers to
  if (!v) return "∅";
  if (v.ref != null) { const t = allTerms(S.base).find((x) => x.t.id === String(v.ref)); return t ? `↩ ${t.t.function} : ${t.t.type}` : "↩ " + v.ref; }
  if (v.hole) return "▢ " + v.hole;
  return `${v.at && v.at[0] >= 0 ? "“" + clip(v.constant) + "”" : v.constant} : ${v.type}`;
}
const clip = (s) => { s = s.replace(/\s+/g, " "); return s.length > 36 ? s.slice(0, 34) + "…" : s; };
const valLabel = (v) => (v == null ? "∅" : v.ref != null ? "↩ " + ((allTerms(S.base).find((x) => x.t.id === String(v.ref)) || { t: { function: v.ref } }).t.function) : v.hole ? "▢ " + v.reason : v.constant != null ? (v.at && v.at[0] >= 0 ? "“" + clip(v.constant) + "”" : v.constant) : "?");
function paintDock(st) {
  const dock = $("dock"), parts = [];
  const sp = (cls, s) => `<span class="${cls}">${esc(s)}</span>`;
  const show = st || LIVE || cur();
  for (const [c, s] of strip(show)) parts.push(sp(c, s));
  if (S.note && !DRAGGING && !S.staged && !S.hold) for (const [c, s] of strip(S.note)) parts.push(sp(c, s));
  let btn = "";
  if (S.staged && !DRAGGING) {
    const v = verdict(S.staged.e);
    btn = `<button id="accept" class="go" ${v === "ok" ? "" : "disabled"}>✓ a</button><button id="cancel">✕ esc</button>`;
  }
  const undo = S.undo.length && !S.staged && !DRAGGING ? `<button id="undo">↶ z</button>` : "";
  const html = parts.join(" ") + `<span class="grow"></span>${btn}${undo}`;
  if (dock.__html === html) return;
  dock.__html = html; dock.innerHTML = html;
  if ($("accept")) $("accept").onclick = accept;
  if ($("cancel")) $("cancel").onclick = cancel;
  if ($("undo")) $("undo").onclick = undo1;
}
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

// ---------- stage, accept, cancel, undo: all through the engine ----------
function stageBody(body) {
  if (!body) return;
  const e = ask(body, true);
  S.staged = { body, e }; S.hold = null; S.note = null;
  paint();
}
function dropped(next) {
  DRAGGING = false; HELD = null; LIVE = null; RAIL_IDS = new Set();
  if (next && next.scroll != null && next.scroll !== S.scroll && !next.change) S.scroll = next.scroll;
  if (next && next.refused) { S.note = { refused: next.refused }; S.staged = null; }
  else if (next && next.change) stageBody(next.change);
  paint();
}
async function accept() {
  if (!S.staged || verdict(S.staged.e) !== "ok") return;
  const body = S.staged.body, was = S.base.snapshot;
  const r = await post("/accept", { reading: S.id, ...body });
  if (!r.saved) { S.note = { refused: { codes: codes({ diag: r.diagnostics, error: r.error }) } }; S.staged = null; return paint(); }
  S.undo.push({ snapshot: was, idx: IDX.get(was) });
  await reload();
}
function cancel() { S.staged = null; S.hold = null; S.note = null; paint(); }
async function undo1() {
  const u = S.undo.pop();
  if (!u) return;
  const r = await post("/restore", { snapshot: u.idx });
  if (!r.saved) { S.note = { refused: { codes: codes({ diag: r.diagnostics, error: r.error }) } }; return paint(); }
  await reload();
}
async function reload() {
  await loadAll();
  S.base = LATEST.get(S.id); S.staged = null; S.hold = null; DRAFTS.clear(); VERD.clear(); Q = []; S.stale = null;
  if (S.open && S.open.t === "piece") { const p = (S.base.pieces || []).find((q) => q.start <= S.open.p.start && S.open.p.start < q.end); S.open = p ? { t: "piece", p } : null; }
  else if (S.open && (S.open.t === "op" || S.open.t === "place")) S.open = null;
  pick(); paint();
}
function openThing(th) {
  if (DRAGGING) return;
  S.open = th && th.t !== "none" ? th : null; S.pscroll = 0; S.note = null;
  const f = th && FOC.find((x) => x.th === th);
  if (f) S.focus = f.id;
  paint();
}

// ---------- the keyboard: the same options as the pointer, the same /edit bodies ----------
function holdOf(th) {
  const { out, places } = options(th);
  th.places = places; delete th.rail;
  verdicts(places.map((o) => o.body));
  const opts = [...out.filter((o) => !o.self), ...places.slice().sort((a, b) => b.open - a.open)];
  const fb = far(th);
  if (fb) opts.push({ target: null, body: fb, pull: true });
  if (!opts.length) return null;
  return { th, opts, i: 0 };
}
function holdState() {
  const o = S.hold.opts[S.hold.i];
  if (o.states) return withDraft(o.states[o.k]);
  if (!o.body) return base();
  ask(o.body, true);
  return withDraft(stateFor(o.body, { target: o.target, pull: o.pull }));
}
function stepHandle(side, dir) { // ] widen end, [ narrow end, { widen start, } narrow start
  const f = FOC.find((x) => x.id === S.focus), p = f && f.th.t === "piece" ? f.th.p : S.open && S.open.t === "piece" ? S.open.p : null;
  if (!p) return;
  S.open = { t: "piece", p };
  const st = handleStates(p, side);
  if (!S.hold || !S.hold.handle || S.hold.side !== side) {
    const k0 = st.findIndex((s) => !s.change);
    S.hold = { handle: true, side, th: { t: "handle", p }, opts: [{ states: st, k: k0 }], i: 0 };
  }
  const o = S.hold.opts[0];
  o.k = Math.max(0, Math.min(st.length - 1, o.k + dir));
  if (o.states[o.k].change) ask(o.states[o.k].change, true);
  paint();
}
function moveFocus(dir, vertical) {
  const zone = FOC.filter((f) => f.zone === S.zone);
  if (!zone.length) return;
  let i = zone.findIndex((f) => f.id === S.focus);
  if (i < 0) i = dir > 0 ? -1 : zone.length;
  if (vertical && S.zone === "text") {
    const c = zone[i] || zone[0], li = c.li + dir;
    const cand = zone.filter((f) => f.li === li);
    if (cand.length) { S.focus = cand.reduce((a, b) => (Math.abs(b.x - c.x) < Math.abs(a.x - c.x) ? b : a)).id; return; }
    if (dir > 0 && S.scroll < layout(S.base).lines.length - visLines()) { S.scroll += 1; return; }
    if (dir < 0 && S.scroll > 0) { S.scroll -= 1; return; }
  }
  const j = i + dir;
  if (j >= 0 && j < zone.length) S.focus = zone[j].id;
  else if (S.zone === "text") { // the next link beyond the view: scroll one line
    const L = layout(S.base);
    S.scroll = Math.max(0, Math.min(L.lines.length - visLines(), S.scroll + dir));
    S.focus = null; S.pendingFocus = dir;
  }
}
document.addEventListener("keydown", (k) => {
  if (!S.base || k.target.tagName === "SELECT" || k.metaKey || k.ctrlKey) return;
  const key = k.key;
  if (S.hold) {
    const n = S.hold.opts.length;
    if (S.hold.handle && (key === "]" || key === "[" || key === "{" || key === "}")) { stepHandle(key === "]" || key === "[" ? "e" : "s", key === "]" || key === "{" ? (key === "{" ? -1 : 1) : key === "[" ? -1 : 1); return k.preventDefault(); }
    const refusedAt = (i) => { const o = S.hold.opts[i]; return o && o.body && o.body.number != null && vOf(o.body) === "no"; };
    const step = (d) => { let i = S.hold.i; for (let g = 0; g < n; g++) { i = (i + d + n) % n; if (!refusedAt(i)) break; } S.hold.i = i; };
    if (["ArrowRight", "ArrowDown", "Tab"].includes(key) && !k.shiftKey) step(1);
    else if (["ArrowLeft", "ArrowUp"].includes(key) || (key === "Tab" && k.shiftKey)) step(-1);
    else if (key === "Enter" || key === " ") { const st = holdState(); S.hold = null; if (st.refused) S.note = { refused: st.refused }; else if (st.change) stageBody(st.change); paint(); return k.preventDefault(); }
    else if (key === "Escape") { S.hold = null; paint(); return k.preventDefault(); }
    else return;
    const o = S.hold.opts[S.hold.i];
    if (o.target && o.target.startsWith("pc-")) { const b = DRAWN.get(o.target); void b; }
    paint(); return k.preventDefault();
  }
  if (key === "Escape") { if (S.staged) cancel(); else { S.note = null; openThing(null); } return k.preventDefault(); }
  if (key === "a" && S.staged) { accept(); return k.preventDefault(); }
  if (key === "z" && S.undo.length && !S.staged) { undo1(); return k.preventDefault(); }
  if (key === "]" || key === "[") { stepHandle("e", key === "]" ? 1 : -1); return k.preventDefault(); }
  if (key === "}" || key === "{") { stepHandle("s", key === "{" ? -1 : 1); return k.preventDefault(); }
  if (key === "Tab") { S.zone = S.zone === "text" ? "page" : "text"; S.focus = null; moveFocus(1); paint(); return k.preventDefault(); }
  if (key === "ArrowRight" || key === "ArrowLeft") { moveFocus(key === "ArrowRight" ? 1 : -1); paint(); return k.preventDefault(); }
  if (key === "ArrowDown" || key === "ArrowUp") { moveFocus(key === "ArrowDown" ? 1 : -1, true); paint(); return k.preventDefault(); }
  if (key === "PageDown" || key === "PageUp") { const L = layout(S.base); S.scroll = Math.max(0, Math.min(L.lines.length - visLines(), S.scroll + (key === "PageDown" ? 1 : -1) * (visLines() - 2))); S.focus = null; paint(); return k.preventDefault(); }
  const f = FOC.find((x) => x.id === S.focus);
  if (!f) return;
  if (key === "Enter") { if (f.act) f.act(); else openThing(f.th); return k.preventDefault(); }
  if (key === " ") { const th = f.drag || f.th; if (th.t === "place" || th.t === "un") return k.preventDefault(); S.hold = holdOf(th); paint(); return k.preventDefault(); }
});
$("board").addEventListener("wheel", (w) => { // scrolling the view, not moving a thing
  if (DRAGGING || !S.base) return;
  w.preventDefault();
  if (w.clientX > $("board").getBoundingClientRect().left + PX - 20) { S.pscroll = Math.max(0, S.pscroll + w.deltaY); }
  else { const L = layout(S.base); S.scroll = Math.max(0, Math.min(Math.max(0, L.lines.length - visLines()), S.scroll + w.deltaY / LH)); S.note = null; }
  paint();
}, { passive: false });

// ---------- the page ----------
let root = null;
let SHOWN = { k: null, st: null };
function display() {
  const st = S.hold ? holdState() : cur();
  const k = JSON.stringify([S.base.snapshot, S.scroll, S.pscroll, st.change, st.r === S.base, !!st.wait, !!st.refused, st.handle, st.target, S.open ? pageKey() : "", S.focus, S.zone, S.more, S.hold && S.hold.i, S.hold ? DV : 0]);
  if (SHOWN.k === k) return SHOWN.st;
  SHOWN = { k, st };
  return st;
}
function paint() {
  if (!S.base) return;
  sizes();
  const st = display();
  root ??= createRoot($("board"));
  root.render(h(DraggableRenderer, { key: S.id, draggable, state: st, width: BW, height: BH, dragThreshold: 4, onDropState: dropped, onDragStatus: status }));
  if (S.pendingFocus) { requestAnimationFrame(() => { const zone = FOC.filter((f) => f.zone === "text"); if (zone.length && S.pendingFocus) { S.focus = (S.pendingFocus > 0 ? zone[zone.length - 1] : zone[0]).id; S.pendingFocus = 0; paint(); } }); }
  paintDock(DRAGGING ? LIVE : st);
  if (S.focus) $("board").setAttribute("aria-activedescendant", S.focus); else $("board").removeAttribute("aria-activedescendant");
}
// a press that never became a drag (a click) leaves nothing held
function status(st) {
  const was = DRAGGING || PENDING, wasD = DRAGGING;
  DRAGGING = st.type === "dragging"; PENDING = !!st.pendingDrag;
  if (DRAGGING && !wasD && HELD && HELD.places) verdicts([...HELD.places, ...(HELD.retags || [])].map((o) => o.body));
  if (DRAGGING && !wasD) S.note = null; // a new drag clears the last refusal // the engine's verdict for every place, in one request
  if (!DRAGGING && !st.pendingDrag && HELD) { HELD = null; RAIL_IDS = new Set(); LIVE = null; setTimeout(paint, 0); }
  else if (was && !DRAGGING && !PENDING) setTimeout(paint, 0);
}
function pick() {
  const words = S.base.text.trim().split(/\s+/);
  $("tab").textContent = words.slice(0, 8).join(" ") + (words.length > 8 ? " …" : "");
  $("tab").title = S.base.text.slice(0, 300);
  const n = S.base.corrections.length;
  $("snap").textContent = [S.stale ? "⟳ newer" : "", n ? `✎ ${n}` : ""].filter(Boolean).join("   ");
}
async function choose(id) {
  S.id = id; S.base = LATEST.get(id); S.staged = null; S.hold = null; S.open = null; S.scroll = 0; S.focus = null; S.undo = []; S.note = null;
  DRAFTS.clear(); VERD.clear(); Q = []; S.stale = null;
  const u = new URL(location); u.searchParams.set("r", id.slice(0, 8)); history.replaceState(null, "", u);
  pick(); paint();
}
(async function main() {
  await loadAll();
  const query = new URL(location).searchParams, want = query.get("r") || query.get("reading"); // ?reading= from the desktop mod
  await Promise.all([F.text, F.it, F.code, F.monoB].map((f) => document.fonts.load(f).catch(() => null))); // text is measured on a canvas: the fonts first
  const latest = LINES.at(-1).id, first = (want && [...LATEST.keys()].find((id) => id.startsWith(want))) || latest; // the latest message unless a link names one
  $("keybtn").onclick = () => { const k = $("key"); k.hidden = !k.hidden; $("keybtn").setAttribute("aria-expanded", String(!k.hidden)); };
  addEventListener("resize", () => paint());
  await choose(first);
})();
