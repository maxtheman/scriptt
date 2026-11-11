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
  const click = async (el, what = "") => { if (!el) throw new Error("nothing to click " + what); const [x, y] = center(el.querySelector("rect") || el); if (trusted()) { await pe("pointermove", x, y); await pe("pointerdown", x, y); await pe("pointerup", x, y); } else { const t = await pe("pointerdown", x, y); await pe("pointerup", x, y); t.dispatchEvent(new MouseEvent("click", { bubbles: true, clientX: x, clientY: y })); } await sleep(150); };
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
  const sent = (b) => window.__net.some((n) => n.path === "/edit" && JSON.stringify(n.body) === JSON.stringify({ reading: S.id, ...b }));
  // press a thing, let the rail bring the places near, wait for a place the engine accepts (✓), drop there
  async function dragToPlace(src, name, ms = 25000) {
    if (src.id) src = document.getElementById(src.id) || src;
    const [sx, sy] = center(src.querySelector("rect") || src);
    await pe("pointermove", sx, sy); await pe("pointerdown", sx, sy);
    for (let i = 1; i <= 4; i++) { await pe("pointermove", sx + i * 3, sy + i * 3); await sleep(30); }
    const okRail = () => [...document.querySelectorAll("#board [id^=rl-]")].find((g) => g.textContent.trim().startsWith("✓"));
    let target = await until(okRail, ms);
    if (!target) target = [...document.querySelectorAll("#board [id^=pl-]")].find((g) => g.dataset.hole === "1") || document.querySelector("#board [id^=rl-]");
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
      ok(drawnPc.length > 0 && drawnPc.every((g) => (r.pieces || []).some((p) => String(p.start) === g.dataset.start && (p.kind ?? "null") === g.dataset.kind)), "A2 every drawn link = a piece, its target = piece.kind");
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
          ok(!S.staged && JSON.stringify(S.base.pieces) === JSON.stringify(r.pieces), "B5 Cancel restores the base");
        }
      }
      // B2: narrow by keyboard: [ on an open link of two words or more (clicked open)
      { const L2 = window.board.layout(S.base); const multi = [...document.querySelectorAll("#board [id^=pc-]")].find((g) => g.dataset.kind !== "(none)" && L2.words.filter((w) => w.s >= +g.dataset.start && w.e <= +g.dataset.end).length >= 2); await key("Escape"); await click(multi, "a link of two words"); }
      await key("["); await until(() => !/…/.test(dock()) && /→/.test(dock()), 20000);
      const e2 = S.hold && S.hold.opts[0].states && { body: S.hold.opts[0].states[S.hold.opts[0].k].change };
      ok(e2 && e2.body && sent(e2.body) && e2.body.path === "kind" && e2.body.value === "(none)", "B2k [ narrows: the last word unlinked (/edit kind (none))");
      await key("Enter"); await sleep(150);
      ok(S.staged || S.note, "B2k Enter stages or shows the engine's refusal");
      await key("Escape");
      // B3: a world type onto words (pointer)
      await key("Escape"); await sleep(80);
      const words2 = [...document.querySelectorAll("#board [id^=pc-]")].filter((g) => g.dataset.kind !== "Code");
      const w2 = words2[Math.min(3, words2.length - 1)];
      const codeChip = el("#wd-t-Code");
      if (ok(codeChip && w2, "B3 a type in the world and words to drop it on")) {
        const res = await drag(codeChip, w2, { shot: `${pre}-b-type` });
        const e = S.staged && { body: S.staged.body };
        ok(e && e.body.path === "kind" && e.body.value === "Code" && String(e.body.at[0]) === w2.dataset.start && sent(e.body), "B3 type drop = /edit kind Code on those words");
        ok(/Code\|/.test(res.mid.dock), "B5 the new link shows before release");
        ok(S.staged, "B3 staged");
        if (opts.accept && S.staged && pre === prefixes[0]) {
          await until(() => el("#accept") && !el("#accept").disabled);
          const before = S.base.snapshot;
          await click(el("#accept"));
          await until(() => S.base.snapshot !== before, 20000); await sleep(200);
          const fresh = await fetch("/readings").then((x) => x.json());
          const latest = fresh.filter((l) => l.id === id).at(-1);
          ok(latest.snapshot !== before && latest.corrections.some((c) => c.path === "kind" && c.kind === "Code" && String(c.at[0]) === w2.dataset.start) && latest.pieces.some((p) => p.by === "user" && p.kind === "Code"), "B6 after Accept and reload the store has the correction");
          // E: undo by keyboard
          await key("z");
          await until(() => S.base.snapshot !== latest.snapshot, 20000); await sleep(200);
          const fresh2 = await fetch("/readings").then((x) => x.json());
          const l2 = fresh2.filter((l) => l.id === id).at(-1);
          ok(JSON.stringify(l2.pieces) === JSON.stringify(r.pieces) && l2.corrections.length === r.corrections.length, "E undo restores the snapshot before the accept, in the store");
        } else if (S.staged) await key("Escape");
      }
      // B4: a constructed type onto words (pointer): from the type page of Surface (Later[Surface])
      await key("Escape"); await key("Escape"); await sleep(100); await click(el("#wd-t-Surface")); await sleep(150);
      const later = el("#pg-c-Later_Surface_");
      const w3 = [...document.querySelectorAll("#board [id^=pc-]")].filter((g) => g.dataset.kind !== "Later[Surface]")[2];
      if (ok(later && w3, "B4 Later[Surface] on the type page")) {
        const res = await drag(later, w3, { shot: `${pre}-b-later` });
        const e = S.staged && { body: S.staged.body };
        ok(e && sent(e.body) && e.body.value === "Later[Surface]" && String(e.body.at[0]) === w3.dataset.start, "B4 constructed type drop = /edit kind Later[Surface]");
        ok(/Later\[Surface\]\|/.test(res.mid.dock) && S.staged, "B4 previewed and staged");
        await key("Escape");
      }
      // B3k: a type by keyboard: Tab to the world, arrows to a type, Space, arrows to words, Enter
      await key("Escape"); await key("Escape"); await sleep(60);
      await key("Tab");
      let guard = 0; while (!(S.focus || "").startsWith("wd-t-Surface") && guard++ < 40) await key("ArrowRight");
      await key(" ");
      ok(S.hold && S.hold.th.t === "type", "B3k Space picks a type up");
      if (S.hold) {
        await key("ArrowRight");
        await until(() => !/…/.test(dock()) && /→/.test(dock()), 20000);
        await key("Enter"); await sleep(100);
        const e = S.staged && { body: S.staged.body };
        ok(e && sent(e.body) && e.body.path === "kind" && e.body.value === "Surface", "B3k Enter drops it on words (/edit kind Surface)");
        ok(S.staged, "B3k staged");
        await key("Escape");
      }
      await key("Tab");
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
      // C2 a world member → a place
      await key("Escape"); await key("Escape"); await sleep(100); await click(el("#wd-t-Surface")); await sleep(150);
      const mem = el("#pg-m-Surface-MOD");
      const place = holes[0] || document.querySelector("#board [id^=pl-]");
      if (ok(mem && place, "C2 a member and a place")) {
        const res = await dragToPlace(mem, `${pre}-c-member`); if (res) row.did.push("C2 → " + res.tid);
        const b = (S.staged && S.staged.body) || (S.note && S.note.refused && S.note.refused.body), e = b && sent(b) && { body: b };
        ok(e && e.body.value.at[0] === -1 && e.body.value.constant === "the mod", "C2 member into a place = /edit {constant: member words, at: [-1,-1]}");
        ok(S.staged || S.note, "C2 answered");
        row.did.push("C2 " + (S.staged ? "staged" : "refused " + JSON.stringify(S.note && S.note.refused && S.note.refused.codes)));
        if (S.staged) await key("Escape");
      }
      await key("Escape");
      // C3 a result → a later place
      const opsEl = [...document.querySelectorAll("#board [id^=op-]")];
      if (opsEl.length >= 2) {
        const srcOp = opsEl[0], tgt = [...document.querySelectorAll("#board [id^=pl-]")].find((g) => !srcOp.contains(g) && +g.dataset.op > +srcOp.dataset.op);
        if (ok(srcOp, "C3 a result to drag")) {
          const res = await dragToPlace(srcOp, `${pre}-c-result`); if (res) row.did.push("C3 → " + res.tid);
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
          ok(b && b.number === o.body.number && b.value.constant !== undefined && window.__net.some((n) => n.path === "/edit" && JSON.stringify({ reading: S.id, ...b }) === JSON.stringify(n.body)), "C1k Enter drops the words (the same /edit body as the pointer)");
          ok(S.staged || S.note, "C1k answered");
          if (S.staged) await key("Escape");
        }
      } else row.bad.push("C1k Space did not pick up");
      // D: while held, only engine-accepted places in the rail; refused ones are not targets
      {
        const src = document.querySelectorAll("#board [id^=pc-]")[4];
        const [sx, sy] = center(src.querySelector("rect"));
        await pe("pointerdown", sx, sy); await pe("pointermove", sx + 7, sy + 7);
        await until(() => window.board.idleQ(), 30000); await pe("pointermove", sx + 8, sy + 8); await sleep(150);
        const rails = [...document.querySelectorAll("#board [id^=rl-]")].map((g) => g.id.slice(3));
        const held = window.board.held();
        const verdicts = held && held.places ? held.places.map((o) => [o.target.slice(3), window.board.verdict(window.board.peek(o.body))]) : [];
        ok(rails.length === 0 || rails.every((k) => verdicts.some(([t, v]) => t === k && v !== "no")), "D1 the rail holds only places the engine did not refuse");
        ok(verdicts.filter(([, v]) => v === "no").every(([t]) => !rails.includes(t)), "D1 refused places are not in the rail");
        const railBox = document.querySelector("#board [id^=rl-]");
        ok(!railBox || (railBox.getBoundingClientRect().bottom <= innerHeight), "D2 the rail is in view");
        row.did.push(`D verdicts ok ${verdicts.filter(([, v]) => v === "ok").length} / no ${verdicts.filter(([, v]) => v === "no").length}; rail ${rails.length}`);
        await key("Escape"); await pe("pointerup", sx, sy); await sleep(150);
        if (S.staged) await key("Escape");
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
