"use strict";
// The board: the message itself is the object. Everything the page knows comes from the engine (GET /readings /worlds /log,
// POST /edit /accept /restore /rerun). The page computes no fit, validity, readiness or pending: it shows what the engine answered.
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
const FIXTURE = "stand-in d1 fixture score";

const S = { lines: [], worlds: {}, log: [], id: null, base: null, pending: null, sel: null, open: null, typeView: null, carry: null, note: "", rerun: null, occ: new Map() };

// ---- the engine's records ----
const latest = id => S.lines.filter(l => l.id === id).at(-1);
const snapshotsOf = id => S.lines.map((l, i) => ({ l, n: i + 1 })).filter(x => x.l.id === id);
const terms = r => r.phrases.flatMap(p => p.terms);
const termById = (r, id) => terms(r).find(t => t.id === id);
const phraseOf = (r, id) => r.phrases.find(p => p.terms.some(t => t.id === id));
const world = () => S.worlds[S.base.world];
const view = () => (S.pending && S.pending.draft) || S.base;
const leaves = (v, path) => v.fields ? Object.entries(v.fields).flatMap(([k, x]) => leaves(x, path + "." + k)) : [{ path, value: v }];
const places = t => Object.entries(t.arguments).flatMap(([k, v]) => leaves(v, k));
const constantsIn = v => v.constant !== undefined ? [v] : v.several ? v.several.flatMap(constantsIn) : v.fields ? Object.values(v.fields).flatMap(constantsIn) : [];
const placeType = (t, p) => t.parameters[p.path] || p.value.type || p.value.hole || p.value.empty || "";
const key = { op: id => `o:${id}`, place: (id, path) => `p:${id}:${path}`, val: at => `v:${at[0]}-${at[1]}`, word: s => `w:${s}` };
const say = (v, r) => v.constant !== undefined ? `“${v.constant}”` : v.ref !== undefined ? `the result of ${(termById(r, v.ref) || {}).function || "#" + v.ref}`
  : v.hole ? `open ${v.hole} (${v.reason})` : v.empty ? `absent (${v.empty})` : v.several ? "[" + v.several.map(x => say(x, r)).join(", ") + "]"
  : v.fields ? "{" + Object.entries(v.fields).map(([k, x]) => `${k}: ${say(x, r)}`).join(", ") + "}" : JSON.stringify(v);
const ready = t => { const j = t.judgments || {}; return !j.valid ? "invalid" : !j.complete ? "incomplete" : j.ready ? "ready" : j.pending ? "waits" : ""; };
const correctionAt = (r, id, path) => r.corrections.find(c => String(c.operation) === id && c.path === path);
const stopLine = () => S.log.filter(l => l.event === "Stop" && l.reading === S.id && l.outcomes).at(-1);
const outcomeOf = (r, id) => (r.fulfillment || []).find(o => String(o.obligation) === id);

async function load() {
  const [lines, worlds, log] = await Promise.all(["/readings", "/worlds", "/log"].map(u => fetch(u).then(x => x.json())));
  Object.assign(S, { lines, worlds, log });
  if (!S.id) S.id = new URLSearchParams(location.search).get("r") || lines.at(-1).id;
  S.base = latest(S.id);
  const ids = [...new Set(lines.map(l => l.id))], pick = $("#pick");
  pick.hidden = ids.length < 2;
  pick.replaceChildren(...ids.map(i => el("option", { value: i, selected: i === S.id }, latest(i).text.slice(0, 48))));
}

// ---- the text layer: words, bricks, sockets ----
function words(parent, from, to, text) {
  let pos = from;
  for (const piece of text.slice(from, to).split(/(\s+)/)) {
    if (!piece) continue;
    if (/^\s+$/.test(piece)) parent.append(piece);
    else parent.append(el("span", { class: "w", "data-key": key.word(pos), "data-w": pos, "data-kind": "word" }, piece));
    pos += piece.length;
  }
}

function render() {
  const r = view(), t = $("#text"), base = S.base;
  t.replaceChildren();
  // value occurrences by span: one occurrence can be bound at several places
  S.occ = new Map();
  for (const op of terms(r)) for (const p of places(op)) for (const c of constantsIn(p.value)) {
    const k = key.val(c.at), o = S.occ.get(k) || { at: c.at, constant: c.constant, type: c.type, term: c, binds: [] };
    o.binds.push({ op, path: p.path, own: !!p.value.constant !== false && p.value.constant !== undefined, inSeveral: p.value.constant === undefined });
    S.occ.set(k, o);
  }
  const changed = S.pending && S.pending.draft ? changedKeys(base, r) : new Set();
  const ownPhrase = (op) => phraseOf(r, op.id);
  const range = (parent, from, to, phrase) => {
    const occs = [...S.occ.values()].filter(o => o.at[0] >= from && o.at[1] <= to).sort((a, b) => a.at[0] - b.at[0]);
    let pos = from;
    for (const o of occs) {
      if (o.at[0] < pos) continue;
      words(parent, pos, o.at[0], r.text);
      const here = o.binds.filter(b => phrase && ownPhrase(b.op) === phrase && !b.inSeveral);
      const v = el("span", { class: "val", tabindex: 0, role: "button", "data-key": key.val(o.at), "data-kind": "value", "data-drag": 1,
        "aria-label": `“${o.constant}”, a ${o.type}. Enter to inspect, Space to pick up and use elsewhere.` }, el("span", { "data-text": 1 }, r.text.slice(o.at[0], o.at[1])));
      for (const b of here) v.append(placeLabel(b.op, b.path, "pl", changed, r));
      parent.append(v);
      pos = o.at[1];
    }
    words(parent, pos, to, r.text);
  };
  let pos = 0;
  for (const p of r.phrases) {
    range(t, pos, p.start, null);
    const ph = el("span", { class: "ph" + (p.unresolved.length ? " unres" : ""), "data-phrase": p.start });
    for (const op of p.terms) ph.append(opTag(op, r, changed));
    for (const u of p.unresolved) ph.append(el("span", { class: "op", "data-kind": "unresolved", tabindex: 0, role: "button", "data-key": `u:${u.id}`, "aria-label": `unresolved request ${u.reason}` }, "? ", el("span", { class: "ty" }, u.reason)));
    for (const op of p.terms) for (const pl of places(op)) {  // sockets sit on the operation's stud, so a brick wraps as one piece
      const c = pl.value.constant !== undefined ? pl.value : null;
      if (c && c.at[0] >= p.start && c.at[1] <= p.end) continue;
      if (pl.value.several && pl.value.several.length) continue;
      ph.append(socket(op, pl, r, changed));
    }
    range(ph, p.start, p.end, p);
    t.append(ph);
    pos = p.end;
  }
  range(t, pos, r.text.length, null);
  restoreMarks();
  drawCard();
  requestAnimationFrame(drawArcs);
  $("#snap").textContent = snapLabel();
  $("#older").disabled = $("#rerun").disabled = !!S.pending;
}

