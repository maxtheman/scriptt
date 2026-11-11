// model.js: the pure part of the board. It reads a saved reading (form 5) and its world (agree.world_record()) and answers
// "where can this go, and what would the reading be". It never decides meaning the engine owns: anything it derives
// (what fits, the flags of an edited operation, a new operation) is returned with prov:true and drawn as provisional.
// The engine's own flags stay on every operation that is not touched by an edit.
(function (root) {
  const own = (o, k) => o && Object.prototype.hasOwnProperty.call(o, k);

  // ---- types: names and structure come from worlds.json only
  const nameOf = (t) => !t ? "?" : t.base ?? t.brand ?? t.sum ?? t.product ?? t.member ?? (own(t, "constructor") ? `${t["constructor"]}[${nameOf(t.of)}]` : "?");
  const ctorOf = (t) => (t && own(t, "constructor") ? t["constructor"] : null);

  function indexWorld(W) {
    const ancestors = (n, seen = new Set()) => { if (!n || seen.has(n)) return []; seen.add(n); const t = W.types[n]; return [n, ...(t?.brand && t.of ? ancestors(nameOf(t.of), seen) : [])]; };
    return { W, ancestors, types: Object.keys(W.types), fns: Object.keys(W.functions), nameOf, ctorOf };
  }

  // does a declared type tree take a thing of type name n?  (sums are searched; a brand is nominal; Maybe and Later take what their argument takes)
  function takes(wx, tree, n) {
    if (!tree) return false;
    const c = ctorOf(tree);
    if (c === "Maybe" || c === "Later") return takes(wx, tree.of, n);
    if (c === "Many") return false;                      // a list takes members, not a single thing: see leaf.elem
    const anc = wx.ancestors(n);
    const has = (t) => { if (nameOf(t) !== "?" && anc.includes(nameOf(t))) return true; if (t.sum) return t.alternatives.some((a) => !a.member && has(a)); return false; };
    return has(tree);
  }

  // ---- reading -> a draft: operations in order, nested applications hoisted (kept with nested:true)
  function toDraft(r) {
    const ops = {}, order = [], phraseOf = {};
    const hoist = (t, pi) => {
      const args = {};
      for (const [k, v] of Object.entries(t.arguments)) args[k] = walkVal(v, pi);
      ops[t.id] = { id: t.id, fn: t.function, type: t.type, args, params: t.parameters, judg: t.judgments, phrase: pi };
      order.push(t.id); phraseOf[t.id] = pi;
    };
    const walkVal = (v, pi) => {
      if (v && v.function && v.id != null && v.arguments) { hoist(v, pi); return { ref: v.id, nested: true }; }
      if (v && v.several) return { ...v, several: v.several.map((x) => walkVal(x, pi)) };
      if (v && v.fields) return { ...v, fields: Object.fromEntries(Object.entries(v.fields).map(([k, x]) => [k, walkVal(x, pi)])) };
      return v;
    };
    r.phrases.forEach((p, pi) => p.terms.forEach((t) => hoist(t, pi)));
    return { ops, order, log: [], seq: 0, consts: structuredClone(r.constants), world: [] };
  }

  // ---- values
  const kindOf = (v) => !v ? "none" : v.constant != null ? "const" : v.ref != null ? "ref" : v.hole != null ? "hole" : v.empty != null ? "empty" : v.several ? "several" : v.fields ? "fields" : "none";
  const walkValue = (v, f) => { f(v); if (v?.several) v.several.forEach((x) => walkValue(x, f)); if (v?.fields) Object.values(v.fields).forEach((x) => walkValue(x, f)); };
  const refsIn = (op) => { const out = []; Object.values(op.args).forEach((v) => walkValue(v, (x) => x.ref != null && out.push(x.ref))); return out; };
  const dependsOn = (st, a, b, seen = new Set()) => { if (a === b) return true; if (seen.has(a)) return false; seen.add(a); const op = st.ops[a]; return !!op && refsIn(op).some((r) => dependsOn(st, r, b, seen)); };
  const resultName = (op) => op.type.replace(/^Later\[(.*)\]$/, "$1");

  // ---- the places of a draft: every leaf that can hold a value
  function places(wx, st) {
    const out = [];
    for (const id of st.order) {
      const op = st.ops[id], fn = wx.W.functions[op.fn];
      if (!fn) continue;
      for (const [pname, tree] of fn.parameters) walk(op, pname, tree, op.args[pname]);
    }
    function leaf(op, path, tree, val, extra = {}) { out.push({ id: `pl-${op.id}-${path}`, op: op.id, path, tree, val, declared: nameOf(tree), ...extra }); }
    function walk(op, path, tree, val) {
      const c = ctorOf(tree);
      if (c === "Many" && val?.several) {
        val.several.forEach((m, i) => leaf(op, `${path}.${i}`, tree.of, m, { member: i, list: path }));
        leaf(op, `${path}.+`, tree.of, null, { add: true, list: path, emptyList: val.several.length === 0 });
      } else if (tree.product && val?.fields) {
        for (const [f, ft] of Object.entries(tree.fields)) walk(op, `${path}.${f}`, ft, val.fields[f] ?? { hole: nameOf(ft), reason: "" });
      } else if (c === "Many") leaf(op, path, tree, val, { listHole: true, elem: tree.of });
      else leaf(op, path, tree, val);
    }
    return out;
  }

  // set a value at a path of an operation (path: "arg", "arg.field", "arg.3", "arg.+")
  function setAt(st, opId, path, val) {
    const n = structuredClone(st);
    const segs = path.split("."), op = n.ops[opId];
    let holder = op.args, key = segs[0];
    for (let i = 1; i < segs.length; i++) {
      const cur = holder[key], s = segs[i];
      if (cur?.fields) { holder = cur.fields; key = s; }
      else if (cur?.several) { holder = cur.several; key = s === "+" ? cur.several.length : Number(s); }
      else break;
    }
    holder[key] = val;
    return n;
  }

  // a thing that is held -> what it is, as a value
  // remove a member of a list place (an empty list stays an explicit empty list, not a hole)
  function removeAt(st, opId, listPath, idx) {
    const n = structuredClone(st), segs = listPath.split("."); let cur = n.ops[opId].args[segs[0]];
    for (let i = 1; i < segs.length; i++) cur = cur.fields ? cur.fields[segs[i]] : cur.several[Number(segs[i])];
    cur.several.splice(idx, 1); return n;
  }
  const valueOf = (t) => t.k === "const" ? { constant: t.c.constant, type: t.c.type, at: t.c.at } : t.k === "op" ? { ref: t.id } : null;
  const thingName = (t) => t.k === "const" ? `“${t.c.constant}”` : t.k === "op" ? `result of ${t.id}` : t.k === "fn" ? t.name : t.name ?? "";
  const typeOfThing = (st, t) => t.k === "const" ? t.c.type : t.k === "op" ? resultName(st.ops[t.id]) : null;

  // can this place take this thing? {ok, why}
  function fits(wx, st, pl, t) {
    const tn = typeOfThing(st, t);
    if (t.k === "op") {
      if (pl.op === t.id) return { ok: false, why: `${pl.op} cannot take its own result` };
      if (dependsOn(st, t.id, pl.op)) return { ok: false, why: `${t.id} already depends on ${pl.op}: that would be a cycle` };
    }
    if (pl.add) return takes(wx, pl.tree, tn) ? { ok: true, why: `adds a member (${nameOf(pl.tree)})` } : { ok: false, why: `${tn} is not a ${nameOf(pl.tree)}` };
    if (pl.listHole) return takes(wx, pl.elem, tn) ? { ok: true, why: `starts the list (${nameOf(pl.elem)})` } : { ok: false, why: `${tn} is not a ${nameOf(pl.elem)}, which ${pl.declared} holds` };
    if (pl.tree.product) return { ok: false, why: `${pl.declared} is a record: fill its fields` };
    if (takes(wx, pl.tree, tn)) return { ok: true, why: `${tn} is accepted by ${pl.declared}` };
    return { ok: false, why: `${pl.declared} takes ${acceptedList(wx, pl.tree)}, not ${tn}` };
  }
  function acceptedList(wx, t) { const c = ctorOf(t); if (c) return acceptedList(wx, t.of); if (t.sum) return t.alternatives.map((a) => (a.member ? a.member : nameOf(a))).filter((x, i, a) => a.indexOf(x) === i).join(" | "); return nameOf(t); }

  function bindState(st, pl, val) {
    if (pl.add) return setAt(st, pl.op, pl.path, val);
    if (pl.listHole) return setAt(st, pl.op, pl.path, { several: [val], type: pl.declared });
    return setAt(st, pl.op, pl.path, val);
  }
  const holeValue = (pl, reason) => ({ hole: pl.declared, reason });

  // after a replacement, a nested operation that nothing refers to any more goes
  function sweep(st) {
    const n = structuredClone(st);
    for (const id of [...n.order]) { const op = n.ops[id]; if (op.nested && !n.order.some((o) => n.ops[o] !== op && refsIn(n.ops[o]).includes(id))) { delete n.ops[id]; n.order.splice(n.order.indexOf(id), 1); } }
    return n;
  }

  // ---- provisional judgments: only for operations touched by an edit
  function recompute(wx, st, base) {
    const n = structuredClone(st), touched = new Set();
    for (const id of n.order) if (!base.ops[id] || JSON.stringify(base.ops[id].args) !== JSON.stringify(n.ops[id].args)) touched.add(id);
    let grew = true;
    while (grew) { grew = false; for (const id of n.order) if (!touched.has(id) && refsIn(n.ops[id]).some((r) => touched.has(r))) { touched.add(id); grew = true; } }
    const memo = {};  // pending: the result is not available yet (deferred itself, or waits on an input that is pending)
    const wait = (id) => { const op = n.ops[id]; return !!op && refsIn(op).some((r) => pend(r)); };
    const pend = (id) => { if (id in memo) return memo[id]; memo[id] = false; const op = n.ops[id]; return (memo[id] = !!op && (op.type.startsWith("Later") || wait(id))); };
    for (const id of n.order) {
      const op = n.ops[id];
      if (!touched.has(id)) { op.prov = false; continue; }
      let hole = false; Object.values(op.args).forEach((v) => walkValue(v, (x) => { if (x.hole != null) hole = true; }));
      const complete = !hole;
      op.judg = { ...op.judg, complete, pending: pend(id), deferred: op.type.startsWith("Later"), ready: complete && !wait(id), diagnostics: [] };
      op.prov = true;
    }
    return n;
  }

  // ---- everything that can happen to a held thing: moves (states) and refusals (reasons)
  // thing: {k:"const",c,from?} | {k:"op",id} | {k:"fn",name} | {k:"hole",place} | {k:"type",name} | {k:"member",...}
  function movesFor(wx, st, base, t, units) {
    const ok = [], no = [], pls = places(wx, st);
    const done = (s, label, target, why, extra = {}) => ok.push({ target, state: recompute(wx, sweep(s), base), label, why, ...extra });
    if (t.k === "const" || t.k === "op") {
      for (const pl of pls) {
        if (t.from === pl.id) continue;
        const f = fits(wx, st, pl, t);
        if (!f.ok) { no.push({ target: pl.id, reason: f.why }); continue; }
        let s = bindState(st, pl, valueOf(t));
        if (t.from) { const src = pls.find((p) => p.id === t.from); if (src && !src.add) s = setAt(s, src.op, src.path, holeValue(src, "cleared")); }
        done(s, `${pl.op}.${pl.path}`, pl.id, f.why);
      }
    } else if (t.k === "hole") {            // an open place takes a word that fits it, or an operation's result
      const pl = t.place;
      for (const u of units) if (u.c) { const th = { k: "const", c: u.c }, f = fits(wx, st, pl, th); if (f.ok && JSON.stringify(pl.val) === JSON.stringify(valueOf(th))) continue; f.ok ? done(bindState(st, pl, valueOf(th)), thingName(th), u.id, f.why) : no.push({ target: u.id, reason: f.why }); }
      for (const id of st.order) { const th = { k: "op", id }, f = fits(wx, st, pl, th); if (f.ok && pl.val?.ref === id) continue; f.ok ? done(bindState(st, pl, valueOf(th)), `↩${id} ${st.ops[id].fn}`, `op-${id}`, f.why) : no.push({ target: `op-${id}`, reason: f.why }); }
    } else if (t.k === "fn") {              // apply a function to a thing (provisional: the engine builds this operation)
      const fn = wx.W.functions[t.name], things = [];
      for (const u of units) if (u.c) things.push({ target: u.id, th: { k: "const", c: u.c } });
      for (const pl of pls) if (pl.val && (pl.val.constant != null || pl.val.ref != null)) things.push({ target: pl.id, th: pl.val.constant != null ? { k: "const", c: pl.val } : { k: "op", id: pl.val.ref } });
      for (const x of things) {
        const tn = typeOfThing(st, x.th);
        const slot = fn.parameters.find(([, tree]) => takes(wx, tree, tn) || (ctorOf(tree) === "Many" && takes(wx, tree.of, tn)));
        if (!slot) { no.push({ target: x.target, reason: `${t.name} takes ${fn.parameters.map(([p, tr]) => nameOf(tr)).join(", ")}, not ${tn}` }); continue; }
        const nid = String(Math.max(-1, ...st.order.map(Number).filter((x) => !isNaN(x))) + 1), s = structuredClone(st);
        const args = {}; for (const [p, tr] of fn.parameters) args[p] = { hole: nameOf(tr), reason: "cleared" };
        const v = valueOf(x.th); args[slot[0]] = ctorOf(slot[1]) === "Many" ? { several: [v], type: nameOf(slot[1]) } : v;
        s.ops[nid] = { id: nid, fn: t.name, type: nameOf(fn.result), args, params: Object.fromEntries(fn.parameters.map(([p, tr]) => [p, nameOf(tr)])), judg: {}, phrase: null, isNew: true };
        s.order.push(nid);
        done(s, `${t.name}(${slot[0]})`, x.target, `new operation ${nid}: ${t.name} with ${thingName(x.th)} in ${slot[0]}`);
      }
    }
    return { ok, no };
  }

  // the engine writes Python JSON: NaN, Infinity and -Infinity appear as bare tokens (not valid JSON). They are read as null (no number).
  const parseEngine = (text) => JSON.parse(text.replace(/([:\[,]\s*)(-?Infinity|NaN)(?=\s*[,\]}])/g, "$1null"));

  // ---- editing the words and the world (provisional: the engine regroups and the world is a gated draft)
  const membersOf = (W) => { const out = []; for (const [n, t] of Object.entries(W.types)) if (t.sum) for (const a of t.alternatives) if (a.member) out.push({ type: n, member: a.member, words: a.words }); return out; };
  function patchWorld(W, drafts) {
    if (!drafts?.length) return W;
    const w = structuredClone(W);
    for (const d of drafts) { const t = w.types[d.type]; if (!t?.sum) continue; const add = { member: d.member, words: d.words, type: t.alternatives.find((a) => a.member)?.type, draft: true }; t.alternatives.push(add);
      for (const o of Object.values(w.types)) if (o.sum) for (const a of o.alternatives) if (a.sum === d.type) a.alternatives.push(add);
      for (const f of Object.values(w.functions)) for (const [, tr] of f.parameters) { const go = (x) => { if (x?.sum === d.type && x !== t) x.alternatives.push(add); if (x?.alternatives) x.alternatives.forEach(go); if (x?.of) go(x.of); }; go(tr); } }
    return w;
  }
  const replaceConst = (st, oldAt, c) => { const n = structuredClone(st); n.consts = n.consts.filter((x) => x.at[0] !== oldAt[0]); if (c) n.consts.push(c); n.consts.sort((a, b) => a.at[0] - b.at[0]);
    for (const op of Object.values(n.ops)) for (const k of Object.keys(op.args)) { const fix = (v) => { if (v?.constant != null && v.at && v.at[0] === oldAt[0]) return c ? { ...c } : { hole: v.type, reason: "cleared" }; if (v?.several) return { ...v, several: v.several.map(fix) }; if (v?.fields) return { ...v, fields: Object.fromEntries(Object.entries(v.fields).map(([f, x]) => [f, fix(x)])) }; return v; }; op.args[k] = fix(op.args[k]); } return n; };
  // candidates for a span edit: each is a member of some type or refused with the reason
  function spanOptions(text, c, W) {
    const toks = [...text.matchAll(/\S+/g)].map((m) => [m.index, m.index + m[0].length]), [a, b] = c.at, mem = membersOf(W), out = [];
    const nextR = toks.find(([s]) => s >= b), prevL = [...toks].reverse().find(([, e]) => e <= a), inside = toks.filter(([s, e]) => s >= a && e <= b);
    const cands = [];
    if (prevL) cands.push({ label: "extend left", at: [prevL[0], b] });
    if (nextR) cands.push({ label: "extend right", at: [a, nextR[1]] });
    if (inside.length > 1) { cands.push({ label: "shrink left", at: [inside[1][0], b] }); cands.push({ label: "shrink right", at: [a, inside[inside.length - 2][1]] }); }
    for (const cd of cands) { const words = text.slice(cd.at[0], cd.at[1]), hit = mem.filter((x) => x.words.toLowerCase() === words.toLowerCase());
      out.push(hit.length ? { ...cd, words, ok: true, type: hit[0].type, why: `${hit[0].type} has a member “${words}”` } : { ...cd, words, ok: false, why: `“${words}” is not a member of ${[...new Set(mem.map((x) => x.type))].join(", ")}` }); }
    return out;
  }
  const retagOptions = (c, W) => membersOf(W).filter((x) => x.words.toLowerCase() === c.constant.toLowerCase());
  root.Model = { membersOf, patchWorld, replaceConst, spanOptions, retagOptions, removeAt, parseEngine, nameOf, ctorOf, indexWorld, takes, toDraft, kindOf, walkValue, refsIn, dependsOn, resultName, places, setAt, fits, bindState, holeValue, sweep, recompute, movesFor, valueOf, thingName, typeOfThing, acceptedList };
})(typeof window !== "undefined" ? window : globalThis);
