// Board 5 audit. Load in the page (`await import("/audit.js")` or eval its text), then `await audit5(["e6741406", ...], {accept: true})`.
// Every gesture is a real PointerEvent / KeyboardEvent dispatched at the on-screen coordinates of an element, on the element that
// elementFromPoint finds there (as for a person). Drags go through Dragology's own handlers: the audit never calls the page's
// state functions to move things; it reads S, the network log (__net) and the DOM to check what happened.
(function () {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const center = (e) => { const q = e.getBoundingClientRect(); return [q.left + q.width / 2, q.top + q.height / 2]; };
  const at = (x, y) => document.elementFromPoint(x, y) || document.body;
  // with the driver (web/audit-run.mjs) each gesture is a trusted input event made by Chrome; without it, a dispatched event
  window.__cdpWait = window.__cdpWait || {};
  window.__cdpDone = (id) => { const f = window.__cdpWait[id]; delete window.__cdpWait[id]; if (f) f(); };
  const bridge = (g) => new Promise((res) => { const id = String(Math.random()); window.__cdpWait[id] = res; window.cdpInput(JSON.stringify({ id, ...g })); });
  const trusted = () => typeof window.cdpInput === "function";
  const pe = async (type, x, y) => {
    if (trusted()) { await bridge({ type, x: Math.round(x * 10) / 10, y: Math.round(y * 10) / 10 }); return at(x, y); }
    const el = at(x, y); el.dispatchEvent(new PointerEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y, button: 0, buttons: type === "pointerup" ? 0 : 1, pointerId: 1, isPrimary: true, pointerType: "mouse" })); return el;
  };
  const click = async (el, what = "") => { if (!el) throw new Error("nothing to click " + what); if (el.id) el = document.getElementById(el.id) || el; const [x, y] = center(el.querySelector("rect") || el); if (trusted()) { await pe("pointermove", x, y); await pe("pointerdown", x, y); await pe("pointerup", x, y); } else { const t = await pe("pointerdown", x, y); await pe("pointerup", x, y); t.dispatchEvent(new MouseEvent("click", { bubbles: true, clientX: x, clientY: y })); } await sleep(150); };
  const key = async (k, extra = {}) => { if (trusted()) await bridge({ type: "key", key: k, ...extra }); else document.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true, ...extra })); await sleep(60); };
  const shot = async (name) => { if (trusted()) await bridge({ type: "shot", name }); };
  const until = async (f, ms = 8000) => { const t = Date.now(); while (Date.now() - t < ms) { const v = f(); if (v) return v; await sleep(60); } return null; };
  const idle = () => until(() => window.board && !window.board.busy(), 20000);
  const dock = () => document.getElementById("dock").innerText;
  const el = (sel) => document.querySelector(sel);
  // a drag: press on src, move in steps to (dx, dy), wait for the engine's draft under the pointer, read the dock, release
  async function drag(src, to, opts = {}) {
    if (src.id) src = document.getElementById(src.id) || src;
    if (to && to.id) to = document.getElementById(to.id) || to;
    const [sx, sy] = center(src.querySelector("rect") || src);
    const [dx, dy] = Array.isArray(to) ? to : center(to.querySelector("rect") || to);
    const grabbed = await pe("pointerdown", sx, sy);
    for (let i = 1; i <= 8; i++) { await pe("pointermove", sx + ((dx - sx) * i) / 8, sy + ((dy - sy) * i) / 8); await sleep(25); }
    await until(() => !/…/.test(dock()) && dock().trim(), opts.wait || 6000);
    await pe("pointermove", dx + 0.5, dy); await sleep(60);
    const mid = { dock: dock(), net: window.__net.length, rail: document.querySelectorAll("[id^=rl-]").length, ghost: !!document.querySelector("#board svg [opacity='0.5']") };
    if (opts.shot) await shot(opts.shot + "-held");
    if (opts.bail) { await key("Escape"); return { mid, grabbed }; }
    await pe("pointerup", dx + 0.5, dy); await sleep(250);
    if (opts.shot) { await until(() => !/…/.test(dock()), 8000); await shot(opts.shot + "-staged"); }
    return { mid, grabbed };
  }
  const sent = (b) => window.__net.some((n) => (n.path === "/edit" && JSON.stringify(n.body) === JSON.stringify({ reading: S.id, ...b })) || (n.path === "/edits" && n.body.reading === S.id && n.body.edits.some((x) => JSON.stringify(x) === JSON.stringify(b))));
  // press a thing, let the rail bring the places near, wait for a place the engine accepts (✓), drop there
  async function dragToPlace(src, name, ms = 25000, not = "") {
    if (src.id) src = document.getElementById(src.id) || src;
    const [sx, sy] = center(src.tagName === "text" ? src : src.querySelector("rect") || src);
    await pe("pointermove", sx, sy); await pe("pointerdown", sx, sy);
    for (let i = 1; i <= 4; i++) { await pe("pointermove", sx + i * 3, sy + i * 3); await sleep(30); }
    const okRail = () => [...document.querySelectorAll("#board [id^=rl-]")].find((g) => g.textContent.trim().startsWith("✓"));
    let target = await until(okRail, ms);
    const mine = (g) => not && (g.id.startsWith("pl-" + not + "-") || g.id.startsWith("rl-" + not + "-"));
    if (!target) target = [...document.querySelectorAll("#board [id^=pl-]")].find((g) => g.dataset.hole === "1" && !mine(g)) || [...document.querySelectorAll("#board [id^=rl-]")].find((g) => !mine(g)) || [...document.querySelectorAll("#board [id^=pl-]")].find((g) => !mine(g));
    if (!target) { await pe("pointerup", sx, sy); return null; }
    const tid = target.id;
    const [dx, dy] = center(target.querySelector("rect"));
    for (let i = 1; i <= 8; i++) { await pe("pointermove", sx + 12 + ((dx - sx - 12) * i) / 8, sy + 12 + ((dy - sy - 12) * i) / 8); await sleep(30); }
    await until(() => !/…/.test(dock()) && dock().trim(), 15000);
    await pe("pointermove", dx + 0.5, dy); await sleep(80);
    const mid = dock();
    await shot(name + "-held");
    await pe("pointerup", dx + 0.5, dy); await sleep(300);
    await until(() => !/…/.test(dock()), 8000); await shot(name + "-staged");
    return { tid, mid, accepted: tid.startsWith("rl-") && target.textContent.trim().startsWith("✓") };
  }
  const lastEdit = () => window.__net.filter((n) => n.path === "/edit").at(-1);
  const proseCheck = () => { // every text node drawn by the page outside the message and the world/d1 data
    const out = [];
    const msg = new Set([...document.querySelectorAll("#board text.w")]);
    for (const t of document.querySelectorAll("#board text, #dock span, #dock button, header")) {
      if (msg.has(t)) continue;
      const s = (t.textContent || "").trim();
      if (/\b[a-z]+ [a-z]+ [a-z]+ [a-z]+ [a-z]+\b/i.test(s) && !isData(s)) out.push(s.slice(0, 80));
    }
    return out;
  };
  function isData(s) { // a world docstring, a d1 record, or the message's words
    const r = S.base, w = Object.values(window.board.world());
    if (r.text.includes(s.replace(/^[“"]|[”"]$/g, "").replace(/…$/, "").split("|").pop())) return true;
    const docs = JSON.stringify(window.board.world()) + JSON.stringify(r.decisions);
    return s.split(/\s+/).length < 5 || docs.includes(s.slice(0, 30)) || r.decisions.some((d) => (d.state || "").includes(s.slice(0, 30)));
  }

  const server = async (snapshot) => (await fetch("/readings").then((x) => x.json())).find((l) => l.snapshot === snapshot);
  // the links drawn now, against the server's record of the snapshot the page names (never the page's own copy)
  const linksMatch = (rec) => { const g = [...document.querySelectorAll("#board [id^=pc-]")]; return g.length > 0 && g.every((e) => (rec.pieces || []).some((p) => String(p.start) === e.dataset.start && String(p.end) === e.dataset.end && (p.kind ?? "null") === e.dataset.kind)); };
  const pause = () => sleep(450); // a person's pace after a change of page
  const typeChips = () => [...document.querySelectorAll("#board [id^=pg-b-],#board [id^=pg-u-],#board [id^=pg-a-],#board [id^=pg-p-],#board [id^=pg-r-]")];
  async function openTypedLink(test) { // click links in view until one's page passes test(); returns the link
    for (const g of [...document.querySelectorAll("#board [id^=pc-]")]) {
      const k = g.dataset.kind; if (!k || k === "(none)" || k === "null") continue;
      await key("Escape"); await pause(); await click(g); await pause();
      if (test()) return g;
    }
    return null;
  }
  window.audit5 = async function (prefixes, opts = {}) {
    const report = { when: new Date().toISOString(), readings: [], failures: [], dragology: {} };
    // G2: the page's own source registers no pointer/mouse/drag listener
    const src = await fetch("/board.js").then((r) => r.text());
    const banned = src.match(/addEventListener\(\s*["'](pointer\w+|mouse\w+|drag\w*|drop|touch\w+)["']|on(Pointer|Mouse)(Down|Move|Up)\s*[:=]|onDrag(Start|Over|End)?\s*[:=]|onDrop\s*[:=]|draggable\s*=\s*["']true/g) || [];
    report.dragology = { loaded: !!window.Dragology && !!document.querySelector('script[src*="dragology-0.2.0"]'), renderer: document.querySelectorAll("#board svg").length === 1, banned, specs: (src.match(/dragologyOnDrag/g) || []).length };
    for (const pre of prefixes) {
      const id = [...new Set(window.board.ids())].find((i) => i.startsWith(pre));
      const row = { id: pre, bad: [], did: [] };
      const ok = (c, m) => { if (!c) row.bad.push(m); else row.did.push("✓ " + m); return c; };
      await window.board.choose(id); await sleep(300);
      try {
      const r = S.base;
      row.chars = r.text.length; row.pieces = (r.pieces || []).length; row.ops = window.board.terms(r).length;
      // A: one wiki page
      const L = window.board.layout(r);
      ok(L.words.map((w) => w.str).join("") === r.text.replace(/\s+/g, "") && [...document.querySelectorAll("#board text.w")].every((t) => r.text.slice(+t.dataset.s, +t.dataset.e) === t.textContent), "A1 the words laid out are the text, once, at their places");
      ok(L.words.filter((w) => w.piece).length >= L.words.length * 0.6, "A2 the words carry their piece links");
      const drawnPc = [...document.querySelectorAll("#board [id^=pc-]")];
      const rec0 = await server(S.base.snapshot);
      ok(rec0 && rec0.text === r.text, "A0 the page draws a snapshot the server has");
      ok(rec0 && linksMatch(rec0), "A2 every drawn link = a piece of the server's record (start, end), its target = piece.kind");
      ok(document.querySelectorAll("#board [id^=op-]").length > 0 || !row.ops, "A3 function spans drawn");
      // A4/A5: open a link with the pointer: a type page and the d1 kind data
      const typed = drawnPc.find((g) => /^(Subject|Asked|Surface|Code|Words|Concept|Text|Agent)$/.test(g.dataset.kind)) || drawnPc.find((g) => g.dataset.kind !== "(none)");
      if (typed) {
        await click(typed);
        ok(S.open && S.open.t === "piece", "A4 click opens the link");
        const pageT = [...document.querySelectorAll("#board [id^=page-] text")].map((t) => t.textContent).join("\n");
        ok(pageT.includes(typed.dataset.kind) && /: \*|ƒ /.test(pageT), "A4 the page of its target from the world");
        await shot(`${pre}-a-open-link`);
        ok(/d1 · kind/.test(pageT) && document.querySelectorAll("#board [id^=pg-o-]").length >= 2, "A5 d1's options and probabilities for its words");
      }
      // A4 by keyboard: Escape, arrows to a link, Enter
      await key("Escape"); await key("ArrowRight"); await key("ArrowRight");
      const fid = S.focus; await key("Enter");
      ok(fid && S.open && S.open.t === "piece", "A4k arrows + Enter open a link");
      // B1: widen a link by its end handle (pointer)
      const hd = el("#hd-e");
      if (ok(hd, "B1 the open link has handles")) {
        const p = S.open.p, next = L.words.find((w) => w.s > p.end + 1 && w.piece && w.piece.start !== p.start && document.querySelector(`#board text.w[data-s="${w.s}"]`));
        const tgt = next && document.querySelector(`#board text.w[data-s="${next.s}"]`);
        if (tgt) {
          const q = tgt.getBoundingClientRect();
          const res = await drag(hd, [q.right - 1, q.top + q.height / 2], { shot: `${pre}-b-widen` });
          const e = S.staged && { body: S.staged.body };
          ok(e && sent(e.body) && e.body.path === "kind" && e.body.at[0] === p.start && e.body.at[1] > p.end && e.body.value === p.kind, "B1 widen = /edit kind over the wider words, same kind");
          ok(/→/.test(res.mid.dock), "B5 the consequence shows before release");
          ok(S.staged && /✓ a/.test(dock()), "B5 release stages it with Accept / Cancel");
          await click(el("#cancel"));
          await pause();
          ok(!S.staged && rec0 && linksMatch(rec0) && !/→/.test(dock()), "B5 Cancel: the drawn links are the server's record again, nothing staged");
        }
      }
      // B2: narrow by keyboard: [ on an open link of two words or more (clicked open)
      { const L2 = window.board.layout(S.base); const multi = [...document.querySelectorAll("#board [id^=pc-]")].find((g) => g.dataset.kind !== "(none)" && L2.words.filter((w) => w.s >= +g.dataset.start && w.e <= +g.dataset.end).length >= 2); await key("Escape"); await click(multi, "a link of two words"); }
      await key("["); await until(() => !/…/.test(dock()) && /→/.test(dock()), 20000);
      const e2 = S.hold && S.hold.opts[0].states && { body: S.hold.opts[0].states[S.hold.opts[0].k].change };
      ok(e2 && e2.body && sent(e2.body) && e2.body.path === "kind" && e2.body.value === "(none)", "B2k [ narrows: the last word unlinked (/edit kind (none))" + " got " + JSON.stringify({ e2, hold: !!S.hold, open: S.open && S.open.p, focus: S.focus, dock: dock() }).slice(0, 400));
      await key("Enter"); await sleep(150);
      ok(S.staged || S.note, "B2k Enter stages or shows the engine's refusal");
      await key("Escape");
      // B3: a type onto words (pointer), picked up from a link's page (no permanent world panel)
      await key("Escape"); await pause();
      const typedLink = await openTypedLink(() => typeChips().length > 0);
      if (ok(typedLink, "B3 a link whose page offers types")) {
        const chip = typeChips()[0], tname = chip.dataset.label;
        const w2 = [...document.querySelectorAll("#board [id^=pc-]")].filter((g) => g.dataset.kind !== tname && g.id !== typedLink.id)[3];
        const res = await drag(chip, w2, { shot: `${pre}-b-type` });
        const e = S.staged && { body: S.staged.body };
        ok(e && e.body.path === "kind" && e.body.value === tname && String(e.body.at[0]) === w2.dataset.start && sent(e.body), `B3 type drop = /edit kind ${tname} on those words`);
        ok(res.mid.dock.includes(tname + "|"), "B5 the new link shows before release");
        if (opts.accept && S.staged && pre === prefixes[0]) {
          await until(() => el("#accept") && !el("#accept").disabled);
          const before = S.base.snapshot;
          await click(el("#accept"));
          await until(() => S.base.snapshot !== before, 20000); await sleep(200);
          const fresh = await fetch("/readings").then((x) => x.json());
          const latest = fresh.filter((l) => l.id === id).at(-1);
          ok(latest.snapshot !== before && latest.corrections.some((c) => c.path === "kind" && c.kind === tname && String(c.at[0]) === w2.dataset.start) && latest.pieces.some((p) => p.by === "user" && p.kind === tname), "B6 after Accept and reload the store has the correction");
          await pause();
          ok(linksMatch(latest), "B6 the page draws the saved snapshot");
          await key("z"); // E: undo by keyboard
          await until(() => S.base.snapshot !== latest.snapshot, 20000); await sleep(200);
          const fresh2 = await fetch("/readings").then((x) => x.json());
          const l2 = fresh2.filter((l) => l.id === id).at(-1);
          ok(JSON.stringify(l2.pieces) === JSON.stringify(rec0.pieces) && l2.corrections.length === rec0.corrections.length, "E undo restores the snapshot before the accept, in the store");
          await pause();
          ok(linksMatch(l2), "E the page draws it");
        } else if (S.staged) await key("Escape");
      }
      // B4: a constructed type (Later[K]) onto words (pointer), from a link's page
      await key("Escape"); await pause();
      const tl2 = await openTypedLink(() => document.querySelector("#board [id^=pg-c-Later_]"));
      if (ok(tl2, "B4 a link whose page offers Later[K]")) {
        const later = el("#board [id^=pg-c-Later_]"), lname = later.dataset.label;
        const w3 = [...document.querySelectorAll("#board [id^=pc-]")].filter((g) => g.dataset.kind !== lname && g.id !== tl2.id)[2];
        const res = await drag(later, w3, { shot: `${pre}-b-later` });
        const e = S.staged && { body: S.staged.body };
        ok(e && sent(e.body) && e.body.value === lname && /^Later\[/.test(lname) && String(e.body.at[0]) === w3.dataset.start, `B4 constructed type drop = /edit kind ${lname}`);
        ok(res.mid.dock.includes(lname + "|") && S.staged, "B4 previewed and staged");
        await key("Escape");
      }
      // B3k: a type by keyboard: open a link (arrows, Enter), Tab to its page, arrows to a type, Space, arrows to words, Enter
      await key("Escape"); await pause();
      { let g = 0; await key("ArrowRight"); while (g++ < 30) { await key("Enter"); await pause(); if (typeChips().length) break; await key("Escape"); await pause(); await key("ArrowRight"); } }
      await key("Tab");
      { let g = 0; while (!typeChips().some((c) => c.id === S.focus) && g++ < 60) await key("ArrowRight"); }
      const kchip = typeChips().find((c) => c.id === S.focus);
      await key(" ");
      ok(kchip && S.hold && S.hold.th.t === "type", "B3k Space picks a type up from the page");
      if (S.hold) {
        await key("ArrowRight");
        await until(() => !/…/.test(dock()) && /→/.test(dock()), 20000);
        await key("Enter"); await sleep(100);
        const e = S.staged && { body: S.staged.body };
        ok(e && sent(e.body) && e.body.path === "kind" && e.body.value === kchip.dataset.label, "B3k Enter drops it on words (/edit kind)");
        await key("Escape");
      }
      await key("Tab"); await key("Escape"); await pause();
      // C: a rejected or open place takes words, a world member and a result
      const holes = [...document.querySelectorAll("#board [id^=pl-]")].filter((g) => g.dataset.hole === "1");
      const unres = [...document.querySelectorAll("#board [id^=un-]")];
      row.holes = holes.length; row.unresolved = unres.length;
      // C1 words → a place: one drag; while it is held the rail brings the places near; it ends on a place the engine accepts
      {
        const pc0 = [...document.querySelectorAll("#board [id^=pc-]")][5];
        const res = pc0 && await dragToPlace(pc0, `${pre}-c-words`);
        if (ok(res, "C1 a place to drop words in (in view or in the rail)")) {
          const b = (S.staged && S.staged.body) || (S.note && S.note.refused && S.note.refused.body);
          ok(b && b.number != null && b.value && b.value.constant !== undefined && b.value.at[0] >= 0 && sent(b), "C1 words into a place = /edit {constant, type, at}");
          ok(S.staged || S.note, "C1 answered: staged or refused with the engine's code");
          row.did.push("C1 " + res.tid + " " + (S.staged ? "staged" : "refused " + JSON.stringify(S.note && S.note.refused && S.note.refused.codes)));
          if (S.staged) await key("Escape");
        }
      }
      // C2 a world member → a place, picked up from a link's page
      await key("Escape"); await pause();
      const sumLink = await openTypedLink(() => document.querySelector("#board [id^=pg-m-]"));
      if (ok(sumLink, "C2 a link whose page offers members")) {
        const mem = document.querySelector("#board [id^=pg-m-]"), words = mem.dataset.label;
        const res = await dragToPlace(mem, `${pre}-c-member`); if (res) row.did.push("C2 → " + res.tid);
        const b = (S.staged && S.staged.body) || (S.note && S.note.refused && S.note.refused.body), e = b && sent(b) && { body: b };
        ok(e && e.body.value.at[0] === -1 && e.body.value.constant === words, "C2 member into a place = /edit {constant: member words, at: [-1,-1]}");
        ok(S.staged || S.note, "C2 answered");
        row.did.push("C2 " + (S.staged ? "staged" : "refused " + JSON.stringify(S.note && S.note.refused && S.note.refused.codes)));
        if (S.staged) await key("Escape");
      }
      await key("Escape"); await pause();
      // C3 a result → a later place
      const opsEl = [...document.querySelectorAll("#board [id^=op-]")];
      if (opsEl.length >= 2) {
        const srcOp = opsEl[0], tgt = [...document.querySelectorAll("#board [id^=pl-]")].find((g) => !srcOp.contains(g) && +g.dataset.op > +srcOp.dataset.op);
        if (ok(srcOp, "C3 a result to drag")) {
          const res = await dragToPlace(srcOp.querySelector("text"), `${pre}-c-result`, 25000, srcOp.dataset.op); if (res) row.did.push("C3 → " + res.tid);
          const b = (S.staged && S.staged.body) || (S.note && S.note.refused && S.note.refused.body), e = b && sent(b) && { body: b };
          ok(e && e.body.value && String(e.body.value.ref) === srcOp.dataset.op, "C3 result into a place = /edit {ref}");
          ok(S.staged || S.note, "C3 answered");
          row.did.push("C3 " + (S.staged ? "staged" : "refused " + JSON.stringify(S.note && S.note.refused && S.note.refused.codes)));
          if (S.staged) await key("Escape");
        }
      }
      // C1k: words into a place by keyboard: focus a link, Space, arrows to a place, Enter
      await key("Escape"); await key("ArrowRight");
      await key(" ");
      if (S.hold) {
        let g = 0; while (S.hold && !(S.hold.opts[S.hold.i].body && S.hold.opts[S.hold.i].body.number != null) && g++ < 400) await key("ArrowRight");
        const o = S.hold && S.hold.opts[S.hold.i];
        if (ok(o && o.body && o.body.number != null, "C1k Space + arrows reach a place")) {
          await until(() => !/…/.test(dock()) && dock().trim(), 15000);
          await key("Enter"); await sleep(150);
          const b = (S.staged && S.staged.body) || (S.note && S.note.refused && S.note.refused.body);
          ok(b && b.number === o.body.number && b.value.constant !== undefined && sent(b), "C1k Enter drops the words (the same /edit body as the pointer)");
          ok(S.staged || S.note, "C1k answered");
          if (S.staged) await key("Escape");
        }
      } else row.bad.push("C1k Space did not pick up");
      // D: while words are held, the rail's ✓/✕ equal the engine's own answer: each rail place's request, taken from what the page
      // sent, is asked again here with /edit (one by one, by the audit) and compared with the glyph drawn
      {
        await key("Escape"); await key("Escape"); await pause(); // no open link, so no handles over the words
        const pcsD = [...document.querySelectorAll("#board [id^=pc-]")];
        const src = pcsD[Math.max(0, pcsD.length - 3)]; // a link no earlier step held
        const [sx, sy] = center(src.querySelector("rect"));
        const n0 = window.__net.length;
        await pe("pointermove", sx, sy); await pe("pointerdown", sx, sy); await pe("pointermove", sx + 7, sy + 7);
        await until(() => document.querySelector("#board [id^=rl-]") && window.board.idleQ(), 30000); await sleep(200);
        await pe("pointermove", sx + 8, sy + 8); await sleep(250);
        const railEls = [...document.querySelectorAll("#board [id^=rl-]")].map((g) => ({ id: g.id.slice(3), t: g.textContent.trim(), bottom: g.getBoundingClientRect().bottom }));
        const batch = window.__net.slice(n0).filter((n) => n.path === "/edits").at(-1);
        await key("Escape"); await pe("pointerup", sx, sy); await sleep(200);
        if (S.staged) await key("Escape");
        let agree = 0, disagree = [];
        for (const r of railEls) {
          const mineB = (x) => `${x.number}-${x.path.replace(/\./g, "_")}` === r.id && x.value && x.value.at && String(x.value.at[0]) === src.dataset.start && String(x.value.at[1]) === src.dataset.end;
          const nb = window.__net.filter((n) => n.path === "/edits" && n.body.reading === S.id && n.body.edits.some(mineB)).at(-1);
          const b = nb && nb.body.edits.find(mineB);
          if (!b) { if (!r.t.startsWith("…")) disagree.push(r.id + " no request"); continue; }
          const ans = await fetch("/edit", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reading: S.id, ...b }) }).then((x) => x.json());
          const engineOk = !ans.error && ans.draft && !(ans.diagnostics || []).length;
          if (r.t.startsWith("…") || (engineOk ? r.t.startsWith("✓") : r.t.startsWith("✕"))) agree++; else disagree.push(r.id + " drawn " + r.t.slice(0, 1) + " engine " + (engineOk ? "ok" : JSON.stringify(ans.diagnostics || ans.error)));
        }
        ok(window.__net.some((n) => n.path === "/edits" && n.body.reading === S.id && n.body.edits.some((x) => x.value && x.value.at && String(x.value.at[0]) === src.dataset.start)) && railEls.length > 0, "D1 holding words asks the engine for its places with /edits, and the rail shows places" + ` (${src.id}; rail ${railEls.map((r) => r.t.slice(0, 1)).join("")}; batches ${window.__net.slice(n0).filter((n) => n.path === "/edits").length})`);
        ok(disagree.length === 0, "D1 every ✓/✕ in the rail equals the engine's /edit answer for that place" + (disagree.length ? ": " + disagree.slice(0, 3).join("; ") : ""));
        ok(railEls.every((r) => r.bottom <= innerHeight), "D2 the rail is in view");
        row.did.push(`D rail ${railEls.length}: agree ${agree}`);
      }
      // F: no agent prose
      const prose = proseCheck();
      ok(prose.length === 0, "F no sentence written by the page" + (prose.length ? ": " + prose.slice(0, 3).join(" / ") : ""));
      } catch (e) { row.bad.push("threw: " + e.message + " " + (e.stack || "").split("\n")[1]); }
      report.readings.push(row);
      if (row.bad.length) report.failures.push({ id: pre, bad: row.bad });
    }
    report.posts = window.__net.reduce((m, n) => ((m[n.path] = (m[n.path] || 0) + 1), m), {});
    report.summary = { readings: prefixes.length, failing: report.failures.length, banned: report.dragology.banned.length };
    return report;
  };
  window.auditKit = { sleep, center, pe, click, key, until, drag, dock, lastEdit, shot, trusted };
})();