function opTag(op, r, changed) {
  const st = ready(op), o = outcomeOf(r, op.id), tags = [];
  if (st) tags.push(el("span", { class: "st " + st }, st));
  if (o) tags.push(el("span", { class: "st " + o.outcome }, o.outcome));
  return el("span", { class: "op" + (changed.has(key.op(op.id)) ? " chg" : ""), tabindex: 0, role: "button", "data-kind": "op", "data-op": op.id, "data-drag": 1, "data-key": key.op(op.id),
    "aria-label": `operation ${op.function}, result ${op.type}${st ? ", " + st : ""}${o ? ", stop check " + o.outcome : ""}. Enter to inspect, Space to pick up its result.` },
    op.function, el("span", { class: "ty prop" }, "→ " + op.type), ...tags);
}

function placeLabel(op, path, cls, changed, r) {
  const c = correctionAt(r, op.id, path), k = key.place(op.id, path);
  return el("span", { class: cls + (changed.has(k) ? " chg" : ""), tabindex: 0, role: "button", "data-place": k, "data-op": op.id, "data-path": path, "data-kind": "place", "data-key": k,
    "aria-label": `place ${path} of ${op.function}, type ${op.parameters[path.split(".")[0]] || ""}${c ? ", corrected by you" : ""}. Enter to inspect.` }, path, c ? el("span", { class: "mark" }, c.status === "invalidated" ? "✎✕" : "✎") : null);
}

function socket(op, pl, r, changed) {
  const v = pl.value, c = correctionAt(r, op.id, pl.path), k = key.place(op.id, pl.path);
  const what = v.ref !== undefined ? ["←", (termById(r, v.ref) || {}).function || "?"] : v.constant !== undefined ? ["↖", ""] : v.hole ? ["?", v.reason] : v.empty ? ["∅", "absent"] : ["", ""];
  const s = el("span", { class: "sock" + (v.hole ? " hole" : "") + (changed.has(k) ? " chg" : ""), tabindex: 0, role: "button", "data-place": k, "data-op": op.id, "data-path": pl.path, "data-kind": "place", "data-key": k,
    "data-target": v.ref !== undefined ? key.op(v.ref) : v.constant !== undefined ? key.val(v.at) : "",
    "aria-label": `place ${pl.path} of ${op.function}: ${say(v, r)}${c ? ", corrected by you" : ""}. Enter to inspect.` },
    pl.path, " ", el("span", { class: "arrow" }, what[0]), what[1] ? " " + what[1] : "", c ? el("span", { class: "mark" }, c.status === "invalidated" ? "✎✕" : "✎") : null);
  return s;
}

function drawArcs() {
  const svg = $("#arcs"), box = $("#stage").getBoundingClientRect();
  svg.replaceChildren();
  svg.setAttribute("viewBox", `0 0 ${box.width} ${box.height}`);
  for (const s of document.querySelectorAll(".sock[data-target]")) {
    if (!s.dataset.target) continue;
    const t = document.querySelector(`[data-key="${CSS.escape(s.dataset.target)}"]`);
    if (!t) continue;
    const a = s.getBoundingClientRect(), b = t.getBoundingClientRect();
    const x1 = a.left + a.width / 2 - box.left, y1 = a.top - box.top, x2 = b.left + b.width / 2 - box.left, y2 = b.top - box.top;
    const on = S.sel && (S.sel.key === s.dataset.key || S.sel.key === s.dataset.target);
    const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
    p.setAttribute("d", `M${x1},${y1} C${x1},${Math.min(y1, y2) - 34} ${x2},${Math.min(y1, y2) - 34} ${x2},${y2}`);
    if (on) p.setAttribute("class", "on");
    svg.append(p);
  }
}
addEventListener("resize", () => requestAnimationFrame(drawArcs));

