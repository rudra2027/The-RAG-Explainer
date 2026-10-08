// lens.js - the "search lens": chunks of the knowledge base as tiles.
//
// While a search runs, each tile fills in what happened to that chunk:
//   D  = dense (meaning) score + rank      - indigo bar
//   K  = BM25 (keyword) score + rank       - amber bar
//   F  = fused RRF score + rank            - violet bar
// Dropped chunks fade out; the final top chunks get a gold star with their rank.
//
// Small knowledge base: EVERY chunk gets a tile (seeing the losers makes strategies comparable).
// Big knowledge base (more than `limit` chunks, e.g. a 700-chunk article collection): tiles are
// created on demand, only for chunks a search actually touched - 700 tiles would be unreadable.

import { DEPT_COLOR } from "./explain.js";

let grid;
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function tileHtml(p) {
  return `<div class="tile fresh" id="tile-${p.id}" title="${esc(p.text)}">
    <div class="tile-head"><i style="background:${DEPT_COLOR[p.department] || "#64748b"}"></i>
      <span>${esc(p.source.replace(/\.(md|txt|pdf)$/, ""))}</span><b>#${p.chunk_index}</b></div>
    <div class="tile-bars">
      <div class="tb d"><span>D</span><em><s></s></em><small></small></div>
      <div class="tb k"><span>K</span><em><s></s></em><small></small></div>
      <div class="tb f"><span>F</span><em><s></s></em><small></small></div>
    </div>
    <div class="tile-terms"></div>
    <div class="star"></div>
  </div>`;
}

export function renderLens(el, points, total, limit, noteEl) {
  grid = el;
  const showAll = total > 0 && total <= limit && points.length === total;
  noteEl.textContent = total === 0 ? "" : showAll ? ""
    : `${total.toLocaleString()} chunks are too many to draw - the lens shows only the chunks this search touches.`;
  grid.innerHTML = showAll ? points.map(tileHtml).join("")
    : total === 0 ? '<div class="empty small">The knowledge base is empty. Ingest documents to fill the lens.</div>' : "";
}

// Get the tile of a chunk, creating it on demand (big knowledge bases).
function tile(r) {
  let t = document.getElementById(`tile-${r.id}`);
  if (!t) {
    grid.querySelector(".empty")?.remove();
    grid.insertAdjacentHTML("beforeend", tileHtml(r));
    t = document.getElementById(`tile-${r.id}`);
  }
  return t;
}

export function lensReset() {
  if (!grid) return;
  const onDemand = !!grid.dataset.onDemand;
  grid.querySelectorAll(".tile").forEach((t) => {
    t.className = "tile";
    t.querySelectorAll("s").forEach((s) => (s.style.width = "0"));
    t.querySelectorAll("small").forEach((s) => (s.textContent = ""));
    t.querySelector(".tile-terms").textContent = "";
    t.querySelector(".star").textContent = "";
  });
  if (onDemand) grid.innerHTML = "";
}

export function lensSetOnDemand(on) { if (grid) on ? (grid.dataset.onDemand = "1") : delete grid.dataset.onDemand; }

function setBar(r, kind, fraction, text) {
  const t = tile(r);
  t.querySelector(`.tb.${kind} s`).style.width = `${Math.max(4, Math.min(1, fraction) * 100)}%`;
  t.querySelector(`.tb.${kind} small`).textContent = text;
  t.classList.add(`hit-${kind}`);
}

// Best (lowest) rank of each chunk across several lists (MQE gives one list per query).
function bestPerChunk(lists, rankKey) {
  const best = new Map();
  Object.values(lists).forEach((list) => list.forEach((r) => {
    const prev = best.get(r.id);
    if (!prev || r[rankKey] < prev[rankKey]) best.set(r.id, r);
  }));
  return best;
}

export function lensDense(lists) {
  bestPerChunk(lists, "dense_rank").forEach((r) => setBar(r, "d", r.dense_score, `${r.dense_score.toFixed(2)} · #${r.dense_rank}`));
}

export function lensBm25(lists) {
  const best = bestPerChunk(lists, "bm25_rank");
  const max = Math.max(...[...best.values()].map((r) => r.bm25_score), 1);
  best.forEach((r) => {
    setBar(r, "k", r.bm25_score / max, `${r.bm25_score.toFixed(1)} · #${r.bm25_rank}`);
    tile(r).querySelector(".tile-terms").textContent = r.matched_terms.join(" · ");
  });
}

export function lensFuse(results) {
  const max = Math.max(...results.map((r) => r.fused_score || 0), 1e-9);
  results.forEach((r, i) => setBar(r, "f", (r.fused_score || 0) / max, `${(r.fused_score || 0).toFixed(4)} · #${i + 1}`));
}

export function lensPostfilter(kept) {
  const keep = new Set(kept.map((r) => r.id));
  grid?.querySelectorAll(".tile").forEach((t) => {
    const wasCandidate = t.classList.contains("hit-d") || t.classList.contains("hit-k");
    if (wasCandidate && !keep.has(t.id.slice(5))) t.classList.add("dropped");
    if (!wasCandidate) t.classList.add("ignored");
  });
}

export function lensRerank(top) {
  grid?.querySelectorAll(".tile").forEach((t) => t.classList.add("dropped"));
  top.forEach((r, i) => {
    const t = tile(r);
    t.classList.remove("dropped", "ignored");
    t.classList.add("top");
    t.querySelector(".star").textContent = `★ ${i + 1}`;
  });
}
