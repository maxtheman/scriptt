// Board 4 audit, run in the page: eval the text of this file, then `await audit4(["ffe36f", ...])`. It drives the page's own handlers with
// pointer and keyboard events dispatched at real coordinates (elementsFromPoint decides the target, as for a person) and reads the page's
// network log. It never calls /accept; every drop is a /edit preview and is cancelled. Returns a report object.
window.audit4 = async function (prefixes, opts = {}) {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const settle = async () => { for (let i = 0; i < 40; i++) { await sleep(60); if (!S.held && !(S.hover && !S.hover.res)) break; } await sleep(120); };
  const center = e => { const q = e.getBoundingClientRect(); return [q.left + q.width / 2, q.top + q.height / 2]; };
  const ev = (type, x, y, target, extra = {}) => (target || document).dispatchEvent(new PointerEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y, button: 0, buttons: type === "pointerup" ? 0 : 1, pointerId: 1, isPrimary: true, ...extra }));
  const key = (target, k, extra = {}) => { target.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true, ...extra })); };
  const drag = async (src, dst, bail) => {
    dst.scrollIntoView({ block: "center" }); await sleep(30);
    const [sx, sy] = center(src), [dx, dy] = center(dst);
    ev("pointerdown", sx, sy, src); ev("pointermove", sx + 8, sy + 8, src); ev("pointermove", (sx + dx) / 2, (sy + dy) / 2, document.body); ev("pointermove", dx, dy, dst);
    await sleep(250);
    const mid = document.querySelector("#dock").innerText;
    if (bail) { key(document.body, "Escape"); await settle(); return { mid, held: true }; }
    ev("pointerup", dx, dy, dst); await settle();
    return { mid };
  };
  const wordsOf = (a, b) => { const ws = [...document.querySelectorAll("#text .w")]; return ws.filter(w => +w.dataset.s >= a && +w.dataset.e <= b); };
  const textNow = () => document.querySelector("#text").textContent;
  const report = { readings: [], failures: [], posts: {} };
  const net0 = window.__net.length;
  for (const pre of prefixes) {
    const id = [...new Set(S.lines.map(l => l.id))].find(i => i.startsWith(pre));
    S.id = id; S.sel = S.pending = S.held = null; S.span = null; S.cursor = 0; await load(); render(); await sleep(50);
    const r = S.base, row = { id: pre, chars: r.text.length, phrases: r.phrases.length, ops: terms(r).length, bad: [], did: [] };
    const fail = m => { row.bad.push(m); };
    const ok = (c, m) => { if (!c) fail(m); };
    ok(document.querySelectorAll("#text .w").length > r.text.split(/\s+/).length * 0.8, "W1 words rendered");
    ok(document.querySelectorAll(".ph.req").length === r.phrases.filter(p => p.terms.length).length, "W2 request phrases marked");
    ok(document.querySelectorAll(".ph.none").length === r.phrases.filter(p => !p.terms.length && !p.unresolved.length).length, "W3 request-free phrases marked");
    ok(document.querySelectorAll(".pl.hole").length === [...terms(r)].flatMap(t => places(t)).filter(p => p.value.hole).length, "W4 open places shown");
    ok([...document.querySelectorAll(".pl.hole")].every(e => /open ·/.test(e.textContent)), "W5 open place says why in words");
    const copy = document.querySelector("#text").cloneNode(true); copy.querySelectorAll(".brick,.unres-chip,.hdl").forEach(e => e.remove());
    ok(copy.textContent === r.text, "R1 text equals the source (one representation)");
    const before = textNow();
    // A: click a rejected/open hole: the inspector says what d1 was offered
    const hole = document.querySelector(".pl.hole");
    if (hole) {
      hole.scrollIntoView({ block: "center" }); hole.click(); await sleep(80);
      const insp = document.querySelector("#insp");
      ok(!insp.hidden && /open:/i.test(insp.innerText), "A1 click on an open place opens it with its reason");
      ok(/what d1 was asked here/i.test(insp.innerText) && insp.querySelectorAll(".opt").length > 0, "A2 shows d1's question and options");
      ok(/put something here/i.test(insp.innerText) && insp.querySelectorAll("button.chip").length > 0, "A3 offers values to put there");
      row.did.push("clicked open place " + hole.dataset.place);
      // A4: choose a candidate in the inspector: engine preview, staged or refused, never silent
      const n0 = window.__net.length; const c = insp.querySelector("button.chip"); if (c) { c.click(); await settle(); ok(S.pending || S.refused, "A4 candidate click answers (staged or refused)"); key(document.body, "Escape"); key(document.body, "Escape"); S.refused = null; if (S.pending) cancel(); S.sel = null; render(); }
    }
    // B: words into an open hole by pointer: select span near the hole's phrase, drag it onto the hole
    const holeKeys = [...document.querySelectorAll(".pl.hole")].map(e => e.dataset.place);
    let staged = 0, refused = 0;
    for (const hk of holeKeys.slice(0, 3)) {
      const h = document.querySelector(`[data-place="${CSS.escape(hk)}"]`);
      const ph = h.closest(".ph"), ws = [...ph.querySelectorAll(".w")];
      if (ws.length < 2) continue;
      h.scrollIntoView({ block: "center" });
      const i0 = W.findIndex(w => w.el === ws[0]), i1 = W.findIndex(w => w.el === ws[Math.min(ws.length - 1, 2)]);
      const [x0, y0] = center(ws[0]), [x1, y1] = center(ws[Math.min(ws.length - 1, 2)]);
      ev("pointerdown", x0, y0, ws[0]); ev("pointermove", x0 + 10, y0, ws[0]); ev("pointermove", x1, y1, ws[Math.min(ws.length - 1, 2)]); ev("pointerup", x1, y1, ws[Math.min(ws.length - 1, 2)]);
      await sleep(60);
      ok(S.span && S.span.b - S.span.a >= 1, "B1 pointer selects a span of words");
      const grab = W[S.span.a].el, mid = (S.span.a + S.span.b) >> 1;
      const res = await drag(W[mid].el, h);
      const was = window.__net.filter(n => n.path === "/edit").at(-1);
      ok(was && was.body.path === h.dataset.path && was.body.number === +h.dataset.op && was.body.value.constant !== undefined && was.body.value.at[0] >= 0, "B2 the drop sent /edit with the span and its place");
      const verdictNow = S.pending ? "staged" : S.refused ? "refused" : "?";
      if (S.pending) { staged++; ok(document.querySelector("#accept"), "B3 staged shows Accept"); cancel(); } else if (S.refused) { refused++; ok(/engine|rule|type/i.test(document.querySelector("#dock").innerText), "B4 refusal says why"); S.refused = null; paintDock(); }
      else fail("B5 drop neither staged nor refused: held=" + !!S.held + " hover=" + JSON.stringify(S.hover && { k: S.hover.key, r: !!S.hover.res }) + " dock=" + document.querySelector("#dock").innerText.slice(0, 120));
      ok(textNow() === before, "B6 text unchanged after cancel");
      row.did.push(`span→${hk}: ${verdictNow}`);
    }
    // C: a world member into a place
    document.querySelector("#world details[data-k=members]").open = true;
    let mem = document.querySelector('[data-pick=member][data-member="PAGE"]');
    const filledSurface = [...document.querySelectorAll(".pl")].find(p => termById(S.base, p.dataset.op) && declared(termById(S.base, p.dataset.op), p.dataset.path) === "Surface");
    if (mem && filledSurface) {
      const res = await drag(mem, filledSurface);
      const was = window.__net.filter(n => n.path === "/edit").at(-1);
      ok(was && was.body.value.at[0] === -1 && was.body.value.constant === "the page", "C1 member dropped with no span");
      ok(S.pending ? /the page/.test(document.querySelector("#dock").innerText) : (!!S.refused || /already/.test(document.querySelector("#dock").innerText)), "C2 member drop answered");
      row.did.push(`member the page→${filledSurface.dataset.place}: ${S.pending ? "staged" : "refused"}`);
      if (S.pending) cancel(); S.refused = null; paintDock();
      mem = document.querySelector('[data-pick=member][data-member="PAGE"]');
    }
    // D: member into a place of another type: refused with the engine's reason
    document.querySelector("#world details[data-k=members]").open = true; mem = document.querySelector('[data-pick=member][data-member="PAGE"]');
    const anyHole = document.querySelector(".pl.hole") || document.querySelector(".pl");
    if (mem && anyHole) { await drag(mem, anyHole); ok(S.pending || S.refused, "D1 any drop is answered"); if (S.refused) ok(/\[\[/.test(document.querySelector("#dock").innerText), "D2 refusal shows the engine's diagnostics"); if (S.pending) cancel(); S.refused = null; paintDock(); }
    // E: a result (synthesized) into a place
    let ops = [...document.querySelectorAll(".op[data-op]")];
    if (ops.length >= 2) {
      const src = ops[0], target = [...document.querySelectorAll(".pl")].find(p => p.dataset.op !== src.dataset.op);
      if (target) { await drag(src, target); const was = window.__net.filter(n => n.path === "/edit").at(-1); ok(was && was.body.value.ref === src.dataset.op, "E1 result dropped as {ref}"); ok(S.pending || S.refused || /already/.test(document.querySelector("#dock").innerText), "E2 answered"); row.did.push(`result ${src.dataset.op}→${target.dataset.place}: ${S.pending ? "staged" : "refused"}`); if (S.pending) cancel(); S.refused = null; paintDock(); }
    }
    // F: retag: a filled place's value onto another place
    ops = [...document.querySelectorAll(".op[data-op]")];
    const filled = [...document.querySelectorAll(".pl.filled")];
    if (filled.length >= 1) {
      const src = filled[0], target = [...document.querySelectorAll(".pl")].find(p => p !== src);
      if (target) { await drag(src, target); const was = window.__net.filter(n => n.path === "/edit").at(-1); ok(was && was.body.value.constant !== undefined, "F1 retag sends the place's value"); ok(S.pending || S.refused || /already/.test(document.querySelector("#dock").innerText), "F2 answered"); row.did.push(`retag ${src.dataset.place}→${target.dataset.place}: ${S.pending ? "staged" : "refused"}`); if (S.pending) cancel(); S.refused = null; paintDock(); }
    }
    // G: a function onto a request-free phrase
    ops = [...document.querySelectorAll(".op[data-op]")];
    document.querySelector("#world details[data-k=fns]").open = true;
    const fn = document.querySelector("[data-pick=fn][data-fn=explain]"), none = [...document.querySelectorAll(".ph.none")].find(p => p.textContent.trim().length > 20);
    if (fn && none) {
      const w = none.querySelector(".w"); const res = await drag(fn, w);
      const was = window.__net.filter(n => n.path === "/edit").at(-1);
      ok(was && was.body.number === null && /^explain\./.test(was.body.path), "G1 function dropped on a phrase sends number null and function.parameter");
      ok(S.pending ? /new operation explain/.test(document.querySelector("#dock").innerText) : !!S.refused, "G2 answered");
      row.did.push(`explain→phrase ${none.dataset.ph}: ${S.pending ? "staged" : "refused"}`);
      if (S.pending) cancel(); S.refused = null; paintDock();
    }
    // H: keyboard parity: word → shift+arrows → space → o → enter
    S.span = null; setSpan(null);
    const hole2 = document.querySelector(".pl.hole");
    if (hole2) {
      const ph = hole2.closest(".ph"), w = ph.querySelector(".w"); w.scrollIntoView({ block: "center" }); w.focus(); await sleep(30);
      for (let i = 0; i < 2; i++) key(document.activeElement, "ArrowRight", { shiftKey: true });
      ok(S.span && S.span.b - S.span.a === 2, "H1 shift+arrow extends the selection");
      key(document.activeElement, " "); await sleep(30);
      ok(S.held && S.held.kind === "words", "H2 space picks the selection up");
      ok(document.activeElement.dataset && document.activeElement.dataset.place, "H3 focus moves to a place");
      key(document.activeElement, "o"); await sleep(30);
      const f = document.activeElement; ok(f.classList.contains("pl") && f.classList.contains("hole"), "H4 'o' jumps to an open place");
      await sleep(250);
      ok(/Fits|Refused/.test(document.querySelector("#dock").innerText), "H5 focus previews through the engine");
      key(f, "Enter"); await settle();
      const was = window.__net.filter(n => n.path === "/edit").at(-1);
      ok(was && was.body.path === f.dataset.path && was.body.value.constant !== undefined, "H6 Enter dropped (same /edit body shape as the pointer)");
      ok(S.pending || S.refused, "H7 answered");
      if (S.pending) { key(document.activeElement, "Escape"); await sleep(30); ok(!S.pending && textNow() === before, "H8 Escape cancels, text equal"); }
      S.refused = null; paintDock();
    }
    // I: Escape mid-hold, drop outside
    ops = [...document.querySelectorAll(".op[data-op]")]; if (ops[0]) ops[0].scrollIntoView({ block: "center" });
    if (ops[0]) { const [sx, sy] = center(ops[0]); ev("pointerdown", sx, sy, ops[0]); ev("pointermove", sx + 9, sy + 9, ops[0]); await sleep(30); ok(S.held, "I1 hold"); key(document.body, "Escape"); await sleep(30); ok(!S.held && !document.querySelector(".ghost"), "I2 escape clears hold and ghost"); ev("pointerup", sx, sy, document.body); }
    report.readings.push(row); if (row.bad.length) report.failures.push({ id: pre, bad: row.bad });
  }
  report.posts = window.__net.slice(net0).reduce((m, n) => (m[n.path] = (m[n.path] || 0) + 1, m), {});
  report.summary = { readings: prefixes.length, failures: report.failures.length };
  return report;
};