// what the engine's draft changed, for marking the text: places and operations whose bindings or judgments differ
function changedKeys(a, b) {
  const out = new Set();
  for (const c of diff(a, b)) if (c.key) out.add(c.key);
  return out;
}
const JUDGE = ["valid", "complete", "pending", "deferred", "ready"];
function diff(a, b) {
  const out = [], ta = new Map(terms(a).map(t => [t.id, t])), tb = new Map(terms(b).map(t => [t.id, t]));
  for (const [id, t] of tb) {
    if (!ta.has(id)) { out.push({ text: `new operation ${t.function}`, key: key.op(id) }); continue; }
    const u = ta.get(id), pa = Object.fromEntries(places(u).map(p => [p.path, p.value])), pb = Object.fromEntries(places(t).map(p => [p.path, p.value]));
    for (const path of new Set([...Object.keys(pa), ...Object.keys(pb)])) {
      const x = pa[path] ? say(pa[path], a) : "(none)", y = pb[path] ? say(pb[path], b) : "(none)";
      if (x !== y) out.push({ text: `${t.function}.${path}`, was: x, now: y, key: key.place(id, path) });
    }
    for (const j of JUDGE) if ((u.judgments || {})[j] !== (t.judgments || {})[j]) out.push({ text: `${t.function} · ${j}`, was: String((u.judgments || {})[j]), now: String((t.judgments || {})[j]), key: key.op(id) });
    const da = ((u.judgments || {}).diagnostics || []).length, db = ((t.judgments || {}).diagnostics || []).length;
    if (da !== db) out.push({ text: `${t.function} · diagnostics`, was: String(da), now: String(db), key: key.op(id) });
  }
  for (const [id, t] of ta) if (!tb.has(id)) out.push({ text: `operation ${t.function} removed` });
  if (a.fulfillment && !b.fulfillment) out.push({ text: "the earlier Stop check no longer applies (the engine clears it on any edit)" });
  return out;
}

// ---- engine previews: one rule, the engine's ----
const ask = async body => { const r = await api("/edit", body); return { body, draft: r.draft || null, diagnostics: r.diagnostics || [], error: r.error }; };
const okay = r => r.draft && !r.diagnostics.length && !r.error;
const sourceOf = (el_) => {
  if (el_.dataset.kind === "value") { const o = S.occ.get(el_.dataset.key); return { key: el_.dataset.key, label: `“${o.constant}”`, value: o.term, from: o.binds.map(b => key.place(b.op.id, b.path)) }; }
  const op = termById(S.base, el_.dataset.op);
  return { key: el_.dataset.key, label: `the result of ${op.function}`, value: { ref: op.id }, from: [] };
};
function targetsOf(src) {
  const list = [];
  for (const op of terms(S.base)) for (const p of places(op)) if (p.value.several === undefined) list.push({ op, p, k: key.place(op.id, p.path) });
  return list;
}
function previewAll(src) {
  const results = new Map();
  const job = Promise.all(targetsOf(src).map(async tg => {
    if (src.from.includes(tg.k)) { results.set(tg.k, { here: true }); return; }
    results.set(tg.k, await ask({ reading: S.id, number: +tg.op.id, path: tg.p.path, value: src.value }));
  }));
  return { results, job, src };
}
const fitWord = r => r.here ? "already here" : okay(r) ? "fits" : r.draft === null && r.diagnostics.length ? `refused: ${r.diagnostics.map(d => d[2]).join(", ")}` : r.error || "refused";

// ---- selection and the card ----
const find = k => document.querySelector(`[data-key="${CSS.escape(k)}"]`);
function select(k, kind, extra = {}) {
  S.sel = { key: k, kind, ...extra }; S.open = null; S.typeView = null; S.rerun = null;
  render(); markSel(); find(k)?.focus();
}
function markSel() { document.querySelectorAll(".sel").forEach(e => e.classList.remove("sel")); if (S.sel) find(S.sel.key)?.classList.add("sel"); drawArcs(); }
function closeCard() { const k = S.sel && S.sel.key; S.sel = null; S.open = null; S.typeView = null; S.rerun = null; render(); if (k) find(k)?.focus(); }

function placeCard(c, anchor) {
  const stage = $("#stage").getBoundingClientRect(), a = anchor ? anchor.getBoundingClientRect() : { left: stage.left, bottom: stage.top + 40, top: stage.top };
  c.hidden = false;
  c.style.left = Math.max(0, Math.min(a.left - stage.left, stage.width - Math.min(420, stage.width) - 4)) + "px";
  c.style.top = (a.bottom - stage.top + 10) + "px";
}

function rel(id, k, v, body) {
  const open = S.open === id;
  const li = el("li", {}, el("button", { class: "rel", "aria-expanded": open, "data-rel": id, onclick: () => { S.open = open ? null : id; drawCard(); $(`[data-rel="${CSS.escape(id)}"]`)?.focus(); } },
    el("span", { class: "k" }, k), el("span", { class: "v" }, v), el("span", { class: "c" }, open ? "−" : "+")));
  if (open) { const b = el("div", { class: "body" }); body(b); li.append(b); }
  return li;
}
const go = (label, fn) => el("button", { class: "link", onclick: fn }, label);
const tname = n => el("button", { class: "link", onclick: () => { S.typeView = n; drawCard(); } }, n);

