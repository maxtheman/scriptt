// Board 5 audit. Run by web/audit-run.mjs (headless Chrome over CDP): every pointer and key event is a trusted browser input event
// made by Chrome, and what was sent to the engine is Chrome's own network record (__cdpNet), not the page's log.
// `await audit5(["8c7eae08", ...], {accept: true})`. Without the driver it falls back to dispatched events and the page's log.
// The audit never calls the page's functions to move or change things; it uses the page API only to wait and to pick the reading.
(function () {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const center = (e) => { const q = e.getBoundingClientRect(); return [q.left + q.width / 2, q.top + q.height / 2]; };
  const at = (x, y) => document.elementFromPoint(x, y) || document.body;
  window.__cdpWait = window.__cdpWait || {};
  window.__cdpDone = (id) => { const f = window.__cdpWait[id]; delete window.__cdpWait[id]; if (f) f(); };
  const bridge = (g) => new Promise((res) => { const id = String(Math.random()); window.__cdpWait[id] = res; window.cdpInput(JSON.stringify({ id, ...g })); });
  const trusted = () => typeof window.cdpInput === "function";
  const pe = async (type, x, y) => {
    if (trusted()) { await bridge({ type, x: Math.round(x * 10) / 10, y: Math.round(y * 10) / 10 }); return at(x, y); }
    const el = at(x, y); el.dispatchEvent(new PointerEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y, button: 0, buttons: type === "pointerup" ? 0 : 1, pointerId: 1, isPrimary: true, pointerType: "mouse" })); return el;
  };
  const rectOf = (el) => (el.tagName === "text" ? el : el.querySelector(":scope > rect") || el.querySelector("rect") || el);
  const click = async (el, what = "") => {
    if (!el) throw new Error("nothing to click " + what);
    if (el.id) el = document.getElementById(el.id) || el;
    const [x, y] = center(rectOf(el));
    if (trusted()) { await pe("pointermove", x, y); await pe("pointerdown", x, y); await pe("pointerup", x, y); }
    else { const t = await pe("pointerdown", x, y); await pe("pointerup", x, y); t.dispatchEvent(new MouseEvent("click", { bubbles: true, clientX: x, clientY: y })); }
    await sleep(150);
  };
  const key = async (k, extra = {}) => { if (trusted()) await bridge({ type: "key", key: k, ...extra }); else document.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true, ...extra })); await sleep(60); };
  const shot = async (name) => { if (trusted()) await bridge({ type: "shot", name }); };
  const syncNet = async () => { if (trusted()) { await sleep(120); await bridge({ type: "noop" }); } };
  const until = async (f, ms = 8000) => { const t = Date.now(); while (Date.now() - t < ms) { const v = f(); if (v) return v; await sleep(60); } return null; };
  const dock = () => document.getElementById("dock").innerText;
  const el = (sel) => document.querySelector(sel);
  const all = (sel) => [...document.querySelectorAll(sel)];
  const pause = () => sleep(450); // a person's pace after a change of page (the page fades between pages)
  const net = () => (trusted() ? window.__cdpNet || [] : window.__net);
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  // the request went to the engine: as one /edit, or inside one /edits batch
  const sent = (b) => net().some((n) => (n.path === "/edit" && same(n.body, { reading: S.id, ...b })) || (n.path === "/edits" && n.body && n.body.reading === S.id && n.body.edits.some((x) => same(x, b))));
  const linksNow = () => all("#board [id^=pc-]").map((e) => ({ id: e.id, start: +e.dataset.start, end: +e.dataset.end, kind: e.dataset.kind }));
  const server = async (snapshot) => (await fetch("/readings").then((x) => x.json())).find((l) => l.snapshot === snapshot);
  const linksMatch = (rec) => { const g = linksNow(); return g.length > 0 && g.every((e) => (rec.pieces || []).some((p) => p.start === e.start && p.end === e.end && (p.kind ?? "null") === e.kind)); };
  const staged = () => S.staged && S.staged.body;
  const refusedBody = () => S.note && S.note.refused && S.note.refused.body;
  const typeChips = () => all("#board [id^=pg-b-],#board [id^=pg-u-],#board [id^=pg-a-],#board [id^=pg-p-],#board [id^=pg-r-]");
  const railOk = () => all("#board [id^=rl-]").filter((g) => g.dataset.verdict === "ok" && g.id !== "rl-info");
  const railReady = () => !el("#rl-wait") && !!el("#rl-info");

  // a drag: press on src, move in steps, wait for the engine's draft under the pointer, read what is drawn, release
  async function drag(src, to, opts = {}) {
    if (src.id) src = document.getElementById(src.id) || src;
    if (to && to.id) to = document.getElementById(to.id) || to;
    const [sx, sy] = center(rectOf(src));
    const [dx, dy] = Array.isArray(to) ? to : center(rectOf(to));
    await pe("pointermove", sx, sy); await pe("pointerdown", sx, sy);
    for (let i = 1; i <= 8; i++) { await pe("pointermove", sx + ((dx - sx) * i) / 8, sy + ((dy - sy) * i) / 8); await sleep(25); }
    await until(() => !/…/.test(dock()) && dock().trim(), opts.wait || 15000);
    await pe("pointermove", dx + 0.5, dy); await sleep(80);
    const mid = { dock: dock(), links: linksNow(), places: all("#board [id^=pl-]").map((g) => [g.id, [...g.querySelectorAll("text")].map((t) => t.textContent).filter((t) => t !== "✓" && t !== "✕").pop()]) };
    if (opts.shot) await shot(opts.shot + "-held");
    await pe("pointerup", dx + 0.5, dy); await sleep(300);
    if (opts.shot) { await until(() => !/…/.test(dock()), 8000); await shot(opts.shot + "-staged"); }
    await syncNet();
    return { mid };
  }
  // press a thing; once the rail is laid out from the engine's answers, drop on a place it accepts (✓)
  async function dragToAccepted(src, name) {
    if (src.id) src = document.getElementById(src.id) || src;
    const [sx, sy] = center(rectOf(src));
    await pe("pointermove", sx, sy); await pe("pointerdown", sx, sy);
    for (let i = 1; i <= 4; i++) { await pe("pointermove", sx + i * 3, sy + i * 3); await sleep(30); }
    await until(railReady, 30000); await pe("pointermove", sx + 13, sy + 13); await sleep(200);
    const target = railOk()[0];
    if (!target) { await pe("pointerup", sx + 13, sy + 13); await sleep(200); await syncNet(); return { none: true, rail: all("#board [id^=rl-]").length }; }
    const tid = target.id, [dx, dy] = center(rectOf(target));
    for (let i = 1; i <= 8; i++) { await pe("pointermove", sx + 13 + ((dx - sx - 13) * i) / 8, sy + 13 + ((dy - sy - 13) * i) / 8); await sleep(30); }
    await until(() => !/…/.test(dock()) && dock().trim(), 15000);
    await pe("pointermove", dx + 0.5, dy); await sleep(80);
    const mid = { dock: dock(), places: all("#board [id^=pl-]").map((g) => [g.id, [...g.querySelectorAll("text")].map((t) => t.textContent).filter((t) => t !== "✓" && t !== "✕").pop()]) };
    await shot(name + "-held");
    await pe("pointerup", dx + 0.5, dy); await sleep(300);
    await until(() => !/…/.test(dock()), 8000); await shot(name + "-staged");
    await syncNet();
    return { tid, mid };
  }
  async function openLink(test) { // click links in view until one's page passes test(); returns the link
    for (const g of all("#board [id^=pc-]")) {
      const k = g.dataset.kind; if (!k || k === "(none)" || k === "null") continue;
      await key("Escape"); await pause(); await click(g); await pause();
      if (test()) return document.getElementById(g.id) || g;
    }
    return null;
  }
  const reset = async () => { for (let i = 0; i < 3; i++) await key("Escape"); await pause(); };
  // F: every text the page draws outside the message: a sentence (four words or more) must be the record's or the world's own words
  function proseCheck() {
    const msg = new Set(all("#board text.w")), out = [];
    const data = S.base.text + JSON.stringify(window.board.world()) + JSON.stringify(S.base.decisions);
    for (const t of [...all("#board text"), ...all("#dock span"), ...all("#dock button"), ...all("header span, header strong").filter((e) => !e.querySelector("span"))]) { // leaf texts only
      if (msg.has(t)) continue;
      const s = (t.textContent || "").trim();
      const words = s.match(/[A-Za-z]{2,}/g) || [];
      if (words.length >= 4 && !words.every((w) => data.includes(w))) out.push(s.slice(0, 80));
    }
    return out;
  }

  window.audit5 = async function (prefixes, opts = {}) {
    const report = { when: new Date().toISOString(), trusted: trusted(), readings: [], failures: [], dragology: {} };
    const src = await fetch("/board.js").then((r) => r.text());
    const banned = src.match(/addEventListener\(\s*["'](pointer\w+|mouse\w+|drag\w*|drop|touch\w+)["']|on(Pointer|Mouse)(Down|Move|Up)\s*[:=]|onDrag(Start|Over|End)?\s*[:=]|onDrop\s*[:=]|draggable\s*=\s*["']true/g) || [];
    report.dragology = { loaded: !!window.Dragology && !!document.querySelector('script[src*="dragology-0.2.0"]'), renderer: all("#board svg").length === 1, banned, specs: (src.match(/dragologyOnDrag/g) || []).length };
    for (const pre of prefixes) {
      const id = window.board.ids().find((i) => i.startsWith(pre));
      const row = { id: pre, bad: [], did: [] };
      const ok = (c, m) => { if (!c) row.bad.push(m); else row.did.push("✓ " + m); return c; };
      await window.board.choose(id); await sleep(400);
      try {
        const r = S.base;
        const rec0 = await server(S.base.snapshot);
        row.chars = r.text.length; row.pieces = (rec0.pieces || []).length;
        // ---- A: one wiki page
        ok(rec0 && rec0.text === r.text, "A0 the page draws a snapshot the server has");
        ok(all("#board text.w").every((t) => rec0.text.slice(+t.dataset.s, +t.dataset.e) === t.textContent) && all("#board text.w").length > 50, "A1 every word drawn is the text at its place");
        const L = window.board.layout(r);
        ok(L.words.map((w) => w.str).join("") === rec0.text.replace(/\s+/g, ""), "A1 the layout holds the whole text once");
        ok(linksMatch(rec0), "A2 every drawn link = a piece of the server's record, its target = piece.kind");
        const opsIds = rec0.phrases.flatMap((p) => p.terms.map((t) => t.id));
        const drawnOps = all("#board [id^=op-]");
        ok(drawnOps.length > 0 && drawnOps.every((g) => opsIds.includes(g.dataset.op)) && drawnOps.every((g) => { const t = rec0.phrases.flatMap((p) => p.terms).find((x) => x.id === g.dataset.op); return Object.keys(t.parameters).every((k) => document.querySelector(`#board [data-place="${t.id}.${k}"]`)); }), "A3 each drawn function span is an operation of the record, with every declared place");
        // A4/A5 by pointer
        const typed = await openLink(() => /: \*/.test(all("#board [id^=page-] text").map((t) => t.textContent).join("\n")));
        if (ok(typed, "A4 click opens a link and its type page from the world")) {
          const pageT = all("#board [id^=page-] text").map((t) => t.textContent).join("\n");
          ok(pageT.includes(typed.dataset.kind + " : *"), "A4 the page is of the link's target");
          await shot(`${pre}-a-open-link`);
          ok(/d1 · kind/.test(pageT) && all("#board [id^=pg-o-]").length >= 2, "A5 d1's options and probabilities for its words");
          // B7: revisit d1: click an option that is not the chosen one
          const optEl = all("#board [id^=pg-o-]").find((g) => !/^●/.test(g.querySelector("text").textContent.trim()) && !/\(none\)/.test(g.dataset.label));
          if (ok(optEl, "B7 an option d1 did not choose")) {
            const kind = optEl.dataset.label.split(" ")[0];
            await click(optEl); await until(() => staged(), 15000); await syncNet();
            ok(staged() && staged().path === "kind" && staged().value === kind && staged().at[0] === +typed.dataset.start && sent(staged()), `B7 clicking d1's option ${kind} stages that retag (/edit kind)`);
            await key("Escape"); await pause();
          }
        }
        await reset();
        await key("ArrowRight"); await key("ArrowRight");
        const fid = S.focus; await key("Enter"); await pause();
        ok(fid && S.open && S.open.t === "piece", "A4k arrows + Enter open a link");
        // ---- B1: widen by the end handle (pointer); the draft is drawn in place before release
        const hd = el("#hd-e");
        if (ok(hd, "B1 the open link has handles")) {
          const p = S.open.p, next = L.words.find((w) => w.s > p.end && document.querySelector(`#board text.w[data-s="${w.s}"]`) && w.s - p.end < 40);
          const tgt = next && document.querySelector(`#board text.w[data-s="${next.s}"]`);
          if (ok(tgt, "B1 a word after the link")) {
            const q = tgt.getBoundingClientRect();
            const res = await drag(hd, [q.right - 1, q.top + q.height / 2], { shot: `${pre}-b-widen` });
            const b = staged();
            ok(b && sent(b) && b.path === "kind" && b.at[0] === p.start && b.at[1] > p.end && b.value === p.kind, "B1 widen = /edit kind over the wider words, same kind");
            ok(b && res.mid.links.some((l) => l.start === b.at[0] && l.end === b.at[1] && l.kind === b.value), "B5 the engine's draft is drawn in place before release (the wider link)");
            ok(/→/.test(res.mid.dock) && b && res.mid.dock.includes(b.value + "|"), "B5 before → after in the dock before release");
            ok(b && /✓ a/.test(dock()), "B5 release stages it with Accept / Cancel");
            if (opts.accept && b && pre === prefixes[0]) {
              await until(() => el("#accept") && !el("#accept").disabled);
              const before = S.base.snapshot;
              await key("a");
              await until(() => S.base.snapshot !== before, 20000); await sleep(200);
              const latest = (await fetch("/readings").then((x) => x.json())).filter((l) => l.id === id).at(-1);
              ok(latest.snapshot !== before && latest.corrections.some((c) => c.path === "kind" && c.kind === b.value && same(c.at, b.at)) && latest.pieces.some((x) => x.by === "user" && x.start === b.at[0] && x.end === b.at[1]), "B6 after Accept (a) and reload the store has the correction");
              await pause(); ok(linksMatch(latest), "B6 the page draws the saved snapshot");
              await key("z");
              await until(() => S.base.snapshot !== latest.snapshot, 20000); await sleep(200);
              const l2 = (await fetch("/readings").then((x) => x.json())).filter((l) => l.id === id).at(-1);
              ok(same(l2.pieces, rec0.pieces) && l2.corrections.length === rec0.corrections.length, "E undo (z) restores the snapshot before the accept, in the store");
              await pause(); ok(linksMatch(l2), "E the page draws it");
            } else if (b) {
              await click(el("#cancel")); await pause();
              ok(!S.staged && linksMatch(rec0) && !/→/.test(dock()), "B5 Cancel: the drawn links are the server's record again");
            }
          }
        }
        // ---- keyboard widen/narrow on a link of two words or more: ] [ { }
        const multiOf = () => { const L2 = window.board.layout(S.base); return all("#board [id^=pc-]").find((g) => g.dataset.kind !== "(none)" && L2.words.filter((w) => w.s >= +g.dataset.start && w.e <= +g.dataset.end).length >= 2 && L2.words.some((w) => w.e <= +g.dataset.start && document.querySelector(`#board text.w[data-s="${w.s}"]`))); }; // two words or more, with a word before it in view
        for (const [k, check, label] of [["]", (b, p) => b.at[0] === p.start && b.at[1] > p.end && b.value === p.kind, "B1k ] widens the end"], ["[", (b, p) => b.at[1] === p.end && b.at[0] > p.start && b.value === "(none)", "B2k [ narrows the end (the last word unlinked)"], ["{", (b, p) => b.at[0] < p.start && b.at[1] === p.end && b.value === p.kind, "B1k { widens the start"], ["}", (b, p) => b.at[0] === p.start && b.at[1] < p.end && b.value === "(none)", "B2k } narrows the start (the first word unlinked)"]]) {
          await reset(); const m = multiOf(); if (!ok(m, label + ": a link of two words")) continue;
          await click(m); await pause();
          const p = S.open && S.open.p;
          await key(k); await until(() => !/…/.test(dock()) && /→/.test(dock()), 20000);
          await key("Enter"); await sleep(200); await syncNet();
          const b = staged() || refusedBody();
          ok(p && b && sent(b) && check(b, p), label + " (/edit kind), then Enter stages it");
          await key("Escape");
        }
        // ---- B2: narrow by the end handle (pointer): drag it back over the last word
        await reset();
        { const m = multiOf(); if (ok(m, "B2 a link of two words")) {
          await click(m); await pause();
          const p = S.open.p, L2 = window.board.layout(S.base), inside = L2.words.filter((w) => w.s >= p.start && w.e <= p.end);
          const prev = document.querySelector(`#board text.w[data-s="${inside[inside.length - 2].s}"]`), h2 = el("#hd-e");
          if (ok(prev && h2, "B2 the handle and the word before the last")) {
            const q = prev.getBoundingClientRect();
            await drag(h2, [q.right, q.top + q.height / 2], { shot: `${pre}-b-narrow` });
            const b = staged();
            ok(b && sent(b) && b.value === "(none)" && b.at[1] === p.end && b.at[0] > p.start, "B2 narrow = the last word unlinked (/edit kind (none))");
            await key("Escape");
          }
        } }
        // ---- B3: a type picked up from a link's page, onto words (pointer)
        await reset();
        const typedLink = await openLink(() => typeChips().length > 0);
        if (ok(typedLink, "B3 a link whose page offers types")) {
          const chip = typeChips()[0], tname = chip.dataset.label;
          const w2 = all("#board [id^=pc-]").filter((g) => g.dataset.kind !== tname && g.id !== typedLink.id)[3];
          const res = await drag(chip, w2, { shot: `${pre}-b-type` });
          const b = staged();
          ok(b && sent(b) && b.path === "kind" && b.value === tname && b.at[0] === +w2.dataset.start, `B3 type drop = /edit kind ${tname} on those words`);
          ok(b && res.mid.links.some((l) => l.start === b.at[0] && l.end === b.at[1] && l.kind === tname), "B5 the new link is drawn in place before release");
          await key("Escape");
        }
        // ---- B4: Later[K] from a link's page, onto words (pointer), then by keyboard
        await reset();
        const tl2 = await openLink(() => el("#board [id^=pg-c-Later_]"));
        if (ok(tl2, "B4 a link whose page offers Later[K]")) {
          const later = el("#board [id^=pg-c-Later_]"), lname = later.dataset.label;
          const w3 = all("#board [id^=pc-]").filter((g) => g.dataset.kind !== lname && g.id !== tl2.id)[2];
          const res = await drag(later, w3, { shot: `${pre}-b-later` });
          const b = staged();
          ok(b && sent(b) && b.value === lname && /^Later\[/.test(lname) && b.at[0] === +w3.dataset.start, `B4 constructed type drop = /edit kind ${lname}`);
          ok(b && res.mid.links.some((l) => l.start === b.at[0] && l.kind === lname), "B4 drawn in place before release");
          await key("Escape");
          // B4k: Tab to the page, arrows to Later[K], Space, an arrow to words, Enter
          await key("Tab"); { let g = 0; while (!(S.focus || "").startsWith("pg-c-Later_") && g++ < 80) await key("ArrowRight"); }
          await key(" ");
          if (ok(S.hold && S.hold.th.t === "type" && /^Later\[/.test(S.hold.th.name), "B4k Space picks Later[K] up from the page")) {
            await key("ArrowRight"); await until(() => !/…/.test(dock()) && /→/.test(dock()), 20000);
            await key("Enter"); await sleep(150); await syncNet();
            const bk = staged(); ok(bk && sent(bk) && /^Later\[/.test(bk.value), "B4k Enter drops it on words");
            await key("Escape");
          }
          await key("Tab");
        }
        // ---- B3k: a type by keyboard from a link's page
        await reset();
        { let g = 0; await key("ArrowRight"); while (g++ < 30) { await key("Enter"); await pause(); if (typeChips().length) break; await key("Escape"); await pause(); await key("ArrowRight"); } }
        await key("Tab");
        { let g = 0; while (!typeChips().some((c) => c.id === S.focus) && g++ < 60) await key("ArrowRight"); }
        const kchip = typeChips().find((c) => c.id === S.focus);
        await key(" ");
        if (ok(kchip && S.hold && S.hold.th.t === "type", "B3k Space picks a type up from the page")) {
          await key("ArrowRight"); await until(() => !/…/.test(dock()) && /→/.test(dock()), 20000);
          await key("Enter"); await sleep(150); await syncNet();
          const b = staged(); ok(b && sent(b) && b.path === "kind" && b.value === kchip.dataset.label, "B3k Enter drops it on words (/edit kind)");
          await key("Escape");
        }
        await key("Tab"); await reset();
        // ---- C: places take words, a world member, a result; they stage where the engine accepts
        row.holes = all("#board [id^=pl-]").filter((g) => g.dataset.hole === "1").length; row.unresolved = all("#board [id^=un-]").length;
        { let res = null, n = 0; // C1 words: links in turn until the engine accepts them somewhere
          for (const g of all("#board [id^=pc-]").slice(4, 12)) { n++; res = await dragToAccepted(g, `${pre}-c-words`); if (!res.none) break; await reset(); }
          if (ok(res && !res.none, `C1 the engine accepts some held words somewhere (tried ${n} links)`)) {
            const b = staged(); ok(b && sent(b) && b.number != null && b.value.constant !== undefined && b.value.at[0] >= 0, "C1 words into an accepting place stage (/edit {constant, type, at})");
            ok(b && res.mid.places.some(([pid, txt]) => pid === "pl-" + b.number + "-" + b.path.replace(/\./g, "_") && txt === "⇠"), "C1 the draft shows the place filled before release");
            row.did.push("C1 → " + res.tid); await key("Escape");
          }
        }
        await reset();
        { // C2 a member: open a rejected or open place, its type's page offers members; hold one, drop where the engine accepts
          let res = null; const tried = [];
          for (const h of all("#board [id^=pl-]").filter((g) => g.dataset.hole === "1").concat(all("#board [id^=pl-]"))) {
            await reset(); await click(h); await pause();
            const mem = el("#board [id^=pg-m-]"); if (!mem) continue;
            tried.push(mem.dataset.label); res = await dragToAccepted(mem, `${pre}-c-member`); if (!res.none) break; await reset();
            if (tried.length >= 3) break;
          }
          if (ok(res && !res.none, `C2 the engine accepts a member somewhere (members tried: ${tried.join(", ") || "none on any place's page"})`)) {
            const b = staged(); ok(b && sent(b) && b.value.at[0] === -1 && tried.includes(b.value.constant), "C2 member into an accepting place stages (/edit {constant: member words, at: [-1,-1]})");
            row.did.push("C2 → " + res.tid); await key("Escape");
          }
        }
        await reset();
        { // C3 a result: operations in turn until the engine accepts one's result somewhere
          let res = null, n = 0;
          for (const op of all("#board [id^=op-]")) { n++; res = await dragToAccepted(op.querySelector("text"), `${pre}-c-result`); if (!res.none) break; await reset(); if (n >= 6) break; }
          if (ok(res && !res.none, `C3 the engine accepts a result somewhere (tried ${n} operations)`)) {
            const b = staged(); ok(b && sent(b) && b.value.ref != null, "C3 result into an accepting place stages (/edit {ref})");
            row.did.push("C3 → " + res.tid); await key("Escape");
          }
        }
        await reset();
        { // C4 a function onto an unresolved request (ƒ ▢), from that request's own page
          const un = el("#board [id^=un-]");
          if (un) {
            await click(un); await pause();
            const fnChip = el("#board [id^=pg-f-]");
            if (ok(fnChip, "C4 the page of ƒ ▢ offers the world's functions")) {
              await drag(fnChip, document.getElementById(un.id), { shot: `${pre}-c-function` });
              const b = staged() || refusedBody();
              ok(b && sent(b) && b.number === null && b.path.startsWith(fnChip.dataset.label + "."), "C4 function onto ƒ ▢ = /edit {number: null, path: function.parameter}, answered");
              row.did.push("C4 " + (staged() ? "staged" : "refused " + JSON.stringify(S.note && S.note.refused && S.note.refused.codes)));
              await key("Escape");
            }
          } else row.did.push("C4 no ƒ ▢ in view");
        }
        await reset();
        { // C1k: words into a place by keyboard: Space, arrows (refused places are skipped), Enter
          await key("ArrowRight"); await key(" ");
          if (ok(S.hold, "C1k Space picks the link up")) {
            await until(() => S.hold && window.board.idleQ(), 20000);
            let g = 0; while (S.hold && !(S.hold.opts[S.hold.i].body && S.hold.opts[S.hold.i].body.number != null) && g++ < 400) await key("ArrowRight");
            const o = S.hold && S.hold.opts[S.hold.i];
            if (ok(o && o.body && o.body.number != null, "C1k arrows reach a place")) {
              await until(() => !/…/.test(dock()) && dock().trim(), 15000);
              await key("Enter"); await sleep(200); await syncNet();
              const b = staged() || refusedBody();
              ok(b && same(b, o.body) && sent(b), "C1k Enter drops the words (the same request as the pointer)");
              row.did.push("C1k " + (staged() ? "staged" : "refused"));
              await key("Escape");
            }
          }
        }
        await reset();
        { // D: while words are held, the rail equals the engine's answer, asked again here in one /edits request by the audit
          const pcsD = all("#board [id^=pc-]"), srcD = pcsD[Math.max(0, pcsD.length - 3)];
          const [sx, sy] = center(rectOf(srcD));
          await pe("pointermove", sx, sy); await pe("pointerdown", sx, sy); await pe("pointermove", sx + 7, sy + 7);
          await until(railReady, 30000); await pe("pointermove", sx + 9, sy + 9); await sleep(300);
          await syncNet();
          const drawnOk = railOk().map((g) => g.id.slice(3)), info = (el("#rl-info") && el("#rl-info").querySelector("text").textContent) || "";
          const marks = all("#board [id^=pl-]").map((g) => [g.id.slice(3), [...g.querySelectorAll("text")].map((t) => t.textContent).find((t) => t === "✓" || t === "✕") || null]);
          await shot(`${pre}-d-held`);
          await key("Escape"); await pe("pointerup", sx, sy); await sleep(200); if (S.staged) await key("Escape");
          const mineOf = (x) => x.value && x.value.at && x.value.at[0] === +srcD.dataset.start && x.value.at[1] === +srcD.dataset.end;
          const batch = net().filter((n) => n.path === "/edits" && n.body.edits.some(mineOf)).at(-1);
          if (ok(batch, "D1 holding words sent their places to the engine in one /edits request (seen by Chrome)")) {
            const mine = batch.body.edits.filter(mineOf);
            const ans = await fetch("/edits", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reading: S.id, edits: mine, drafts: false }) }).then((x) => x.json());
            const okKeys = mine.filter((x, i) => !(ans.results[i].diagnostics || []).length).map((x) => `${x.number}-${x.path.replace(/\./g, "_")}`);
            const noN = mine.length - okKeys.length, more = +((/\+(\d+)/.exec(info) || [0, 0])[1]), shownNo = +((/✕ (\d+)/.exec(info) || [0, -1])[1]);
            ok(drawnOk.every((k) => okKeys.includes(k)), "D1 every place the rail offers (✓) is one the engine accepts");
            ok(drawnOk.length + more === okKeys.length, `D1 the rail offers all the engine accepts (${drawnOk.length} + ${more} = ${okKeys.length})`);
            ok(shownNo === noN, `D1 the rail counts the refused (${shownNo} = ${noN})`);
            ok(marks.every(([k, m]) => m === null || (m === "✓") === okKeys.includes(k)), "D1 each ✓/✕ on a place in the text equals the engine's answer");
            row.did.push(`D engine ok ${okKeys.length} / no ${noN}; rail ✓ ${drawnOk.length} +${more}`);
          }
        }
        await reset();
        const prose = proseCheck();
        ok(prose.length === 0, "F no sentence written by the page" + (prose.length ? ": " + prose.slice(0, 3).join(" / ") : ""));
      } catch (e) { row.bad.push("threw: " + e.message + " " + (e.stack || "").split("\n")[1]); }
      report.readings.push(row);
      if (row.bad.length) report.failures.push({ id: pre, bad: row.bad });
    }
    report.posts = net().reduce((m, n) => ((m[n.path] = (m[n.path] || 0) + 1), m), {});
    report.summary = { readings: prefixes.length, failing: report.failures.length, banned: report.dragology.banned.length };
    return report;
  };
  window.auditKit = { sleep, center, pe, click, key, until, drag, dock, shot, trusted, syncNet };
})();
