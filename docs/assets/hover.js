// Hover text on the names in each Python code block, as an IDE shows it: the signature or the
// type, the first sentence of the docstring, and where the name is defined. The build writes the
// text into hover.json (docs/hover.py) and names each block by a hash of its code.
let hoverData = null;

async function hoverTips() {
  if (!hoverData) {
    const script = document.querySelector('script[src*="assets/hover.js"]');
    const response = await fetch(new URL("hover.json", script.src));
    hoverData = await response.json();
  }
  return hoverData;
}

// FNV-1a (32 bit) over the UTF-16 code units: the same key as docs/hover.py.
function blockKey(text) {
  let value = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) {
    value = Math.imul(value ^ text.charCodeAt(i), 0x01000193) >>> 0;
  }
  return value.toString(16).padStart(8, "0");
}

function markNames(code, rows) {
  const text = code.textContent;
  const lineStarts = [0];
  for (let i = 0; i < text.length; i++) if (text[i] === "\n") lineStarts.push(i + 1);
  const wanted = rows
    .map(([line, column, length, tip]) => ({ start: lineStarts[line] + column, length, tip }))
    .sort((a, b) => a.start - b.start);
  const walker = document.createTreeWalker(code, NodeFilter.SHOW_TEXT);
  const nodes = [];
  for (let node = walker.nextNode(), at = 0; node; node = walker.nextNode()) {
    nodes.push({ node, at });
    at += node.nodeValue.length;
  }
  for (const { node, at } of nodes) {
    const end = at + node.nodeValue.length;
    const inside = wanted.filter((w) => w.start >= at && w.start + w.length <= end);
    for (const w of inside.reverse()) {  // from the right, so the offsets to the left stay true
      const range = document.createRange();
      range.setStart(node, w.start - at);
      range.setEnd(node, w.start - at + w.length);
      const name = document.createElement("span");
      name.className = "hover-name";
      name.dataset.tip = w.tip;
      range.surroundContents(name);
    }
  }
}

function showTip(event) {
  const name = event.target.closest(".hover-name");
  const box = document.getElementById("hover-tip");
  if (!name) { box.hidden = true; return; }
  const [head, ...rest] = hoverData.tips[Number(name.dataset.tip)].split("\n");
  box.replaceChildren();
  const signature = document.createElement("code");
  signature.textContent = head;
  box.append(signature);
  for (const line of rest) {
    const part = document.createElement("div");
    part.textContent = line;
    if (line.startsWith("defined in ")) part.className = "hover-where";
    box.append(part);
  }
  const place = name.getBoundingClientRect();
  box.hidden = false;
  box.style.left = Math.min(place.left, window.innerWidth - box.offsetWidth - 8) + "px";
  box.style.top = (place.bottom + 6 + box.offsetHeight > window.innerHeight
    ? place.top - box.offsetHeight - 6 : place.bottom + 6) + "px";
}

async function addHover() {
  const data = await hoverTips();
  if (!document.getElementById("hover-tip")) {
    const box = document.createElement("div");
    box.id = "hover-tip";
    box.hidden = true;
    document.body.append(box);
    document.addEventListener("mouseover", showTip);
  }
  document.querySelectorAll("div.highlight > pre > code:not([data-hover])").forEach((code) => {
    code.setAttribute("data-hover", "1");
    const rows = data.blocks[blockKey(code.textContent.trimEnd())];
    if (rows) markNames(code, rows);
  });
}

if (typeof document$ !== "undefined") { document$.subscribe(addHover); } else { document.addEventListener("DOMContentLoaded", addHover); }