function scoreRows(d) {
  const out = [];
  for (const [q, spec] of Object.entries(d.asked)) {
    const p = ((d.answers || {})[q] || {}).probabilities || {};
    const entries = Object.entries(p).sort((x, y) => y[1] - x[1]);
    const standIn = entries.length > 2 && Math.abs(entries[0][1] - 0.9) < 1e-9 && entries.slice(2).every(e => Math.abs(e[1] - entries[1][1]) < 1e-9);
    out.push(el("p", { class: "mute" }, spec.instructions));
    const optionLabel = id => (spec.options.find(o => o.id === id) || {}).description || id;
    for (const [id, v] of entries.slice(0, 3)) out.push(el("div", {}, el("span", { class: "bar", style: `width:${Math.max(2, Math.round(v * 80))}px` }), `${(v * 100).toFixed(v < .01 ? 1 : 0)}% `, el("span", { class: "t" }, id), " ", el("span", { class: "mute" }, id === "none" || id.startsWith("(") || /^\d+$/.test(id) ? optionLabel(id) : ""), String(d.chosen && (d.chosen.constant || d.chosen)) === id || (d.chosen && d.chosen.constant && /^\d+$/.test(id)) && v === entries[0][1] ? " ✓ chosen" : ""));
    if (entries.length > 3) out.push(el("div", { class: "mute" }, `+${entries.length - 3} more options, each ${(entries[3][1] * 100).toFixed(1)}%`));
    out.push(el("div", { class: "prov" }, standIn ? `${FIXTURE}: 0.9 for the pick, the rest equal. Not live-model evidence.` : "recorded d1 score; its source (live or stand-in) is not written in the record. Not a confidence."));
  }
  if (d.offered.length) out.push(el("div", { class: "mute" }, "offered: " + d.offered.map(o => `“${o.constant}”`).join(", ") + (d.cut.length ? "; cut: " + d.cut.length : "")));
  return out;
}
const decisionsFor = (r, pred) => r.decisions.filter(pred);

function fulfillmentBody(b, op) {
  const o = outcomeOf(S.base, op.id), line = stopLine();
  if (!o) { b.append(el("p", { class: "mute" }, S.base.fulfillment ? "This operation has no outcome in the recorded check." : "No Stop check is recorded for this snapshot (an edit clears it; a hook run records one).")); return; }
  b.append(el("p", {}, el("strong", { class: o.outcome }, o.outcome), o.claim != null ? ` · the reply's claim was judged at ${Math.round(o.claim * 100)}% by d1` : ""));
  if (!line) return;
  const art = o.evidence == null ? null : line.artifacts[o.evidence], ev = art && (typeof art[2] === "number" ? line.evidence[art[2]] : art[2]);
  if (ev && ev.ran) b.append(el("p", {}, "evidence (execution): ran ", el("span", { class: "t" }, ev.ran), ` → exit ${ev.exit}`));
  else if (ev && ev.wrote) b.append(el("p", {}, "evidence (execution): wrote ", el("span", { class: "t" }, ev.wrote), ev.ok ? " (held)" : " (failed)"));
  else if (art && art[2] && art[2].judged !== undefined) b.append(el("p", {}, el("strong", {}, "d1 judged"), " the reply to be the work (prose judgment, not execution)"));
  else b.append(el("p", { class: "mute" }, "no evidence matched this operation."));
  const j = (line.judgments || []).find(x => String(x.obligation) === op.id);
  if (j) b.append(el("p", {}, el("strong", {}, "d1 judged"), `: “${j.instructions}” → ${j.share == null ? "invalid answer" : Math.round(j.share * 100) + "% yes"}; ${j.done ? "counted as done" : "not counted as done"}`));
  if (o.outcome !== "PASS" && !line.blocked) b.append(el("p", { class: "warn" }, `The reply was released with this ${o.outcome}: the record says blocked=${line.blocked}, send-backs ${line.blocks} of 2, so the ceiling was not what let it go; sending back was off.`));
  b.append(el("p", { class: "prov" }, `Stop check at ${line.at}; claims are prose judgments, executions are commands that ran.`));
}

