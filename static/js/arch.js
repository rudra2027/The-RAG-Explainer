// arch.js - the "RAG Architectures" pages (opened from the top navigation bar).
//
// One page per architecture:
//   * the flow diagram (built from the architecture's own list of stages)
//   * "Play animated explainer": a glowing dot travels node to node while a caption tells the
//     story, using the files the student uploaded on the Pipeline page
//   * "Run it": executes the REAL pipeline with this architecture's settings on the knowledge
//     base, lighting up the same nodes live

import { STAGE_ICON, STAGE_KID, STAGE_LABEL } from "./explain.js";

const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let archs = [];
let current = null;
let playing = 0;          // bumped to cancel a running explainer
let kb = { docs: [], points: [] };

// Small line under each node: what happens there, in 4-6 words.
const NODE_HINT = {
  query: "your question", tool_call: "AI plans the search", expand: "ask in more ways", prefilter: "close wrong shelves",
  dense: "search by meaning", bm25: "search by words", fuse: "merge the lists", postfilter: "drop weak cards",
  rerank: "judge re-orders", prompt: "pack the letter", answer: "AI writes", reflect: "check homework",
};

export async function loadArchitectures() {
  archs = (await (await fetch("/api/architectures")).json()).architectures;
  $("#arch-menu").innerHTML = archs.map((a) =>
    `<button data-id="${a.id}"><b>${esc(a.name)}</b><small>${esc(a.tagline)}</small></button>`).join("");
  return archs;
}

export const setKnowledge = (info) => { kb = { ...kb, ...info }; renderKbStrip(); };
export const currentArch = () => current;

function renderKbStrip() {
  const files = kb.docs.map((d) => d.source);
  $("#arch-kb").textContent = files.length
    ? `Using your files: ${files.slice(0, 3).join(", ")}${files.length > 3 ? ` +${files.length - 3} more` : ""}`
    : "No files yet - ingest some on the Pipeline page.";
}

// Parallel stages (dense + BM25 search at the same time) share one column.
function columns(stages) {
  const cols = [];
  for (const s of stages) {
    const prev = cols[cols.length - 1];
    if (s === "bm25" && prev && prev.includes("dense")) prev.push(s);
    else cols.push([s]);
  }
  return cols;
}

export function showArchitecture(id) {
  current = archs.find((a) => a.id === id);
  if (!current) return;
  stopExplainer();
  $("#arch-name").textContent = current.name;
  $("#arch-tag").textContent = current.tagline;
  $("#arch-kid").innerHTML = `🧒 <b>In kid words:</b> ${esc(current.kid)}`;
  $("#arch-good").innerHTML = `<b>👍 Good for</b><br>${esc(current.good_for)}`;
  $("#arch-weak").innerHTML = `<b>⚠️ Weak at</b><br>${esc(current.weak_at)}`;
  $("#arch-question").placeholder = current.example;
  $("#arch-question").value = "";
  $("#arch-feed").innerHTML = "";
  $("#arch-flow").innerHTML = columns(current.stages).map((col, i) => `
    ${i ? '<span class="farrow">➜</span>' : ""}
    <div class="fcol">${col.map((s) => `<div class="fnode" id="fn-${s}"><span class="ic">${STAGE_ICON[s]}</span><b>${esc(STAGE_LABEL[s])}</b><small>${esc(NODE_HINT[s] || "")}</small></div>`).join("")}</div>`).join("");
  $("#arch-cap").innerHTML = `<span class="ic">👆</span><div><b>Press play</b><p>A glowing dot will travel through every step, using the files you uploaded on the Pipeline page.</p></div>`;
  document.querySelectorAll("#arch-menu button").forEach((b) => b.classList.toggle("cur", b.dataset.id === id));
  renderKbStrip();
}

// ---- live state while a REAL run happens (called by main.js for every event) -----------------------
export function markNode(stage, status) {
  const n = $(`#fn-${stage}`);
  if (!n) return;
  n.classList.remove("live", "done", "skipped");
  n.classList.add(status === "running" ? "live" : status === "skipped" ? "skipped" : "done");
}
export function resetNodes() { document.querySelectorAll(".fnode").forEach((n) => n.classList.remove("live", "done", "skipped")); }

// ---- the animated explainer ("video") -----------------------------------------------------------------
function captionFor(stage) {
  const info = STAGE_KID[stage] || {};
  const files = kb.docs.map((d) => d.source);
  const sample = kb.points[0];
  const extra = {
    query: current ? `Example: "${current.example}"` : "",
    dense: sample ? `It compares the question with cards from your files, like "${sample.text.slice(0, 70)}…"` : "",
    bm25: files.length ? `It counts matching words inside ${files[0]}${files.length > 1 ? " and the other files" : ""}.` : "",
    rerank: "The judge's marks decide the final order - not the earlier search scores.",
    prefilter: kb.docs.length ? `Shelves in your knowledge base: ${[...new Set(kb.docs.map((d) => d.department))].join(", ")}.` : "",
  }[stage] || "";
  return `<span class="ic">${STAGE_ICON[stage]}</span><div><b>${esc(info.title || STAGE_LABEL[stage])}</b><p>${esc(info.kid || "")}</p>${extra ? `<p class="muted small">${esc(extra)}</p>` : ""}</div>`;
}

function moveToken(node) {
  const token = $("#arch-token"), wrap = $("#arch-flow-wrap").getBoundingClientRect(), r = node.getBoundingClientRect();
  token.hidden = false;
  return token.animate([{ transform: token.style.transform || "translate(0,0)" },
    { transform: `translate(${r.left - wrap.left + r.width / 2 - 9}px, ${r.top - wrap.top + 6}px)` }],
    { duration: 700, easing: "cubic-bezier(.4,0,.2,1)", fill: "forwards" }).finished.then(() => {
      token.style.transform = `translate(${r.left - wrap.left + r.width / 2 - 9}px, ${r.top - wrap.top + 6}px)`;
    }).catch(() => {});
}

export async function playExplainer() {
  if (!current) return;
  const me = ++playing;
  resetNodes();
  $("#arch-play").hidden = true; $("#arch-stop").hidden = false;
  $("#arch-token").style.transform = "translate(-30px, 10px)";
  for (const stage of current.stages) {
    if (me !== playing) return;
    const node = $(`#fn-${stage}`);
    document.querySelectorAll(".fnode.live").forEach((n) => n.classList.replace("live", "done"));
    node.classList.add("live");
    $("#arch-cap").innerHTML = captionFor(stage);
    await moveToken(node);
    await sleep(2600);              // time to read the caption
  }
  if (me !== playing) return;
  document.querySelectorAll(".fnode.live").forEach((n) => n.classList.replace("live", "done"));
  $("#arch-cap").innerHTML = `<span class="ic">🎉</span><div><b>That's the whole trip!</b><p>Now press <b>Run this architecture</b> to watch it happen for real on your files.</p></div>`;
  stopExplainer(false);
}

export function stopExplainer(reset = true) {
  playing++;
  $("#arch-play").hidden = false; $("#arch-stop").hidden = true;
  $("#arch-token").hidden = true;
  if (reset) resetNodes();
}
