// board.js: the board. A pure function from a draft reading to SVG (Dragology 0.2.0), the panel, the world graph.
// Names, types, members, functions, judgments and decisions are read from engine/readings.json and engine/worlds.json.
// What the page derives itself (what fits, the flags of an edited operation, a new operation) comes from model.js and is drawn provisional.
(() => {
const { React, createRoot, DraggableRenderer, translate } = window.Dragology, h = React.createElement, M = window.Model;
const $ = (id) => document.getElementById(id);
const C = { ink: "#16181d", mute: "#5b6270", rule: "#cfd3da", bg: "#ffffff", surface: "#f4f5f7", accent: "#1d4ed8", ok: "#157a3b", no: "#b4231f", text: "system-ui,-apple-system,'Segoe UI',Roboto,sans-serif", code: "ui-monospace,'SF Mono',Menlo,Consolas,monospace" };
const HUES = ["#2563eb", "#d97706", "#059669", "#db2777", "#7c3aed", "#0891b2", "#65a30d", "#dc2626"];
const SHAPES = ["M-6,0a6,6 0 1,0 12,0a6,6 0 1,0 -12,0", "M-5,-5h10v10h-10z", "M0,-6L6,5L-6,5z", "M0,-7L7,0L0,7L-7,0z", "M-6,0L-3,-6L3,-6L6,0L3,6L-3,6z", "M-2,-6h4v4h4v4h-4v4h-4v-4h-4v-4h4z"];
let W = 1200, GX = 744, FX = 1008, NAR = false; const MW = 680, RH = 48, CH = 32;
const V = Number(new URLSearchParams(location.search).get("v") ?? 15), INLINE = V === 13 || V >= 15;
const setMode = () => { NAR = innerWidth < 1120; W = NAR ? 740 : 1200; GX = NAR ? 28 : 744; FX = NAR ? 330 : 1008; };
const cv = document.createElement("canvas").getContext("2d");
const tw = (s, px = 15, wt = 400, fam = C.text) => { cv.font = `${wt} ${px}px ${fam}`; return Math.ceil(cv.measureText(String(s)).width); };

// ---------- the open reading
let READINGS = [], WORLDS = {}, RD = null, SEL = null, NAV = [], HOVER = null, HELD = null, LIT = new Set(), ACCEPT = new Set(), REFUSED = {}, STEP = null, root = null, LASTL = null;
const NS = /[?&]audit/.test(location.search) ? "scriptt-audit:" : "scriptt-draft:";
const FIT = () => HELD?.fit ?? null;

function units(r, consts) {   // every word is a unit; a constant is one unit (its span); punctuation is a unit
  const out = [], cs = [...(consts ?? r.constants)].sort((a, b) => a.at[0] - b.at[0]);
  const push = (s, e, c) => { const text = r.text.slice(s, e); const ph = r.phrases.findIndex((p) => s >= p.start && s < p.end); out.push({ id: `u-${s}`, start: s, end: e, text, c: c ?? null, phrase: Math.max(0, ph) }); };
  let at = 0;
  const words = (a, b) => { for (const m of r.text.slice(a, b).matchAll(/\S+/g)) push(a + m.index, a + m.index + m[0].length, null); };
  for (const c of cs) { if (c.at[0] < at) continue; words(at, c.at[0]); push(c.at[0], c.at[1], c); at = c.at[1]; }
  words(at, r.text.length);
  return out;
}
function open(i) {
  const r = READINGS[i], wx = M.indexWorld(WORLDS[r.world]), base = M.toDraft(r);
  let st = base;
  try { const saved = JSON.parse(localStorage.getItem(NS + r.id + ":" + r.case) ?? "null"); if (saved) st = saved; } catch {}
  st.consts ??= structuredClone(r.constants); st.world ??= [];
  RD = { i, r, wx, base, st, units: units(r, st.consts), undo: [], redo: [] };
  SEL = null; NAV = []; HOVER = null; HELD = null; STEP = null; LIT = new Set();
  $("pick").value = String(i);
  paint(); renderPanel(); tools();
}
const tools = () => { $("undo").disabled = !RD.undo.length; $("redo").disabled = !RD.redo.length; $("reset").disabled = JSON.stringify(RD.st) === JSON.stringify(RD.base); };
function commit(next) {
  if (JSON.stringify(next) === JSON.stringify(RD.st)) return;
  const log = changes(RD.st, next).filter((c) => c.path || /^\+/.test(c.after)).map((c) => ({ operation: c.op, path: c.path, value: c.after, status: "provisional" }));
  next = { ...next, log: [...(RD.st.log ?? []), ...log] };
  RD.undo.push(RD.st); RD.redo = []; RD.st = next; save(); paint(); renderPanel(); tools();
}
const save = () => { try { localStorage.setItem(NS + RD.r.id + ":" + RD.r.case, JSON.stringify(RD.st)); } catch {} };
function undo() { if (!RD.undo.length) return; RD.redo.push(RD.st); RD.st = RD.undo.pop(); save(); paint(); renderPanel(); tools(); }
function redo() { if (!RD.redo.length) return; RD.undo.push(RD.st); RD.st = RD.redo.pop(); save(); paint(); renderPanel(); tools(); }
function revert() { RD.undo.push(RD.st); RD.redo = []; RD.st = RD.base; save(); paint(); renderPanel(); tools(); }

// ---------- what a value looks like, and what changed
const show = (v) => { const k = M.kindOf(v); return k === "const" ? `“${v.constant}”` : k === "ref" ? `↩${v.ref}` : k === "hole" ? `? ${v.hole} (${v.reason || "open"})` : k === "empty" ? `none ${v.empty}` : k === "several" ? `[${v.several.map(show).join(", ")}]` : k === "fields" ? `{${Object.entries(v.fields).map(([f, x]) => f + ": " + show(x)).join(", ")}}` : "—"; };
const flagText = (o) => flag(o) + (flag(o) === "ready" && o.judg.deferred ? " · later" : "") + (o.prov ? " ≈" : "");
const flag = (o) => !o.judg.complete ? "open" : !o.judg.ready ? "waits" : "ready";
function changes(a, b) {
  const out = [];
  for (const id of b.order) {
    const x = a.ops[id], y = b.ops[id];
    if (!x) { out.push({ op: id, path: "", before: "", after: `+ ${y.fn}`, text: `+ ${y.fn}#${id}` }); continue; }
    for (const k of Object.keys(y.args)) if (JSON.stringify(x.args[k]) !== JSON.stringify(y.args[k])) out.push({ op: id, path: k, before: show(x.args[k]), after: show(y.args[k]), text: `${x.fn}.${k}  ${show(x.args[k])} → ${show(y.args[k])}` });
    if (flag(x) !== flag(y)) out.push({ op: id, path: "", before: flag(x), after: flag(y), text: `${y.fn}#${id}  ${flag(x)} → ${flag(y)}${y.prov ? " ≈" : ""}` });
  }
  for (const id of a.order) if (!b.ops[id]) out.push({ op: id, path: "", before: a.ops[id].fn, after: "", text: `− ${a.ops[id].fn}#${id}` });
  return out;
}

// ---------- relations: which things belong to which (all from the data); a hover, a hold or a selection lights one and its relations
function relations(st) {
  const rel = new Map(), add = (a, b) => { if (!a || !b || a === b) return; (rel.get(a) ?? rel.set(a, new Set()).get(a)).add(b); (rel.get(b) ?? rel.set(b, new Set()).get(b)).add(a); };
  const { wx, r } = RD, F = wx.W.functions, inner = (t) => (M.ctorOf(t) ? inner(t.of) : t);
  const phraseUnits = (pi) => RD.units.filter((u) => u.phrase === pi);
  for (const id of st.order) {
    const op = st.ops[id], f = F[op.fn];
    add(`op-${id}`, `fn-${op.fn}`); add(`op-${id}`, `ty-${M.resultName(op).replace(/^(Many|Maybe)\[(.*)\]$/, "$2")}`); add(`op-${id}`, `rs-${id}`); add(`op-${id}`, `st-${id}`);
    if (op.phrase != null) { add(`op-${id}`, `ph-${op.phrase}`); phraseUnits(op.phrase).forEach((u) => add(`op-${id}`, u.id)); }
    for (const r2 of M.refsIn(op)) add(`op-${id}`, `op-${r2}`);
    if (f) { add(`fn-${op.fn}`, `ty-${M.nameOf(inner(f.result))}`); for (const [, tr] of f.parameters) add(`fn-${op.fn}`, `ty-${M.nameOf(inner(tr))}`); }
  }
  for (const pl of M.places(wx, st)) {
    add(pl.id, `op-${pl.op}`); add(pl.id, `lb-${pl.op}-${pl.path.split(".")[0]}`); if (st.ops[pl.op].phrase != null) phraseUnits(st.ops[pl.op].phrase).forEach((u) => add(pl.id, u.id)); add(pl.id, `ty-${M.nameOf(inner(pl.tree))}`);
    const v = pl.val;
    if (v?.constant != null) { add(pl.id, `ty-${v.type}`); const u = RD.units.find((x) => x.c && x.c.at && v.at && x.c.at[0] === v.at[0]); if (u) add(pl.id, u.id); }
    if (v?.ref != null) { add(pl.id, `op-${v.ref}`); add(pl.id, `ty-${M.resultName(st.ops[v.ref] ?? { type: "?" }).replace(/^(Many|Maybe)\[(.*)\]$/, "$2")}`); }
  }
  for (const u of RD.units) { add(u.id, `ph-${u.phrase}`); if (u.c) add(u.id, `ty-${u.c.type}`); }
  for (const n of Object.keys(wx.W.types)) { add(`ty-${n}`, `sm-${n}`); add(`ty-${n}`, `kd-${n}`); }
  for (const [f, d] of Object.entries(F)) d.parameters.forEach(([p, tr]) => { add(`pt-${f}-${p}`, `fn-${f}`); add(`pt-${f}-${p}`, `ty-${M.nameOf(inner(tr))}`); });
  for (const [n, t] of Object.entries(wx.W.types)) {   // structure: a brand wraps, a sum has alternatives, a product has fields
    const kids = t.brand && t.of ? [t.of] : t.sum ? t.alternatives.filter((a) => !a.member) : t.product ? Object.values(t.fields) : [];
    kids.forEach((k) => { const nm = M.nameOf(inner(k)); if (wx.W.types[nm]) add(`ty-${n}`, `ty-${nm}`); });
  }
  return rel;
}
const litFrom = (key, rel) => { const s = new Set(); if (!key) return s; s.add(key); rel.get(key)?.forEach((k) => s.add(k)); return s; };

// ---------- layout: positions only (the board is a function of the draft, the selection and what is held)
function layout(st) {
  setMode();
  const { wx, r } = RD, F = wx.W.functions, T = wx.W.types, L = { box: {}, items: [], edges: [], arcs: [], rel: relations(st), places: M.places(wx, st) };
  const put = (id, x, y, w, hh, extra = {}) => { const e = { id, x, y, w, h: hh, ...extra }; L.box[id] = e; L.items.push(e); return e; };
  // 1. the message
  const SP = tw(" ", 20), U = RD.units;
  const flow = (list, y0) => {   // the words of one stretch, wrapped; returns the y of the last line
    let x = 0, y = y0;
    list.forEach((u) => { const w = tw(u.text, 20, u.c ? 600 : 400), prev = U[U.indexOf(u) - 1], first = list[0] === u;
      const gap = first || !prev ? 0 : u.start > prev.end ? SP + (u.phrase !== prev.phrase ? 8 : 0) : 0;
      if (x + gap + w > MW && x > 0) { x = 0; y += 40; } else x += gap;
      put(u.id, x, y, w, 32, { t: "unit" , u }); x += w; });
    return y;
  };
  const lineEnd = {};  // phrase rules: one per phrase per line
  const rulesFor = () => { for (const e of L.items.filter((i) => i.t === "unit")) { const key = e.u.phrase + ":" + e.y; (lineEnd[key] ??= { x1: e.x, x2: e.x + e.w, y: e.y + 32, ph: e.u.phrase }); lineEnd[key].x1 = Math.min(lineEnd[key].x1, e.x); lineEnd[key].x2 = Math.max(lineEnd[key].x2, e.x + e.w); } };
  const finishRules = () => { rulesFor(); L.rules = Object.values(lineEnd); };
  // 2. operations: one row per operation, in the order of the phrases; open phrases and quotes are rows too
  const rows = [];
  r.phrases.forEach((p, pi) => { st.order.filter((id) => st.ops[id].phrase === pi).forEach((id) => rows.push({ k: "op", id })); if (p.unresolved) rows.push({ k: "un", pi, p }); else if (p.quotes != null && !p.terms.length) rows.push({ k: "qt", pi, p }); });
  st.order.filter((id) => st.ops[id].phrase == null).forEach((id) => rows.push({ k: "op", id }));
  let ry = 0;
  const opRows = rows.filter((x) => x.k === "op"), opW = Math.max(0, ...opRows.map((x) => tw(x.id, 12, 600, C.code) + tw(st.ops[x.id].fn, 15, 600) + 34)), stW = Math.max(0, ...opRows.map((x) => 20 + tw(flagText(st.ops[x.id]), 13, 400, C.code) + 8));
  const rsW = Math.max(0, ...opRows.map((x) => 14 + 12 + tw(st.ops[x.id].type, 13, 400, C.code) + 12)), px0 = 28 + opW + 8 + rsW + 8 + stW + 24;   // the column where the places start: every row shares it (alignment)
  const lblW = Math.max(0, ...L.places.map((p) => tw(p.path.split(".")[0], 12, 400, C.code))) + 8;
  const emit = (row) => {
    if (row.k === "op") {
      const op = st.ops[row.id], names = [...new Set(L.places.filter((p) => p.op === row.id).map((p) => p.path.split(".")[0]))];
      put(`op-${row.id}`, 28, ry + 8, opW, 32, { t: "op", op, row: row.id });
      put(`rs-${row.id}`, 28 + opW + 8, ry + 8, rsW, 32, { t: "result", op });
      put(`st-${row.id}`, 28 + opW + 8 + rsW + 8, ry + 8, stW, 32, { t: "status", op });
      let line = 0;
      for (const nm of names) {
        let cx = px0, cy = ry + 8 + line * 40;
        const first = L.places.find((p) => p.op === row.id && p.path.split(".")[0] === nm);
        put(`lb-${row.id}-${nm}`, cx, cy, lblW - 4, 32, { t: "label", op: row.id, name: nm, pl: first }); cx += lblW;
        for (const pl of L.places.filter((p) => p.op === row.id && p.path.split(".")[0] === nm)) {
          const pw = placeW(pl, st);
          if (cx + pw > MW + 40 && cx > px0 + lblW) { cx = px0 + lblW; line++; cy += 40; }
          put(pl.id, cx, cy, pw, 32, { t: "place", pl, op: row.id }); cx += pw + 8;
          if (pl.val?.ref != null) L.arcs.push({ from: `op-${row.id}`, via: pl.id, to: `op-${pl.val.ref}`, id: `arc-${pl.id}` });
        }
        line++;
      }
      ry += Math.max(48, Math.max(1, line) * 40 + 8) + 8;
    } else if (row.k === "un") {
      const s2 = `? ${row.p.unresolved.reason}`, w = tw(s2, 14, 600) + 24;
      put(`un-${row.pi}`, 28, ry + 8, w, 32, { t: "unres", p: row.p, pi: row.pi }); ry += 56;
    } else {
      const s2 = `“ ${row.p.quotes}`, w = tw(s2, 14, 600) + 24;
      put(`qt-${row.pi}`, 28, ry + 8, w, 32, { t: "quote", p: row.p, pi: row.pi }); ry += 56;
    }
  };
  if (!INLINE) { const yEnd = flow(U, 0); ry = yEnd + 72; rows.forEach(emit); }
  else { ry = 0; r.phrases.forEach((p, pi) => { const list = U.filter((u) => u.phrase === pi); if (list.length) ry = flow(list, ry) + 32 + 8; rows.filter((x) => (x.k === "op" ? st.ops[x.id].phrase === pi : x.pi === pi)).forEach(emit); ry += 16; }); rows.filter((x) => x.k === "op" && st.ops[x.id].phrase == null).forEach(emit); }
  finishRules();
  // refs: each arc has its own lane in the gutter
  L.arcs.forEach((a, k) => { a.lane = 8 + (k % 3) * 6; });
  L.leftBottom = ry;
  // 3. the world graph, built from worlds.json: types (left), functions with a port for each parameter (right)
  const fit = FIT(), tys = Object.keys(T), fns = Object.keys(F);
  const selT = /^(ty|sm|kd)-/.test(SEL ?? "") ? SEL.slice(3) : /^u-/.test(SEL ?? "") ? RD.units.find((x) => x.id === SEL)?.c?.type ?? null : null;
  let gy = NAR ? L.leftBottom + 32 : 24; const tn = {}, gTop = gy;
  for (const n of tys) {
    const t = T[n], w = 14 + 8 + tw(n, 14, 600) + 12, kw = tw(t.kind, 12, 400, C.code) + 16;
    const e = put(`ty-${n}`, GX, gy, w, 32, { t: "tnode", name: n, def: t }); tn[n] = e;
    put(`sm-${n}`, GX + w + 2, gy, 28, 32, { t: "smark", name: n, def: t }); put(`kd-${n}`, GX + w + 32, gy, kw, 32, { t: "kmark", name: n, def: t }); e.rx = GX + w + 32 + kw; gy += 40;
    if (n === selT) {   // the selected type opens into its structure: members are things to pick up
      const kids = t.brand && t.of ? [{ k: "wraps", text: `wraps ${M.nameOf(t.of)}`, name: M.nameOf(t.of) }]
        : t.sum ? t.alternatives.map((a, i) => a.member ? { k: "member", i, draft: !!a.draft, text: a.words, member: a.member, c: { constant: a.words, type: n, at: null } } : { k: "alt", i, text: M.nameOf(a), name: M.nameOf(a) })
        : t.product ? Object.entries(t.fields).map(([f, ft], i) => ({ k: "field", i, text: `${f}: ${M.nameOf(ft)}`, name: M.nameOf(ft) })) : [];
      kids.forEach((kd, i) => { const w2 = 16 + tw(kd.text + (kd.draft ? " ≈" : ""), 13, 400, C.code) + 12; put(`mb-${n}-${i}`, GX + 24, gy, w2, 32, { t: "tchild", kd, of: n }); gy += 40; });
    }
  }
  const gc = {}; for (const [c, def] of Object.entries(wx.W.constructors)) { const s = `${c} : ${def.kind}`, w = tw(s, 14, 600) + 28; put(`ct-${c}`, GX, gy, w, 32, { t: "ctor", name: c, def }); gy += 40; }
  // functions: re-ranked while holding: those that take or give what is held come first
  const takesHeld = (f) => fit ? fit.has(f) : false;
  const order = [...fns].sort((a, b) => (takesHeld(b) ? 1 : 0) - (takesHeld(a) ? 1 : 0) || fns.indexOf(a) - fns.indexOf(b));
  let fy = gTop, sep = false;
  order.forEach((f, k) => {
    if (fit && !sep && !takesHeld(f)) { sep = true; if (k > 0) fy += 16; }
    const np = F[f].parameters.length, w = 188;
    put(`fn-${f}`, FX, fy, w, 32, { t: "fnode", name: f, def: F[f] });
    F[f].parameters.forEach(([p, tr], i) => put(`pt-${f}-${p}`, FX + 8, fy + 32 + 24 * i, w - 8, 24, { t: "port", fn: f, param: p, tree: tr, i }));
    fy += 32 + 24 * np + 8;
  });
  const inner = (t) => (M.ctorOf(t) ? inner(t.of) : t);
  for (const f of fns) F[f].parameters.forEach(([p, tr], i) => { const tnode = tn[M.nameOf(inner(tr))], fnode = L.box[`fn-${f}`]; if (tnode && fnode) L.edges.push({ id: `e-${f}-${p}`, a: tnode, b: fnode, dy: 32 + 24 * i + 12, kind: "param", fn: f, ty: tnode.id }); });
  for (const f of fns) { const tnode = tn[M.nameOf(inner(F[f].result))], fnode = L.box[`fn-${f}`]; if (tnode && fnode) L.edges.push({ id: `r-${f}`, a: tnode, b: fnode, dy: 16, kind: "result", fn: f, ty: tnode.id }); }
  L.struct = []; for (const [n, t] of Object.entries(T)) { const kids = t.brand && t.of ? [[t.of, "of"]] : t.sum ? t.alternatives.filter((a) => !a.member).map((a) => [a, "alt"]) : t.product ? Object.values(t.fields).map((f) => [f, "field"]) : []; kids.forEach(([k, kind]) => { const nm = M.nameOf(inner(k)); if (tn[nm] && nm !== n) L.struct.push({ id: `s-${n}-${nm}`, a: tn[n], b: tn[nm], kind }); }); }
  L.height = Math.max(L.leftBottom, gy, fy) + 16;
  return L;
}
function placeW(pl, st) {
  const v = pl.val, k = M.kindOf(v);
  if (pl.add) return pl.emptyList ? 10 + tw("none", 14) + 20 + 12 : 32;
  const g = 14 + 6;
  if (k === "const") return 10 + g + tw(v.constant, 15, 600) + 12;
  if (k === "ref") { const o = st.ops[v.ref]; return 10 + tw("↩", 15) + 6 + tw(v.ref, 12, 600, C.code) + 8 + tw(o?.fn ?? "?", 15, 600) + 12; }
  if (k === "hole") return 10 + g + tw(`${pl.declared} · ${v.reason || "open"}`, 14) + 12;
  if (k === "empty") return 10 + g + tw(`none ${v.empty}`, 14) + 12;
  return 10 + g + tw(pl.declared, 14) + 12;
}

// ---------- the board
const typeIdx = (n) => Math.max(0, Object.keys(RD.wx.W.types).indexOf(n));
const color = (n) => HUES[typeIdx(n) % HUES.length];
const glyph = (x, y, n, k = "g") => h("path", { dragologyKey: k, d: SHAPES[typeIdx(n) % SHAPES.length], transform: translate(x, y), fill: color(n), stroke: C.ink, strokeWidth: 1, "data-type": n });
const txt = (k, x, y, s, o = {}) => h("text", { dragologyKey: k, transform: translate(x, y), fontFamily: o.code ? C.code : C.text, fontSize: o.size ?? 15, fontWeight: o.w ?? 400, fill: o.fill ?? C.ink, textAnchor: o.anchor, ...(o.rest ?? {}) }, s);
const rect = (k, w, hh, o = {}) => h("rect", { dragologyKey: k, className: "mark", width: w, height: hh, rx: o.rx ?? 6, fill: o.fill ?? C.bg, stroke: o.stroke ?? C.ink, strokeWidth: o.sw ?? 1.5, ...(o.dash ? { strokeDasharray: o.dash } : {}) });

let DR = null;   // set by the render function so grab() can reach the builder
function thingOf(e, st) {
  const { wx } = RD;
  switch (e.t) {
    case "unit": return e.u.c ? { k: "const", c: e.u.c } : (() => { const id = st.order.find((o) => st.ops[o].phrase === e.u.phrase); return id != null ? { k: "op", id } : { k: "none", why: RD.r.phrases[e.u.phrase]?.unresolved ? `no function: ${RD.r.phrases[e.u.phrase].unresolved.reason}` : "quoted: an earlier reply, kept as given" }; })();
    case "op": return { k: "op", id: e.row };
    case "place": { const v = e.pl.val, k = M.kindOf(v); return k === "const" ? { k: "const", c: v, from: e.pl.id } : k === "ref" ? { k: "op", id: v.ref, from: e.pl.id } : { k: "hole", place: e.pl }; }
    case "label": return { k: "hole", place: e.pl };
    case "result": return { k: "type", name: M.nameOf(M.nameOf ? { base: M.resultName(e.op) } : null) };
    case "tnode": case "smark": case "kmark": return { k: "type", name: e.name };
    case "port": return { k: "type", name: M.nameOf((function g(x) { return M.ctorOf(x) ? g(x.of) : x; })(e.tree)) };
    case "tchild": return e.kd.k === "member" ? { k: "const", c: e.kd.c } : { k: "type", name: e.kd.name ?? e.of };
    case "fnode": return { k: "fn", name: e.name };
    case "status": return { k: "none", why: "" };
    default: return { k: "none", why: "" };
  }
}
function fitSet(st, t) {   // the functions that take or give what is held, read from the world's declared parameters and results
  const { wx } = RD, F = wx.W.functions, s = new Set(), inner = (x) => (M.ctorOf(x) ? inner(x.of) : x);
  if (t.k === "const" || t.k === "op") { const tn = M.typeOfThing(st, t); for (const f of Object.keys(F)) if (F[f].parameters.some(([, tr]) => M.takes(wx, tr, tn) || (M.ctorOf(tr) === "Many" && M.takes(wx, tr.of, tn)))) s.add(f); }
  else if (t.k === "type") for (const f of Object.keys(F)) if (F[f].parameters.some(([, tr]) => M.takes(wx, tr, t.name) || (M.ctorOf(tr) === "Many" && M.takes(wx, tr.of, t.name))) || M.nameOf(inner(F[f].result)) === t.name) s.add(f);
  return s;
}
function farState(e, st) {
  if (e.t !== "place") return st;
  const pl = e.pl, k = M.kindOf(pl.val);
  if (k !== "const" && k !== "ref") return st;
  const n = pl.member != null ? M.removeAt(st, pl.op, pl.list, pl.member) : M.setAt(st, pl.op, pl.path, M.holeValue(pl, "cleared"));
  return M.recompute(RD.wx, M.sweep(n), RD.base);
}

function draggable({ state: st, d, draggedId }) {
  const L = layout(st); LASTL = L;
  const lit = (id) => LIT.has(id), acc = (id) => ACCEPT.has(id), ref = REFUSED;
  const grabProps = (e) => ({
    id: e.id, transform: translate(e.x, e.y), "data-k": e.id, "data-t": e.t, "data-grab": "1", ...(LIT.has(e.id) ? { "data-lit": "1" } : {}), style: { cursor: "grab" },
    dragologyZIndex: draggedId === e.id ? "/1" : false,
    dragologyOnDrag: () => {
      const th = thingOf(e, st);
      const mv = th.k === "none" || th.k === "type" ? { ok: [], no: [] } : M.movesFor(RD.wx, st, RD.base, th, RD.units);
      $("sel").style.display = "none";
      HELD = { id: e.id, thing: th, mv, base: st, fit: fitSet(st, th), key: e.id };
      ACCEPT = new Set(mv.ok.map((m) => m.target)); REFUSED = Object.fromEntries(mv.no.map((m) => [m.target, m.reason]));
      LIT = litFrom(e.id, L.rel); if (th.k === "type") LIT = new Set([...LIT, ...[...(HELD.fit ?? [])].map((f) => `fn-${f}`)]);
      say(`${mv.ok.length} fit · ${mv.no.length} refused`, true);
      const seen = new Set([e.id]), tgs = [{ target: e.id, state: st }];
      for (const m of mv.ok) if (!seen.has(m.target) && L.box[m.target]) { seen.add(m.target); tgs.push(m); }
      const ov = h("g", null,
        ...mv.ok.filter((m) => L.box[m.target]).map((m, i) => { const b = L.box[m.target]; return h("rect", { dragologyKey: "ok" + i, "data-accepts": m.target, transform: translate(b.x - 3, b.y - 3), width: b.w + 6, height: b.h + 6, rx: 8, fill: "none", stroke: C.accent, strokeWidth: 2.5 }); }),
        ...mv.no.filter((m) => L.box[m.target]).map((m, i) => { const b = L.box[m.target]; const s = m.reason.length > 54 ? m.reason.slice(0, 53) + "…" : m.reason; return h("g", { dragologyKey: "no" + i, "data-why": m.reason, "data-refused": m.target }, h("path", { dragologyKey: "x", d: "M0,0L8,8M8,0L0,8", transform: translate(b.x + b.w - 4, b.y - 4), stroke: C.no, strokeWidth: 2 }), h("text", { dragologyKey: "t", transform: translate(b.x, b.y + b.h + 13), fontFamily: C.code, fontSize: 12, fill: C.no }, s)); }));
      return d.closest(tgs.map((x) => d.dropTarget(x.target, x.state, { boundsState: st }))).whenFar(farState(e, st), { gap: 160 }).withFloating({ ghost: true }).withOverlay(ov);
    },
  });
  const edgeP = (a, b, dy, res) => { const x1 = (a.rx ?? a.x + a.w), y1 = a.y + a.h / 2 + (res ? 4 : -4), x2 = b.x, y2 = b.y + dy; const mx = (x1 + x2) / 2; return `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`; };
  const kids = [];
  kids.push(h("path", { dragologyKey: "divider", d: NAR ? `M0,${L.leftBottom + 8}H${W}` : `M${GX - 36},8V${L.height - 8}`, stroke: C.rule, strokeWidth: 1 }));
  // phrase rules (grouping, quoted ones dashed)
  L.rules.forEach((r, i) => kids.push(h("path", { dragologyKey: "rule" + i, d: `M${r.x1},${r.y - 4}H${r.x2}`, stroke: lit(`ph-${r.ph}`) ? C.accent : C.rule, strokeWidth: 2, ...(RD.r.phrases[r.ph].quotes != null ? { strokeDasharray: "4 3" } : {}) })));
  // edges of the world graph first (under the nodes)
  for (const s of L.struct) kids.push(h("path", { dragologyKey: s.id, d: `M${s.a.x},${s.a.y + s.a.h / 2} C${s.a.x - 22},${s.a.y + s.a.h / 2} ${s.b.x - 22},${s.b.y + s.b.h / 2} ${s.b.x},${s.b.y + s.b.h / 2}`, fill: "none", stroke: lit(s.a.id) && lit(s.b.id) ? C.accent : "#d9dce2", strokeWidth: 1.25, strokeDasharray: s.kind === "alt" ? "" : s.kind === "of" ? "2 3" : "6 3", "data-edge": s.kind }));
  for (const e of L.edges) { const on = lit(e.fn ? `fn-${e.fn}` : "") && lit(e.ty); kids.push(h("path", { dragologyKey: e.id, d: edgeP(e.a, e.b, e.dy, e.kind === "result"), fill: "none", stroke: on ? C.accent : "#e6e8ec", strokeWidth: on ? 2.5 : 1, strokeDasharray: e.kind === "result" ? "5 3" : "", "data-edge": e.kind, "data-fn": e.fn, "data-ty": e.ty })); }
  // reference arcs: from the place to the operation it refers to, the same operation (identity, not a copy)
  for (const a of L.arcs) { const p = L.box[a.from], o = L.box[a.to]; if (!p || !o) continue; const on = lit(a.via) || lit(a.to); kids.push(h("path", { dragologyKey: a.id, d: `M${p.x},${p.y + 16}H${a.lane + 4}V${o.y + 16}H${o.x}`, fill: "none", stroke: on ? C.accent : C.mute, strokeWidth: on ? 2.5 : 1.5, "data-arc": a.to })); }
  for (const e of L.items) {
    const on = lit(e.id), sel = SEL === e.id, ok = acc(e.id), no = !!ref[e.id], stroke = on || sel ? C.accent : C.ink, sw = on || sel ? 2.5 : 1.5;
    switch (e.t) {
      case "unit": kids.push(h("g", { ...grabProps(e), "data-role": e.u.c ? "value" : "word", "data-text": e.u.text },
        h("rect", { dragologyKey: "hit", width: e.w + 4, height: e.h, x: -2, fill: on || sel ? "rgba(29,78,216,.10)" : "transparent", rx: 4 }),
        txt("t", 0, 23, e.u.text, { size: 20, w: e.u.c ? 600 : 400, fill: C.ink }),
        e.u.c ? h("rect", { dragologyKey: "ul", y: 28, width: e.w, height: 3, fill: color(e.u.c.type) }) : null)); break;
      case "op": kids.push(h("g", { ...grabProps(e), "data-role": "op", "data-op": e.row },
        rect("b", e.w, e.h, { fill: C.ink, stroke: on || sel ? C.accent : C.ink, sw: on || sel ? 3 : 1.5, rx: 8 }),
        txt("id", 10, 21, e.row, { code: true, size: 12, w: 600, fill: "#aab0bd" }),
        txt("n", tw(e.row, 12, 600, C.code) + 18, 21, e.op.fn, { w: 600, fill: "#ffffff" }))); break;
      case "label": kids.push(h("g", { ...grabProps(e), "data-role": "label" }, h("rect", { dragologyKey: "hit", width: e.w, height: CH, fill: "transparent" }), txt("t", 0, 21, e.name, { code: true, size: 12, fill: on ? C.accent : C.mute }))); break;
      case "place": { const pl = e.pl, v = pl.val, k = M.kindOf(v), missing = k === "hole" ? "hole" : k === "empty" ? "empty" : pl.emptyList ? "list" : null;
        const dash = k === "hole" ? "5 3" : k === "empty" ? "1.5 3.5" : pl.emptyList ? "8 3" : pl.add ? "2 4" : undefined;
        const tname = k === "const" ? v.type : k === "ref" ? M.resultName(RD.st.ops[v.ref] ?? { type: "?" }) : pl.declared;
        const inside = k === "const" ? [glyph(17, 16, v.type, "g"), txt("t", 30, 21, v.constant, { w: 600 })]
          : k === "ref" ? [txt("a", 10, 22, "↩", {}), txt("id", 10 + tw("↩", 15) + 6, 21, v.ref, { code: true, size: 12, w: 600, fill: C.mute }), txt("n", 10 + tw("↩", 15) + 6 + tw(v.ref, 12, 600, C.code) + 8, 21, RD.st.ops[v.ref]?.fn ?? "?", { w: 600 })]
          : k === "hole" ? [glyph(17, 16, pl.declared, "g"), txt("t", 30, 21, `${pl.declared} · ${v.reason || "open"}`, { size: 14, fill: C.no })]
          : k === "empty" ? [glyph(17, 16, pl.declared, "g"), txt("t", 30, 21, `none ${v.empty}`, { size: 14, fill: C.mute })]
          : pl.add ? (pl.emptyList ? [txt("t", 10, 21, "none", { size: 14, fill: C.mute }), txt("p", 10 + tw("none", 14) + 8, 21, "+", { w: 600 })] : [txt("t", 16, 22, "+", { anchor: "middle", w: 600 })]) : [txt("t", 30, 21, pl.declared, { size: 14 })];
        kids.push(h("g", { ...grabProps(e), "data-role": "place", "data-place": `${pl.op}.${pl.path}`, "data-declared": pl.declared, "data-kind": k, ...(missing ? { "data-missing": missing } : {}), "data-reason": v?.reason ?? "" },
          h("rect", { dragologyKey: "hit", x: -6, y: -6, width: e.w + 12, height: CH + 12, fill: "transparent" }),
          h("rect", { dragologyKey: "b", className: "mark", width: e.w, height: CH, rx: 6, fill: ok ? "rgba(29,78,216,.12)" : k === "const" ? color(v.type) + "26" : k === "ref" ? C.surface : C.bg, stroke: no ? C.no : stroke, strokeWidth: ok ? 2.5 : sw, ...(dash ? { strokeDasharray: dash } : {}) }),
          ...inside)); break; }
      case "result": kids.push(h("g", { ...grabProps(e), "data-role": "result", "data-deferred": String(!!e.op.judg.deferred) },
        rect("b", e.w, e.h, { fill: C.bg, stroke: on || sel ? C.accent : C.rule, sw: on || sel ? 2.5 : 1.5, dash: e.op.judg.deferred ? "5 3" : undefined }),
        glyph(14, 16, M.resultName(e.op).replace(/^(Many|Maybe)\[(.*)\]$/, "$2"), "g"), txt("t", 26, 21, e.op.type, { code: true, size: 13, fill: C.mute }))); break;
      case "status": { const f = flag(e.op);
        kids.push(h("g", { ...grabProps(e), "data-role": "status", "data-flag": f, "data-pending": String(!!e.op.judg.pending), "data-deferred": String(!!e.op.judg.deferred), "data-ready": String(!!e.op.judg.ready), "data-complete": String(!!e.op.judg.complete), ...(e.op.prov ? { "data-provisional": "1" } : {}) },
          h("rect", { dragologyKey: "hit", width: e.w, height: CH, fill: "transparent" }),
          h("circle", { dragologyKey: "c", transform: translate(7, 16), r: 6, fill: f === "ready" ? C.ok : C.bg, stroke: f === "ready" ? C.ok : C.ink, strokeWidth: 1.5, ...(f === "open" ? { strokeDasharray: "2 2" } : {}) }),
          f === "waits" ? h("path", { dragologyKey: "w", d: "M7,12V16H10", fill: "none", stroke: C.ink, strokeWidth: 1.5 }) : null,
          txt("t", 20, 21, flagText(e.op), { code: true, size: 13, fill: e.op.prov ? C.accent : C.ink }))); break; }
      case "unres": kids.push(h("g", { ...grabProps(e), "data-role": "unresolved", "data-missing": "unresolved", "data-reason": e.p.unresolved.reason }, rect("b", e.w, CH, { dash: "10 3 2 3", stroke }), txt("t", 12, 21, `? ${e.p.unresolved.reason}`, { size: 14, w: 600, fill: C.no }))); break;
      case "quote": kids.push(h("g", { ...grabProps(e), "data-role": "quote" }, rect("b", e.w, CH, { dash: "3 3", stroke }), txt("t", 12, 21, `“ ${e.p.quotes}`, { size: 14, w: 600, fill: C.mute }))); break;
      case "tnode": { const t = e.def;
        kids.push(h("g", { ...grabProps(e), "data-role": "type", "data-name": e.name, "data-struct": t.sum ? "sum" : t.product ? "product" : t.brand ? "brand" : "base" },
          rect("b", e.w, 32, { stroke, sw, fill: SEL === e.id ? C.surface : C.bg }), glyph(15, 16, e.name, "g"), txt("t", 28, 21, e.name, { size: 14, w: 600 }))); break; }
      case "smark": { const t = e.def, mark = t.sum ? "|" : t.product ? "×" : t.brand ? "▸" : "·";
        kids.push(h("g", { ...grabProps(e), "data-role": "structure", "data-name": e.name }, rect("b", e.w, 32, { stroke, sw, fill: C.surface }), txt("m", 14, 21, mark, { code: true, size: 14, w: 600, anchor: "middle" }))); break; }
      case "kmark": kids.push(h("g", { ...grabProps(e), "data-role": "kind", "data-name": e.name }, rect("b", e.w, 32, { stroke, sw, fill: C.surface }), txt("k", 8, 21, e.def.kind, { code: true, size: 12, fill: C.mute }))); break;
      case "port": { const tr = e.tree; kids.push(h("g", { ...grabProps(e), "data-role": "port", "data-fn": e.fn, "data-param": e.param },
          rect("b", e.w, 24, { stroke, sw: on || sel ? 2.5 : 1, fill: C.bg, rx: 5 }), h("circle", { dragologyKey: "d", transform: translate(0, 12), r: 4.5, fill: C.bg, stroke: C.ink, strokeWidth: 1.5 }),
          txt("n", 12, 16, `${e.param} : ${M.nameOf(tr)}`, { code: true, size: 12, fill: C.ink }))); break; }
      case "tchild": { const kd = e.kd; kids.push(h("g", { ...grabProps(e), "data-role": kd.k }, rect("b", e.w, 32, { stroke, sw, fill: C.surface, dash: kd.k === "member" ? undefined : "4 3" }), txt("t", 10, 21, kd.text, { code: true, size: 13 }))); break; }
      case "ctor": kids.push(h("g", { ...grabProps(e), "data-role": "constructor" }, rect("b", e.w, 32, { stroke, sw, dash: "2 3" }), txt("t", 14, 21, `${e.name} : ${e.def.kind}`, { size: 14, w: 600 }))); break;
      case "fnode": { const f = e.def, takes = FIT()?.has(e.name);
        kids.push(h("g", { ...grabProps(e), "data-role": "function", "data-name": e.name, ...(takes ? { "data-takes": "1" } : {}) },
          rect("b", e.w, 32, { stroke: takes ? C.accent : stroke, sw: takes ? 2.5 : sw, fill: C.surface }),
          txt("t", 10, 21, e.name, { size: 15, w: 600 }), glyph(e.w - 16, 16, M.nameOf((function f2(t) { return M.ctorOf(t) ? f2(t.of) : t; })(f.result)), "rg"))); break; }
    }
  }
  return h("g", null, ...kids);
}

// ---------- paint, hover, select
function sync() { RD.units = units(RD.r, RD.st.consts); RD.wx = M.indexWorld(M.patchWorld(WORLDS[RD.r.world], RD.st.world)); }
function paint() {
  sync();
  const L0 = layoutHeight();
  root ??= createRoot($("board"));
  root.render(h(DraggableRenderer, { key: RD.i, draggable: (p) => draggable(p), state: structuredClone(RD.st), width: W, height: L0, onDropState: dropped, onDragState: previewed }));
}
const fitView = () => { const sv = document.querySelector("#board svg"); if (sv) { const hh = sv.getAttribute("height"); if (sv.getAttribute("viewBox") !== `0 0 ${W} ${hh}`) sv.setAttribute("viewBox", `0 0 ${W} ${hh}`); } };
new MutationObserver(fitView).observe($("board"), { childList: true, subtree: true, attributes: true, attributeFilter: ["height", "viewBox"] });
const layoutHeight = () => { const L = layout(RD.st); return Math.max(L.height, 200); };
function previewed(next) { if (!HELD) return; const ch = changes(HELD.base, next); say(ch.length ? ch.map((c) => c.text).join("   ·   ") : "no change", false, true); }
function dropped(next) { const was = HELD; HELD = null; ACCEPT = new Set(); REFUSED = {}; LIT = HOVER ? litFrom(HOVER, LASTL?.rel ?? new Map()) : new Set(); const ch = changes(RD.st, next); say(ch.length ? ch.map((c) => c.text).join("   ·   ") : was && was.mv.no.length && !was.mv.ok.length ? "refused" : "", false); commit(next); if (!ch.length) paint(); }
const say = (s, held = false, diff = false) => { $("bar").innerHTML = `<span class="${diff ? "ok" : ""}">${esc(s ?? "")}</span>`; };
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function relight(key) { if (HELD) return; HOVER = key; LIT = litFrom(key ?? SEL, LASTL?.rel ?? new Map()); if (SEL && key) LIT = new Set([...LIT, ...litFrom(SEL, LASTL.rel)]); paint(); }
let hv = null;
document.addEventListener("keydown", (k) => { if (k.key === "Escape" && SEL) { SEL = null; NAV = []; LIT = new Set(); paint(); renderPanel(); } });
addEventListener("resize", () => { if (RD && !HELD) paint(); });
document.addEventListener("pointerover", (e) => { if (HELD || e.buttons) return; const k = e.target.closest?.("#board [data-k]")?.getAttribute("data-k") ?? null; if (k !== hv) { hv = k; relight(k); } });
let down = null;
document.addEventListener("pointerdown", (e) => { const el = e.target.closest?.("#board [data-k]"); down = e.target.closest?.("#board") ? { x: e.clientX, y: e.clientY, k: el?.getAttribute("data-k") ?? null } : null; }, true);
document.addEventListener("pointerup", (e) => { const p = down; down = null; setTimeout(() => { if (HELD) { HELD = null; ACCEPT = new Set(); REFUSED = {}; LIT = litFrom(HOVER ?? SEL, LASTL?.rel ?? new Map()); paint(); placeCard(); } }, 80); if (!p || Math.hypot(e.clientX - p.x, e.clientY - p.y) > 5) return; setTimeout(() => { NAV = []; select(p.k, false); }, 0); }, true);
function select(k, nav = true) { if (k === SEL) return; if (nav && SEL) NAV.push(SEL); SEL = k; HOVER = null; LIT = litFrom(k, LASTL?.rel ?? new Map()); paint(); renderPanel(); }
function go(k) { select(k, true); }
function back() { const k = NAV.pop(); if (k === undefined) return; SEL = k; LIT = litFrom(k, LASTL?.rel ?? new Map()); paint(); renderPanel(); }

// ---------- the panel: what the selected piece is, where it can go and why, in the engine's words
const link = (k, text) => `<a class="go" data-go="${esc(k)}">${esc(text ?? k)}</a>`;
const tlink = (n) => (RD.wx.W.types[n] ? link(`ty-${n}`, n) : esc(n));
function structOf(n) {
  const t = RD.wx.W.types[n]; if (!t) return "";
  const kind = t.sum ? "sum" : t.product ? "product" : t.brand ? "brand" : "base";
  const parts = t.sum ? t.alternatives.map((a) => a.member ? `<span class="chip">${esc(a.words)}</span>` : tlink(M.nameOf(a))).join(" | ") : t.product ? Object.entries(t.fields).map(([f, ft]) => `${esc(f)}: ${tlink(M.nameOf(ft))}`).join(", ") : t.brand ? `wraps ${tlink(M.nameOf(t.of))}` : "";
  const chain = RD.wx.ancestors(n).slice(1);
  return `<div class="row"><span class="k">${kind} · kind</span> <span>${esc(t.kind)}</span> ${chain.length ? `<span class="k">inherits</span> ${chain.map(tlink).join(" ▸ ")}` : ""}</div>${parts ? `<div class="row"><span class="k">${kind === "sum" ? "one of" : kind === "product" ? "all of" : "made of"}</span> ${parts}</div>` : ""}`;
}
function moveButtons(th, from) {
  const mv = M.movesFor(RD.wx, RD.st, RD.base, th, RD.units), off = window.__acts.length; window.__acts.push(...mv.ok);
  const ok = mv.ok.map((m, i) => `<div class="row"><span class="chip ok" data-target="${esc(m.target)}">→ ${esc(m.label)}</span><span class="why">${esc(m.why)}</span><button class="act" data-act="${off + i}">Apply</button></div>`).join("");
  const no = mv.no.map((m) => `<div class="row"><span class="chip no">× ${esc(labelOf(m.target))}</span><span class="why">${esc(m.reason)}</span></div>`).join("");
  return ok + no || `<div class="why">no places</div>`;
}
const labelOf = (id) => id.startsWith("pl-") ? id.slice(3).replace("-", ".") : id.startsWith("u-") ? `“${RD.units.find((u) => u.id === id)?.text}”` : id.startsWith("op-") ? `op ${id.slice(3)}` : id;
const decisionsFor = (c) => RD.r.decisions.filter((d) => d.path != null && ([d.chosen, ...(d.offered ?? [])].some((x) => x && x.constant != null && x.at && c.at && x.at[0] === c.at[0])));
function decRows(d) {
  let h2 = `<div class="row"><span class="chip">${esc(d.by)}</span><span class="why">${esc(d.function ?? "")}${d.operation != null ? " " + d.operation : ""}${d.path ? "." + esc(d.path) : ""} · offered ${d.offered?.length ?? 0} · cut ${d.cut?.length ?? 0} · chose ${esc(typeof d.chosen === "object" && d.chosen ? show(d.chosen) : String(d.chosen))}</span></div>`;
  if (d.rule) h2 += `<div class="why">${esc(d.rule)}</div>`;
  for (const [q, a] of Object.entries(d.asked ?? {})) {
    const pr = d.answers?.[q]?.probabilities ?? {}, opts = [...a.options].sort((x, y) => (pr[y.id] ?? -1) - (pr[x.id] ?? -1)).slice(0, 4);
    h2 += `<div class="why">${esc(a.instructions.slice(0, 90))}${a.instructions.length > 90 ? "…" : ""}</div>` + opts.map((o) => `<div class="row"><span class="bar" style="width:${Math.round((pr[o.id] ?? 0) * 120)}px"></span><span class="why">${pr[o.id] == null ? "–" : Math.round(pr[o.id] * 100)}</span><span>${esc(o.id)}</span><span class="why">${esc((o.description || "").slice(0, 44))}</span></div>`).join("");
  }
  return h2;
}
function judgText(o) { const j = o.judg; return `<span class="chip">${j.valid === false ? "invalid" : "valid"}</span> <span class="chip">${j.complete ? "complete" : "open"}</span> <span class="chip">${j.pending ? "pending" : "available"}</span> ${j.deferred ? `<span class="chip">deferred</span>` : ""} <span class="chip">${j.ready ? "ready" : "waits"}</span> ${o.prov ? `<span class="prov">≈ provisional</span>` : `<span class="why">engine</span>`}${(j.diagnostics ?? []).length ? `<div class="why">${esc(JSON.stringify(j.diagnostics))}</div>` : ""}`; }
function renderPanel() {
  window.__acts = [];
  const st = RD.st, { wx, r } = RD, F = wx.W.functions, k = SEL;
  let html = `<nav class="crumb">${NAV.length ? `<button class="act" data-back="1">Back</button>` : ""}</nav>`;
  const row = (kk, v) => `<div class="row"><span class="k">${kk}</span><span>${v}</span></div>`;
  if (!k) html += `<div class="why"></div>`;
  else if (k.startsWith("u-")) {
    const u = RD.units.find((x) => x.id === k), ph = r.phrases[u.phrase], W0 = wx.W;
    const act = (state, label, why, ok = true) => { const i = window.__acts.push({ state, label, why }) - 1; return `<div class="row"><span class="chip ${ok ? "ok" : "no"}">${esc(label)}</span><span class="why">${esc(why)}</span>${ok ? `<button class="act" data-act="${i}">Apply</button>` : ""}</div>`; };
    html += `<div class="row"><b>${esc(u.text)}</b>${u.c ? ` : ${tlink(u.c.type)} <span class="chip">${esc(W0.types[u.c.type]?.kind ?? "")}</span>` : ""}</div>`;
    html += row("phrase", `${esc(ph.brand)} · ${esc(ph.starts_by)}${ph.quotes != null ? ` · quote ${ph.quotes}` : ""}`);
    if (u.c) {
      const holders = M.places(wx, st).filter((p) => p.val?.constant != null && p.val.at && u.c.at && p.val.at[0] === u.c.at[0]);
      html += row("bound in", holders.map((p) => link(p.id, `${p.op}.${p.path}`) + ` ${link(`op-${p.op}`, st.ops[p.op].fn)} <span class="chip">${esc(flagText(st.ops[p.op]))}</span>`).join(" · ") || "nowhere");
      const why = holders.map((p) => st.ops[p.op]).filter((o) => M.refsIn(o).length).map((o) => `${o.fn} reads ${M.refsIn(o).join(", ")}`);
      if (why.length) html += row("waits on", esc(why.join(" · ")));
      html += `<h3>the model's reading</h3>` + (decisionsFor(u.c).map((d) => decRows(d)).join("") || `<div class="why">none recorded</div>`);
      html += `<h3>type</h3>` + structOf(u.c.type);
      const fnsT = [...fitSet(st, { k: "const", c: u.c })]; html += row("taken by", fnsT.map((f) => link(`fn-${f}`, f)).join(" ") || "—");
      html += `<h3>where it goes</h3>` + moveButtons({ k: "const", c: u.c });
      const rt = M.retagOptions(u.c, W0).filter((x) => x.type !== u.c.type);
      html += `<h3>retag</h3>` + (rt.map((x) => { const n2 = M.replaceConst(st, u.c.at, { ...u.c, type: x.type }), bad = M.places(M.indexWorld(W0), n2).filter((p) => p.val?.constant != null && p.val.at?.[0] === u.c.at[0] && !M.fits(wx, n2, p, { k: "const", c: { ...u.c, type: x.type } }).ok).map((p) => `${p.op}.${p.path}`); return act(n2, `as ${x.type}`, `member ${x.member}${bad.length ? `; stops fitting: ${bad.join(", ")}` : ""} ≈`); }).join("") || `<div class="why">only ${esc(u.c.type)} has “${esc(u.c.constant)}”</div>`);
      html += `<h3>span</h3>` + M.spanOptions(r.text, u.c, W0).map((o) => act(o.ok ? M.replaceConst(st, u.c.at, { constant: o.words, type: o.type, at: o.at }) : st, `${o.label} → “${o.words}”`, o.why + (o.ok ? " ≈" : ""), o.ok)).join("");
    } else {
      const id = st.order.find((o) => st.ops[o].phrase === u.phrase);
      html += id != null ? row("tagged", link(`op-${id}`, `${st.ops[id].fn} ${id}`) + ` <span class="chip">${esc(flagText(st.ops[id]))}</span>`) : row("tagged", esc(ph.unresolved ? `unresolved · ${ph.unresolved.reason}` : "quoted"));
      if (id != null) html += `<h3>the model's reading</h3>` + (r.decisions.filter((d) => String(d.operation) === id && d.path == null && Object.keys(d.asked ?? {}).length).slice(0, 1).map((d) => decRows(d)).join("") || `<div class="why">none recorded</div>`);
      if (/[A-Za-z]/.test(u.text)) {
        const sums = Object.entries(W0.types).filter(([, t]) => t.sum).map(([n]) => n);
        html += `<h3>add as a value</h3>` + sums.map((n) => { const st2 = structuredClone(st); st2.world = [...(st.world ?? []), { type: n, member: u.text.toUpperCase().replace(/\W+/g, "_"), words: u.text }]; st2.consts = [...st2.consts, { constant: u.text, type: n, at: [u.start, u.end] }].sort((a, b) => a.at[0] - b.at[0]); return act(st2, `member of ${n}`, `world draft: ${n} gains “${u.text}” ≈ gated`); }).join("");
      }
    }
  } else if (k.startsWith("pl-")) {
    const pl = M.places(wx, st).find((p) => p.id === k); if (!pl) return void ($("sel").innerHTML = "");
    const v = pl.val, kind = M.kindOf(v);
    html += `<div class="row"><b>${esc(pl.op)}.${esc(pl.path)}</b> : ${tlink(M.nameOf(pl.tree.of && M.ctorOf(pl.tree) ? pl.tree.of : pl.tree))}${M.ctorOf(pl.tree) ? ` <span class="chip">${esc(M.ctorOf(pl.tree))}</span>` : ""}</div>`;
    html += row("holds", `${esc(kind)} ${esc(show(v))}`);
    if (kind === "hole") html += row("reason", esc(v.reason || "none recorded"));
    if (kind === "ref") html += row("refers to", link(`op-${v.ref}`, `${st.ops[v.ref]?.fn} ${v.ref}`) + ` <span class="why">same operation, not a copy</span>`);
    html += row("operation", link(`op-${pl.op}`, `${st.ops[pl.op].fn} ${pl.op}`));
    html += structOf(M.nameOf(pl.tree.of && M.ctorOf(pl.tree) ? pl.tree.of : pl.tree));
    const th = kind === "const" ? { k: "const", c: v, from: pl.id } : kind === "ref" ? { k: "op", id: v.ref, from: pl.id } : { k: "hole", place: pl };
    if (kind === "const" || kind === "ref") html += `<h3>rebind to</h3>` + moveButtons({ k: "hole", place: pl }); html += `<h3>${kind === "hole" || kind === "empty" || pl.add ? "what fits" : "where it goes"}</h3>` + moveButtons(th);
    const ds = r.decisions.filter((d) => String(d.operation) === pl.op && d.path === pl.path.split(".").slice(0, 1).join(".") || (d.operation != null && String(d.operation) === pl.op && d.path === pl.path));
    if (ds.length) html += `<h3>decided</h3>` + ds.map((d) => `<div class="row"><span class="chip">${esc(d.by)}</span><span class="why">${esc(d.rule || "")} offered ${d.offered.length} · cut ${d.cut.length} · chose ${esc(typeof d.chosen === "object" ? show(d.chosen) : d.chosen)}</span></div>`).join("");
  } else if (k.startsWith("op-")) {
    const o = st.ops[k.slice(3)]; if (!o) return void ($("sel").innerHTML = "");
    const f = F[o.fn];
    html += `<div class="row"><b>${esc(o.fn)}</b> <span class="chip">${esc(o.id)}</span>${o.isNew ? ` <span class="prov">≈ new, provisional</span>` : ""}</div>`;
    html += row("asks", esc(f.asks)); html += row("signature", `${f.parameters.map(([p, tr]) => `${esc(p)}: ${tlink(M.nameOf(tr))}`).join(", ")} → ${tlink(M.nameOf(f.result))}`);
    html += row("result", esc(o.type)); html += row("flags", judgText(o));
    html += row("because", `${o.judg.complete ? "no hole" : "a hole is open"} · ${o.judg.deferred ? "result is Later" : "result now"} · ${M.refsIn(o).length ? "reads " + M.refsIn(o).map((x) => link(`op-${x}`, x)).join(" ") : "reads no operation"}`);
    html += row("places", M.places(wx, st).filter((p) => p.op === o.id).map((p) => link(p.id, p.path)).join(" "));
    html += `<h3>where its result goes</h3>` + moveButtons({ k: "op", id: o.id });
  } else if (k.startsWith("pt-")) {
    const [, f, p] = k.split("-"), tr = F[f].parameters.find(([x]) => x === p)[1], tn = M.nameOf((function g(x) { return M.ctorOf(x) ? g(x.of) : x; })(tr));
    html += `<div class="row"><b>${esc(f)}.${esc(p)}</b> : ${tlink(M.nameOf(tr))}</div>` + row("function", link(`fn-${f}`, f)) + row("declared", tlink(tn) + (M.ctorOf(tr) ? ` <span class="chip">${esc(M.ctorOf(tr))}</span>` : ""));
    html += row("filled by", st.order.filter((o) => st.ops[o].fn === f).map((o) => link(`pl-${o}-${p}`, `${o}.${p}`)).join(" ") || "no operation") + structOf(tn);
  } else if (k.startsWith("kd-")) {
    const n = k.slice(3), t = wx.W.types[n], same = Object.keys(wx.W.types).filter((x) => wx.W.types[x].kind === t.kind);
    html += `<div class="row"><b>${esc(n)}</b> : <span class="chip">${esc(t.kind)}</span></div>` + row("kind", `${esc(t.kind)} · a type with no argument`) + row("same kind", same.map(tlink).join(" ")) + row("makes", Object.entries(wx.W.constructors).map(([c, d]) => link(`ct-${c}`, `${c} : ${d.kind}`)).join(" "));
  } else if (k.startsWith("ty-") || k.startsWith("mb-") || k.startsWith("sm-")) {
    const n = /^(ty|sm)-/.test(k) ? k.slice(3) : k.split("-")[1], t = wx.W.types[n];
    html += `<div class="row"><b>${esc(n)}</b></div>` + structOf(n);
    const takes = Object.keys(F).filter((f) => F[f].parameters.some(([, tr]) => M.nameOf((function g(x) { return M.ctorOf(x) ? g(x.of) : x; })(tr)) === n)), gives = Object.keys(F).filter((f) => M.nameOf((function g(x) { return M.ctorOf(x) ? g(x.of) : x; })(F[f].result)) === n);
    html += row("taken by", takes.map((f) => link(`fn-${f}`, f)).join(" ") || "—"); html += row("given by", gives.map((f) => link(`fn-${f}`, f)).join(" ") || "—");
    const cs = Object.keys(wx.W.constructors).filter((c) => Object.values(F).some((f) => f.parameters.some(([, tr]) => M.ctorOf(tr) === c && M.nameOf(tr.of) === n)));
    if (cs.length) html += row("applied", cs.map((c) => link(`ct-${c}`, `${c}[${n}]`)).join(" "));
    html += `<div class="why">view only: world edits are a separate, gated operation</div>`;
  } else if (k.startsWith("fn-")) {
    const n = k.slice(3), f = F[n];
    html += `<div class="row"><b>${esc(n)}</b></div>` + row("asks", esc(f.asks)) + row("takes", f.parameters.map(([p, tr]) => `${esc(p)}: ${tlink(M.nameOf(tr))}`).join(", ")) + row("gives", tlink(M.nameOf(f.result)));
    html += row("used by", st.order.filter((o) => st.ops[o].fn === n).map((o) => link(`op-${o}`, o)).join(" ") || "no operation");
    html += `<h3>apply to</h3>` + moveButtons({ k: "fn", name: n }) + `<div class="prov">≈ the engine builds the new operation</div>`;
  } else if (k.startsWith("ct-")) {
    const c = k.slice(3), d = wx.W.constructors[c];
    html += `<div class="row"><b>${esc(c)}</b> : ${esc(d.kind)}</div>` + row("means", esc(d.describes));
  } else if (k.startsWith("lb-")) {
    const [, op, name] = k.split("-"), pl = M.places(wx, st).find((p) => p.op === op && p.path.split(".")[0] === name);
    html += `<div class="row"><b>${esc(op)}.${esc(name)}</b> : ${tlink(M.nameOf(M.ctorOf(pl.tree) ? pl.tree.of : pl.tree))}</div>` + row("function", link(`fn-${st.ops[op].fn}`, st.ops[op].fn)) + `<h3>what fits</h3>` + moveButtons({ k: "hole", place: pl });
  } else if (k.startsWith("rs-")) { const o = st.ops[k.slice(3)]; html += `<div class="row"><b>${esc(o.type)}</b></div>` + row("of", link(`op-${o.id}`, `${o.fn} ${o.id}`)) + structOf(M.resultName(o).replace(/^(Many|Maybe)\[(.*)\]$/, "$2")); }
  else if (k.startsWith("st-")) { const o = st.ops[k.slice(3)]; html += `<div class="row"><b>${esc(flag(o))}</b> ${link(`op-${o.id}`, o.fn + " " + o.id)}</div>` + row("flags", judgText(o)); }
  else if (k.startsWith("un-")) { const p = r.phrases[Number(k.slice(3))]; html += `<div class="row"><b>unresolved</b></div>` + row("reason", esc(p.unresolved.reason)) + row("id", esc(String(p.unresolved.id))) + row("text", esc(r.text.slice(p.start, p.end))) + `<div class="why">owed work: no operation is known for this request</div>`; }
  else if (k.startsWith("qt-")) { const p = r.phrases[Number(k.slice(3))]; html += `<div class="row"><b>quote ${esc(String(p.quotes))}</b></div>` + row("text", esc(r.text.slice(p.start, p.end))); }
  const closed = /^(type|retag|span|add as a value|rebind to|decided)$/;
  html = html.replace(/<h3>(.*?)<\/h3>([\s\S]*?)(?=<h3>|$)/g, (_, t, body) => `<details${closed.test(t) ? "" : " open"}><summary>${t}</summary>${body}</details>`);
  $("sel").innerHTML = (k ? `<button class="act" data-close="1" style="float:right">✕</button>` : "") + html;
  placeCard();
  renderDecisions();
}
$("sel").addEventListener("click", (e) => { const a = e.target.closest("[data-go]"); if (a) return go(a.getAttribute("data-go")); if (e.target.closest("[data-close]")) { SEL = null; NAV = []; LIT = new Set(); paint(); return renderPanel(); } if (e.target.closest("[data-back]")) return back(); const b = e.target.closest("[data-act]"); if (b) { const m = window.__acts[Number(b.getAttribute("data-act"))]; if (m) commit(m.state); } });

// ---------- decisions: step through what the model was asked and answered, recorded in the reading
function decKey(d) { if (d.operation != null && d.path) return `pl-${d.operation}-${d.path}`; if (d.operation != null) return `op-${d.operation}`; return null; }
function placeCard() {
  const c = $("sel"), st = $("stage");
  if (!SEL || HELD) { c.style.display = "none"; return; }
  setTimeout(() => { const el = document.querySelector(`#board [data-k="${SEL}"]`); if (!el || !SEL) { c.style.display = "none"; return; }
    const r = el.getBoundingClientRect(), sr = st.getBoundingClientRect(); c.style.display = "block";
    const w = c.offsetWidth, left = Math.max(0, Math.min(r.left - sr.left, sr.width - w)), below = r.bottom - sr.top + 10;
    c.style.left = left + "px"; c.style.top = below + "px"; }, 150);
}
function renderDecisions() {
  const ds = RD.r.decisions, n = ds.length; if (STEP != null) STEP = Math.min(STEP, n - 1);
  let html = `<div class="row"><button class="act" data-step="-1">‹</button><span class="chip">${STEP == null ? "–" : STEP + 1} / ${n}</span><button class="act" data-step="1">›</button></div>`;
  if (STEP != null) {
    const d = ds[STEP];
    html += `<div class="row"><span class="chip">${esc(d.by)}</span><span class="why">${esc(d.state)}</span></div>`;
    if (d.rule) html += `<div class="why">${esc(d.rule)}</div>`;
    for (const [q, a] of Object.entries(d.asked ?? {})) {
      html += `<pre class="q">${esc(a.instructions)}</pre>`;
      const pr = d.answers?.[q]?.probabilities ?? {};
      html += a.options.map((o) => { const p = pr[o.id]; return `<div class="row"><span class="bar" style="width:${Math.round((p ?? 0) * 120)}px"></span><span class="why">${p == null ? "–" : Math.round(p * 100)}</span><span>${esc(o.id)}</span><span class="why">${esc((o.description || "").slice(0, 60))}</span></div>`; }).join("");
    }
    if (d.function || d.operation != null) html += `<div class="why">${esc(d.function ?? "")} ${d.operation ?? ""} ${esc(d.path ?? "")} · offered ${d.offered.length} · cut ${d.cut.length} · chose ${esc(typeof d.chosen === "object" ? show(d.chosen) : String(d.chosen))}</div>`;
  }
  const kept = RD.st.log ?? [];
  if (kept.length) html += `<h3>corrections</h3>` + kept.map((c) => `<div class="row"><span class="chip">${esc(c.operation)}${c.path ? "." + esc(c.path) : ""}</span><span>${esc(c.value)}</span><span class="prov">${esc(c.status)}</span></div>`).join("");
  $("dec").innerHTML = html;
}
$("dec").addEventListener("click", (e) => { const b = e.target.closest("[data-step]"); if (!b) return; const n = RD.r.decisions.length, dlt = Number(b.getAttribute("data-step")); STEP = STEP == null ? (dlt > 0 ? 0 : n - 1) : Math.max(0, Math.min(n - 1, STEP + dlt)); const d = RD.r.decisions[STEP], key = decKey(d); renderDecisions(); if (key && LASTL?.box[key]) { SEL = key; NAV = []; LIT = litFrom(key, LASTL.rel); paint(); renderPanel(); renderDecisions(); } else { const u = d.state ? RD.units.find((x) => RD.r.phrases[x.phrase] && RD.r.text.slice(RD.r.phrases[x.phrase].start, RD.r.phrases[x.phrase].end).trim().startsWith(d.state.slice(0, 6))) : null; if (u) { LIT = new Set(RD.units.filter((x) => x.phrase === u.phrase).map((x) => x.id)); paint(); } } });
$("undo").onclick = undo; $("redo").onclick = redo; $("reset").onclick = revert;
document.addEventListener("keydown", (k) => { if ((k.metaKey || k.ctrlKey) && k.key.toLowerCase() === "z") { k.preventDefault(); k.shiftKey ? redo() : undo(); } });

// ---------- boot: the engine's own files
(async () => {
  const get = async (u) => M.parseEngine(await (await fetch(u)).text());
  [READINGS, WORLDS] = await Promise.all([get("engine/readings.json"), get("engine/worlds.json")]);
  $("pick").innerHTML = READINGS.map((r, i) => `<option value="${i}">${esc(r.case)} · ${esc(r.text.length > 80 ? r.text.slice(0, 79) + "…" : r.text)}</option>`).join("");
  $("pick").onchange = () => open(Number($("pick").value));
  window.BOARD = { READINGS, WORLDS, open, get RD() { return RD; }, get L() { return LASTL; }, select, paint, get HELD() { return HELD; } };
  open(0);
  window.dispatchEvent(new Event("board-ready"));
})();
})();