function drawCard() {
  const c = $("#card");
  if (S.carry && !S.sel) { c.hidden = true; return; }
  c.replaceChildren();
  if (S.pending) return pendingCard(c);
  if (S.rerun) return rerunCard(c);
  if (!S.sel) { c.hidden = true; return; }
  const sel = S.sel, r = S.base, anchor = find(sel.key);
  placeCard(c, anchor);
  c.append(el("button", { class: "x", "aria-label": "close", onclick: closeCard }, "×"));
  if (S.typeView) return typeCard(c, S.typeView);
  const ul = el("ul");
  if (sel.kind === "history") {
    c.append(el("h2", {}, "Snapshots of this reading"), el("p", { class: "sub" }, "The store keeps every saved snapshot. Restore makes one the latest."));
    for (const { l, n } of snapshotsOf(S.id)) ul.append(el("li", {}, el("div", { class: "row" }, el("span", {}, `#${n} · ${l.snapshot.slice(0, 6)} · ${l.corrections.length} corrections${l.fulfillment ? " · checked" : ""}`),
      el("button", { class: "link", disabled: l === r, onclick: () => restore(n) }, l === r ? "latest" : "Restore"))));
    c.append(ul); return;
  }
  if (sel.kind === "word") {
    const w = r.text.slice(...wordSpan(sel.key)), p = r.phrases.find(p => p.start <= +sel.key.slice(2) && +sel.key.slice(2) < p.end);
    c.append(el("h2", {}, `“${w}”`), el("p", { class: "sub" }, "No meaning of its own is recorded for this word; the engine reads whole phrases."));
    if (p) {
      ul.append(rel("phrase", "phrase", p.terms.length ? `read as ${p.terms.map(t => t.function).join(" + ")}` : p.unresolved.length ? "read as unresolved" : "read as no operation", b => {
        b.append(el("p", {}, `The phrase starts ${p.starts_by}; origin ${p.brand}${p.quotes ? " (quoted)" : ""}.`));
        for (const t of p.terms) b.append(el("div", {}, go(`inspect ${t.function}`, () => select(key.op(t.id), "op", { id: t.id }))));
      }));
      const ds = decisionsFor(r, d => d.state.trim() === r.text.slice(p.start, p.end).trim() && d.operation == null);
      if (ds.length) ul.append(rel("dec", "decisions", `${ds.length} recorded about this phrase`, b => ds.forEach(d => b.append(...scoreRows(d)))));
    }
    return c.append(ul);
  }
  if (sel.kind === "unresolved") { const u = r.phrases.flatMap(p => p.unresolved).find(u => `u:${u.id}` === sel.key); c.append(el("h2", {}, "Unresolved request"), el("p", { class: "sub" }, `The engine could not make this an operation: ${u ? u.reason : ""}. It stays visible as owed work.`)); return; }
  if (sel.kind === "value") {
    const o = S.occ.get(sel.key); if (!o) return closeCard();
    c.append(el("h2", {}, `“${o.constant}”`), el("p", { class: "sub" }, "a constant of type ", tname(o.type), ` · characters ${o.at[0]}–${o.at[1]}`));
    for (const b of o.binds.filter(b => !b.inSeveral)) {
      const id = `bind:${b.op.id}:${b.path}`, k = key.place(b.op.id, b.path);
      ul.append(rel(id, "bound at", `${b.op.function}.${b.path}`, body => {
        body.append(el("p", {}, "the engine's binding of this place; declared type ", tname(b.op.parameters[b.path.split(".")[0]] || o.type)));
        body.append(go("inspect the place", () => select(k, "place", { op: b.op.id, path: b.path })));
        const ds = decisionsFor(r, d => String(d.operation) === b.op.id && d.path === b.path);
        for (const d of ds) body.append(el("p", { class: "mute" }, "d1's recorded question for this place:"), ...scoreRows(d));
      }));
    }
    ul.append(rel("use", "use it at", "other places in this message", body => useList(body, sourceOf(find(sel.key)))));
    return c.append(ul);
  }
  if (sel.kind === "place") {
    const op = termById(r, sel.op), pl = places(op).find(p => p.path === sel.path); if (!pl) return closeCard();
    const ty = placeType(op, pl), cor = correctionAt(r, op.id, pl.path), v = pl.value;
    c.append(el("h2", {}, `${op.function} · ${pl.path}`), el("p", { class: "sub" }, "a place of type ", tname(ty), cor ? ` · ✎ your correction: ${cor.status}${cor.reason ? " — " + cor.reason : ""}` : ""));
    ul.append(rel("value", "holds", say(v, r), body => {
      if (v.constant !== undefined) body.append(go("inspect that word", () => select(key.val(v.at), "value")));
      else if (v.ref !== undefined) { const t = termById(r, v.ref); body.append(el("p", {}, "this is the existing operation's result, not a copy"), t && go(`inspect ${t.function}`, () => select(key.op(t.id), "op", { id: t.id }))); }
      else if (v.hole) body.append(el("p", {}, `missing: ${v.reason}. Nothing was bound.`));
      else body.append(el("p", {}, JSON.stringify(v)));
    }));
    const ds = decisionsFor(r, d => String(d.operation) === op.id && d.path === pl.path);
    if (ds.length) ul.append(rel("dec", "d1 recorded", "its answer for this place", b => ds.forEach(d => b.append(...scoreRows(d)))));
    ul.append(rel("fill", "fill with", "words or results of this message", body => fillList(body, op, pl)));
    c.append(ul, el("div", { class: "actions" }, el("button", { onclick: () => previewBody({ reading: S.id, number: +op.id, path: pl.path, value: null }, `Clear ${op.function}.${pl.path}`, sel.key), disabled: v.hole !== undefined }, "Clear this place")));
    return;
  }
  if (sel.kind === "op") {
    const op = termById(r, sel.id), p = phraseOf(r, op.id), fn = (world() || { functions: {} }).functions[op.function], o = outcomeOf(r, op.id), j = op.judgments || {};
    c.append(el("h2", {}, op.function), el("p", { class: "sub" }, "the phrase read as ", el("span", { class: "t" }, op.function), ` · ${p.brand}: ${p.brand === "Asked" ? "the user's words" : "quoted"} · result `, tname(op.type)));
    ul.append(rel("sig", "signature", fn ? `asks to ${fn.asks.slice(0, 40)}${fn.asks.length > 40 ? "…" : ""}` : "(not in the world)", b => {
      if (!fn) return;
      b.append(el("p", {}, fn.asks));
      for (const [n, ty] of fn.parameters) b.append(el("div", {}, el("span", { class: "t" }, n), " : ", tname(op.parameters[n] || "?")));
      b.append(el("div", {}, "→ ", tname(op.type)));
    }));
    ul.append(rel("status", "judged by engine", ready(op) || "none", b => {
      b.append(el("p", {}, JUDGE.map(k => `${k} ${j[k]}`).join(" · ")));
      for (const d of j.diagnostics || []) b.append(el("p", { class: "no" }, JSON.stringify(d)));
      const waits = Object.values(op.arguments).filter(v => v.ref !== undefined).map(v => termById(r, v.ref)).filter(Boolean);
      if (!j.ready && j.pending && waits.length) b.append(el("p", {}, `its input is the result of ${waits.map(t => t.function).join(", ")}, which is pending.`));
      if (j.deferred) b.append(el("p", {}, "its own result is Later: it depends on work not yet done."));
    }));
    const ds = decisionsFor(r, d => String(d.operation) === op.id && d.path == null && d.function == null);
    if (ds.length) ul.append(rel("dec", "d1 recorded", "why this operation", b => ds.forEach(d => b.append(...scoreRows(d)))));
    ul.append(rel("stop", "Stop check", o ? o.outcome : "none recorded", b => fulfillmentBody(b, op)));
    ul.append(rel("places", "places", Object.keys(op.arguments).join(", "), b => places(op).forEach(pl => b.append(el("div", {}, go(`${pl.path}: ${say(pl.value, r)}`, () => select(key.place(op.id, pl.path), "place", { op: op.id, path: pl.path })))))));
    return c.append(ul);
  }
}
const wordSpan = k => { const s = +k.slice(2), m = /\S+/.exec(S.base.text.slice(s)); return [s, s + m[0].length]; };

