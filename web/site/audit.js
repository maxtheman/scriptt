// Corpus audit of the board (run in the page: `await (await fetch('/audit.js')).text()` then eval, or load via <script>). Returns a report object.
// It renders every reading of the store through the page's own render() and checks structural invariants; it never edits (no /accept).
(async () => {
  const report = { reading: [], failures: [] };
  const writes = []; const orig = Storage.prototype.setItem; Storage.prototype.setItem = function (...a) { writes.push(a[0]); return orig.apply(this, a); };
  const ids = [...new Set(S.lines.map(l => l.id))];
  const posts0 = window.__net.length;
  for (const id of ids) {
    S.id = id; S.sel = S.pending = S.carry = null; await load(); render();
    const r = S.base, t = $("#text"), row = { id: id.slice(0, 6), chars: r.text.length, phrases: r.phrases.length, ops: terms(r).length, unresolved: r.phrases.reduce((n, p) => n + p.unresolved.length, 0), bad: [] };
    const clone = t.cloneNode(true); clone.querySelectorAll(".pl,.op,.sock").forEach(e => e.remove());
    if (clone.textContent !== r.text) row.bad.push("R1 text differs from source (word duplicated, lost or reordered)");
    for (const op of terms(r)) { if (t.querySelectorAll(`.op[data-op="${op.id}"]`).length !== 1) row.bad.push(`R2 op ${op.id} tag count`); }
    if (t.querySelectorAll('.op[data-kind="unresolved"]').length !== row.unresolved) row.bad.push("R2 unresolved chips");
    for (const op of terms(r)) for (const p of places(op)) { if (p.value.several && p.value.several.length) continue; if (t.querySelectorAll(`[data-place="${CSS.escape(key.place(op.id, p.path))}"]`).length !== 1) row.bad.push(`R3 place ${op.id}.${p.path} objects`); }
    for (const e of t.querySelectorAll("[data-kind]:not(.w)")) if (e.tabIndex !== 0 || !(e.getAttribute("aria-label") || "").trim()) row.bad.push("R4 not focusable/named: " + e.dataset.key);
    // R6: open each object's card by a click; height and one-open rule
    let maxH = 0, maxOpen = 0, opened = 0;
    for (const k of [...t.querySelectorAll("[data-kind]")].map(x => x.dataset.key).slice(0, 40)) {
      const e = find(k); e.click(); await new Promise(r_ => setTimeout(r_, 0));
      const c = $("#card"); if (!c.hidden) { opened++; maxH = Math.max(maxH, c.getBoundingClientRect().height); maxOpen = Math.max(maxOpen, c.querySelectorAll('[aria-expanded="true"]').length); }
      else row.bad.push("R6 no card for " + e.dataset.key);
      closeCard();
    }
    row.cardMaxHeightPct = Math.round(100 * maxH / innerHeight); row.maxOpenRels = maxOpen; row.cards = opened;
    if (maxH > innerHeight * 0.4 + 1) row.bad.push("R6 card taller than 40% of viewport");
    if (maxOpen > 1) row.bad.push("R6 more than one relationship open");
    // L2/F4: engine verdicts for the first value (or op result): every answer is an engine answer
    const first = t.querySelector('.val,.op[data-op]');
    if (first) { const pv = previewAll(sourceOf(first)); await pv.job; const vs = [...pv.results.values()]; row.verdicts = vs.length; if (vs.some(x => !x.here && !x.draft && !x.diagnostics.length && !x.error)) row.bad.push("L2 verdict without a draft or diagnostics"); row.fit = vs.filter(x => !x.here && okay(x)).length; row.refused = vs.filter(x => !x.here && !okay(x)).length; }
    report.reading.push(row); if (row.bad.length) report.failures.push({ id: row.id, bad: row.bad });
  }
  report.posts = window.__net.slice(posts0).reduce((m, n) => (m[n.path] = (m[n.path] || 0) + 1, m), {});
  report.storageWrites = writes.length; Storage.prototype.setItem = orig;
  report.summary = { readings: ids.length, chars: report.reading.reduce((n, x) => n + x.chars, 0), ops: report.reading.reduce((n, x) => n + x.ops, 0), unresolved: report.reading.reduce((n, x) => n + x.unresolved, 0), failures: report.failures.length };
  return report;
})()