function typeCard(c, name) {
  const w = world() || { types: {}, constructors: {} };
  const m = /^(\w+)\[(.+)\]$/.exec(name), t = w.types[name];
  c.append(el("button", { class: "link", onclick: () => { S.typeView = null; drawCard(); } }, "← back"), el("h2", {}, name), el("p", { class: "sub" }, t ? `kind ${t.kind}` : m ? "a constructed type" : "not declared in this world"));
  const b = el("div", { class: "body", style: "padding-left:0" });
  if (m) { const k = w.constructors[m[1]]; b.append(el("p", {}, el("span", { class: "t" }, m[1]), `: ${k ? k.kind + ", " + k.describes : "(not declared)"}`), el("p", {}, "of ", tname(m[2]))); }
  if (t) {
    if (t.sum) { const alts = t.alternatives; b.append(el("p", {}, "a sum of: ", alts.map(a => a.member ? el("span", { class: "t", title: a.words }, `${a.member}=“${a.words}”`) : a.sum ? tname(a.sum) : "?").flatMap((x, i) => [i ? " | " : "", x]))); }
    else if (t.brand) b.append(el("p", {}, "a brand over ", tname(t.of.brand || t.of.base || "?"), "; the brand is a nominal label, not evidence."));
    else if (t.base) b.append(el("p", {}, `the base type ${t.base}`));
  }
  const holders = terms(S.base).flatMap(op => places(op).filter(p => placeType(op, p) === name).map(p => `${op.function}.${p.path}`));
  b.append(el("p", {}, holders.length ? `places of this type here: ${holders.join(", ")}` : "no place of exactly this type in this message."));
  b.append(el("p", { class: "mute" }, "What may be used at a place is asked of the engine from the word or place (Use it at… / Fill with…), not computed here."));
  c.append(b);
}

async function fillList(body, op, pl) {
  const r = S.base, list = body.appendChild(el("div"));
  list.textContent = "asking the engine…";
  const cands = [];
  const seen = new Set();
  for (const o of terms(r)) for (const p of places(o)) for (const cst of constantsIn(p.value)) { const k = key.val(cst.at); if (!seen.has(k)) { seen.add(k); cands.push({ label: `“${cst.constant}”`, value: cst }); } }
  for (const t of terms(r)) if (t.id !== op.id) cands.push({ label: `the result of ${t.function}`, value: { ref: t.id } });
  const rows = await Promise.all(cands.map(async cd => ({ cd, res: await ask({ reading: S.id, number: +op.id, path: pl.path, value: cd.value }) })));
  list.replaceChildren(...rows.map(({ cd, res }) => el("div", { class: "row" }, el("button", { "data-cand": cd.label, onclick: () => commitPreview(res, `Use ${cd.label} at ${op.function}.${pl.path}`, key.place(op.id, pl.path)) }, `${okay(res) ? "✓" : "✕"} ${cd.label}`), el("span", { class: okay(res) ? "ok" : "no" }, fitWord(res)))));
}
async function useList(body, src) {
  const list = body.appendChild(el("div")); list.textContent = "asking the engine…";
  const pv = previewAll(src); await pv.job;
  list.replaceChildren(...targetsOf(src).map(tg => { const res = pv.results.get(tg.k); return el("div", { class: "row" }, el("button", { "data-target": tg.k, disabled: !!res.here, onclick: () => commitPreview(res, `Use ${src.label} at ${tg.op.function}.${tg.p.path}`, tg.k) }, `${res.here ? "·" : okay(res) ? "✓" : "✕"} ${tg.op.function}.${tg.p.path}`), el("span", { class: res.here || okay(res) ? "ok" : "no" }, fitWord(res))); }));
}

// ---- the transaction: preview (/edit) -> consequence -> cancel or accept (/accept) ----
function commitPreview(res, what, anchorKey) {
  if (S.carry) endCarry();
  S.pending = { body: res.body, draft: res.draft, diagnostics: res.diagnostics, error: res.error, what, anchor: anchorKey, failure: null };
  S.sel = null; S.typeView = null; S.open = null;
  S.note = okay(res) ? "Previewing the engine's draft. Nothing is saved until you accept." : "The engine refused; the base reading is unchanged."; msg();
  render();
  (find("accept") || $("#card .primary") || $("#card button"))?.focus();
}
async function previewBody(body, what, anchorKey) { commitPreview(await ask(body), what, anchorKey); }

function pendingCard(c) {
  const P = S.pending, ok = okay(P);
  placeCard(c, find(P.anchor));
  c.append(el("h2", {}, ok ? "Preview · nothing is saved" : "Refused by the engine"), el("p", { class: "sub" }, P.what));
  if (!ok) {
    for (const d of P.diagnostics) c.append(el("div", { class: "chgline no" }, `${(termById(S.base, String(d[0])) || {}).function || (d[0] == null ? "new operation" : "#" + d[0])}.${d[1]}: engine rule “${d[2]}”`));
    if (P.error) c.append(el("div", { class: "chgline no" }, P.error));
    c.append(el("p", { class: "sub" }, "The base reading is still what the text shows."));
  } else {
    const ch = diff(S.base, P.draft);
    c.append(el("p", { class: "sub" }, `${ch.length} change${ch.length === 1 ? "" : "s"} in the engine's draft (marked in the text):`));
    for (const x of ch) c.append(el("div", { class: "chgline" }, x.was !== undefined ? [el("strong", {}, x.text), ": ", el("span", { class: "was" }, x.was), " → ", x.now] : x.text));
    if (!ch.length) c.append(el("div", { class: "chgline mute" }, "the draft equals the base: nothing would change."));
  }
  if (P.failure) c.append(el("div", { class: "chgline no", role: "alert" }, P.failure));
  c.append(el("div", { class: "actions" }, ok ? el("button", { class: "primary", "data-key": "accept", id: "accept", onclick: accept }, "Accept (saves as your correction)") : null, el("button", { "data-key": "cancel", onclick: cancel }, ok ? "Cancel" : "Dismiss")));
}
function cancel() { const a = S.pending && S.pending.anchor; S.pending = null; S.note = "Cancelled: the base reading is unchanged."; msg(); render(); find(a)?.focus(); }
async function accept() {
  const P = S.pending, fresh = await fetch("/readings").then(r => r.json()), now = fresh.filter(l => l.id === S.id).at(-1);
  if (now.snapshot !== S.base.snapshot) { P.failure = "Not saved: the store has a newer snapshot than the one this preview was made from. Your draft is kept here; cancel, reload and redo it."; drawCard(); return; }
  const r = await api("/accept", P.body);
  if (r.error || r.diagnostics.length || !r.saved) { P.failure = "Not saved: " + (r.error || r.diagnostics.map(d => d.join(" ")).join("; ")); drawCard(); return; }
  S.pending = null; await load(); S.note = `Accepted and saved (snapshot ${S.base.snapshot.slice(0, 6)}, ${S.base.corrections.length} correction${S.base.corrections.length === 1 ? "" : "s"}). Reloading shows the same reading.`; msg(); render();
}
async function rerun() {
  S.note = "Rerunning: the engine reads the source again with d1…"; msg();
  const r = await api("/rerun", { reading: S.id });
  if (r.error) { S.note = "Rerun failed: " + r.error; return msg(); }
  await load();
  S.sel = null; S.rerun = { corrections: r.corrections || [], diagnostics: r.diagnostics || [], saved: !!r.saved };
  S.note = r.saved ? `Rerun saved as snapshot ${S.base.snapshot.slice(0, 6)}.` : "Rerun not saved."; msg(); render();
}
function rerunCard(c) {
  placeCard(c, $("#msg"));
  c.append(el("button", { class: "x", "aria-label": "close", onclick: () => { S.rerun = null; render(); $("#rerun").focus(); } }, "×"), el("h2", {}, "Rerun with d1"), el("p", { class: "sub" }, "the source was read again; your corrections were applied to the new reading:"));
  if (!S.rerun.corrections.length) c.append(el("div", { class: "chgline mute" }, "no corrections to apply."));
  for (const k of S.rerun.corrections) c.append(el("div", { class: "chgline" }, `${k.function || "op " + k.operation}.${k.path}: `, el("strong", { class: k.status === "retained" ? "ok" : "no" }, k.status), k.reason ? ` — ${k.reason}` : ""));
  for (const d of S.rerun.diagnostics) c.append(el("div", { class: "chgline no" }, JSON.stringify(d)));
  c.append(el("p", { class: "prov" }, "This reading was made by the d1 service configured for the harness; scores in it are recorded as written, not graded."));
}
async function restore(n) {
  const r = await api("/restore", { snapshot: n });
  await load(); S.sel = null; S.note = r.saved ? `Restored snapshot #${n} as the latest.` : "Restore refused: " + JSON.stringify(r.diagnostics || r.error); msg(); render();
}
const msg = () => { $("#msg").textContent = S.note; };
const snapLabel = () => { const all = snapshotsOf(S.id); return `snapshot ${all.findIndex(x => x.l === S.base) + 1} of ${all.length} · ${S.base.corrections.length} correction${S.base.corrections.length === 1 ? "" : "s"}${S.pending ? " · previewing" : ""}`; };

// ---- carrying (drag with the pointer, or Space to pick up with the keyboard): the same previews, the same transaction ----
async function startCarry(e_) {
  if (S.pending) return;
  const src = sourceOf(e_), pv = previewAll(src);
  S.carry = { src, pv, done: false }; S.sel = null; $("#card").hidden = true;
  document.body.classList.add("carrying");
  S.note = `Carrying ${src.label}: asking the engine which places take it…`; msg();
  await pv.job;
  if (S.carry && S.carry.pv === pv) {
    S.carry.done = true; markFit();
    const n = [...pv.results.values()].filter(x => !x.here);
    S.note = `Carrying ${src.label}: ${n.filter(okay).length} place(s) fit, ${n.filter(x => !okay(x)).length} refused (engine verdicts). Tab to a place and press Enter, or drop on it. Escape cancels.`; msg();
  }
}
function markFit() {
  if (!S.carry) return;
  for (const [k, res] of S.carry.pv.results) { const e = find(k) || document.querySelector(`[data-place="${CSS.escape(k)}"]`); if (e) { e.dataset.fit = res.here ? "here" : okay(res) ? "ok" : "no"; e.title = fitWord(res); } }
  document.querySelectorAll("[data-place]").forEach(e => { const res = S.carry.pv.results.get(e.dataset.place); if (res) { e.dataset.fit = res.here ? "here" : okay(res) ? "ok" : "no"; e.title = fitWord(res); } });
}
const restoreMarks = () => { if (S.carry && S.carry.done) markFit(); };
function endCarry(note) { S.carry = null; document.body.classList.remove("carrying"); document.querySelectorAll("[data-fit]").forEach(e => { delete e.dataset.fit; e.removeAttribute("title"); }); document.querySelectorAll(".ghost").forEach(g => g.remove()); document.querySelectorAll(".hot").forEach(h => h.classList.remove("hot")); if (note) { S.note = note; msg(); } }
async function dropOn(placeEl) {
  if (!S.carry) return;
  const C = S.carry; await C.pv.job;
  const k = placeEl.dataset.place, res = C.pv.results.get(k);
  if (!res || res.here) { endCarry("That is where it already is. Nothing changed."); return render(); }
  const op = termById(S.base, placeEl.dataset.op);
  commitPreview(res, `Use ${C.src.label} at ${op.function}.${placeEl.dataset.path}`, k);
}

// ---- events: pointer drag, click, keyboard ----
let drag = null, justDragged = false;
const stage = $("#stage");
stage.addEventListener("pointerdown", e => {
  const d = e.target.closest("[data-drag]");
  if (!d || e.target.closest(".pl") || e.button !== 0 || S.pending) return;
  drag = { el: d, x: e.clientX, y: e.clientY, started: false };
});
addEventListener("pointermove", e => {
  if (!drag) return;
  if (!drag.started) {
    if (Math.hypot(e.clientX - drag.x, e.clientY - drag.y) < 6) return;
    drag.started = true; drag.ghost = el("div", { class: "ghost" }, sourceOf(drag.el).label); document.body.append(drag.ghost); startCarry(drag.el);
  }
  drag.ghost.style.left = e.clientX + 12 + "px"; drag.ghost.style.top = e.clientY + 12 + "px";
  document.querySelectorAll(".hot").forEach(h => h.classList.remove("hot"));
  const p = placeAt(e); if (p) p.classList.add("hot");
});
const placeAt = e => document.elementsFromPoint(e.clientX, e.clientY).map(x => x.closest && x.closest("[data-place]")).find(Boolean);
addEventListener("pointerup", async e => {
  if (!drag) return;
  const d = drag; drag = null;
  if (!d.started) return;
  d.ghost.remove(); justDragged = true; setTimeout(() => { justDragged = false; }, 0);
  const p = placeAt(e);
  document.querySelectorAll(".hot").forEach(h => h.classList.remove("hot"));
  if (p) await dropOn(p); else { endCarry("Dropped outside any place: nothing changed."); render(); }
});
const objectAt = t => t.closest("[data-kind]");
function activate(o) {
  if (S.carry) { if (o.dataset.place) return dropOn(o); return; }
  const k = o.dataset.key, kind = o.dataset.kind;
  if (kind === "op") select(k, "op", { id: o.dataset.op });
  else if (kind === "place") select(k, "place", { op: o.dataset.op, path: o.dataset.path });
  else select(k, kind);
}
stage.addEventListener("click", e => {
  if (justDragged || e.target.closest("#card")) return;
  const o = objectAt(e.target);
  if (!o) { if (S.sel && !S.pending) closeCard(); return; }
  if (S.pending) return;
  activate(o);
});
addEventListener("keydown", e => {
  if (e.key === "Escape") {
    if (S.carry) { endCarry("Cancelled: nothing changed."); render(); return; }
    if (S.pending) return cancel();
    if (S.typeView) { S.typeView = null; return drawCard(); }
    if (S.open) { const o = S.open; S.open = null; drawCard(); $(`[data-rel="${CSS.escape(o)}"]`)?.focus(); return; }
    if (S.rerun) { S.rerun = null; render(); return; }
    if (S.sel) return closeCard();
    return;
  }
  const o = e.target.closest && e.target.closest("#text [data-kind]");
  if (!o || e.target.closest("#card")) return;
  if (e.key === "Enter") { e.preventDefault(); activate(o); }
  else if (e.key === " ") {
    e.preventDefault();
    if (S.carry) return o.dataset.place ? dropOn(o) : undefined;
    if (o.dataset.drag) startCarry(o);
  }
});
$("#rerun").addEventListener("click", rerun);
$("#older").addEventListener("click", () => { S.pending = null; S.sel = { key: "older", kind: "history" }; S.rerun = null; render(); const c = $("#card"); c.style.top = "0px"; c.style.left = "0px"; });
$("#pick").addEventListener("change", async e => { S.id = e.target.value; S.sel = S.pending = null; await load(); render(); });

load().then(() => { render(); S.note = "The engine's reading, from /readings. Scores below are recorded inputs of a stand-in d1, not live-model evidence."; msg(); });
