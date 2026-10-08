// cards.js - turns each finished StageEvent into a card in the feed.
// One renderer per stage, so it's easy to find "how is the BM25 step drawn?".

import { STAGE_BOX } from "./explain.js";

export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function card(kind, title, ms, body, extraClass = "") {
  const el = document.createElement("article");
  el.className = `card ${kind} ${extraClass}`;
  el.innerHTML = `<header><b>${title}</b>${ms != null ? `<span class="ms">${ms} ms</span>` : ""}</header>${body}`;
  return el;
}

// Wrap BM25-matched words in <mark> so students see WHY a chunk scored.
function highlightTerms(text, terms = []) {
  let html = esc(text);
  terms.forEach((t) => {
    const re = new RegExp(`\\b(${t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})\\b`, "gi");
    html = html.replace(re, "<mark>$1</mark>");
  });
  return html;
}

export function chunkCard(c, i) {
  const ov = c.overlap || 0;
  const text = ov ? `<mark>${esc(c.text.slice(0, ov))}</mark>${esc(c.text.slice(ov))}` : esc(c.text);
  return `<div class="chunk" style="animation-delay:${i * 50}ms">
    <div class="meta"><span class="badge">#${c.index}</span><span class="badge">${c.size} chars</span>
      <span class="badge">overlap ${ov}</span>${c.department ? `<span class="badge dept-${c.department}">${esc(c.department)}</span>` : ""}
      ${c.doc_type ? `<span class="badge">${esc(c.doc_type)}</span>` : ""}</div>
    <div class="txt">${text}</div></div>`;
}

export function resultCard(r, i) {
  const badges = [
    r.dense_score != null ? `<span class="badge s-d">dense ${r.dense_score.toFixed(3)} · #${r.dense_rank}</span>` : "",
    r.bm25_score != null ? `<span class="badge s-k">bm25 ${r.bm25_score.toFixed(2)} · #${r.bm25_rank}</span>` : "",
    r.fused_score != null ? `<span class="badge s-f">rrf ${r.fused_score.toFixed(4)}</span>` : "",
    r.rerank_score != null ? `<span class="badge s-r">re-rank ${r.rerank_score}</span>` : "",
  ].join("");
  return `<div class="chunk" style="animation-delay:${i * 40}ms">
    <div class="meta">${badges}<span class="badge dept-${r.department}">${esc(r.department)}</span>
      <span class="badge">${esc(r.source)} #${r.chunk_index}</span></div>
    <div class="txt">${highlightTerms(r.text, r.matched_terms)}</div></div>`;
}

function list(results, limit = 6) {
  return `<div class="chunk-grid">${results.slice(0, limit).map(resultCard).join("")}</div>
    ${results.length > limit ? `<details><summary>show all ${results.length}</summary>
    <div class="chunk-grid">${results.slice(limit).map((r, i) => resultCard(r, i)).join("")}</div></details>` : ""}`;
}

// RRF explained row by row: 1/(60+rank) for every list the chunk appeared in.
function rrfTable(results) {
  const rows = results.slice(0, 10).map((r, i) => {
    const parts = r.found_by.map((f) => {
      const rank = +f.split("#").pop();
      return `<span title="${esc(f)}">1/(60+${rank})</span>`;
    }).join(" + ");
    return `<tr><td>#${i + 1}</td><td>${esc(r.source)} #${r.chunk_index}</td>
      <td class="formula">${parts}</td><td><b>${r.fused_score.toFixed(4)}</b></td>
      <td class="muted small">${r.found_by.map(esc).join("<br>")}</td></tr>`;
  }).join("");
  return `<table class="rrf"><tr><th>Rank</th><th>Chunk</th><th>RRF = Σ 1/(60 + rank)</th><th>Score</th><th>Found by</th></tr>${rows}</table>`;
}

function vectorPreview(rows) {
  return rows.map((row) => `<div class="vec">${row.map((v) => {
    const a = Math.min(1, Math.abs(v) * 6);
    const col = v < 0 ? `rgba(8,145,178,${a})` : `rgba(124,58,237,${a})`;
    return `<span style="background:${col};color:${a > 0.5 ? "#fff" : "#0f172a"}">${v}</span>`;
  }).join("")}<span class="muted">… 376 more</span></div>`).join("");
}

export function renderCard(e) {
  const kind = STAGE_BOX[e.stage] || "warn";
  const d = e.data || {};
  const retry = d.attempt === 2 ? " · retry" : "";

  switch (e.stage) {
    case "load":
      return card(kind, `Load · ${esc(d.source)}`, e.ms, `<p>${esc(e.message)} · type <b>${esc(d.doc_type)}</b></p>
        ${d.truncated ? `<p class="upload-note">Big file (${d.size_mb} MB): you chose the fast option, so only ${(d.used_chars / d.file_chars * 100).toFixed(1)}% was ingested.
        Choose <b>The whole file</b> under <i>Big files</i> and upload again to read everything.</p>` : ""}`);
    case "chunk":
      return card(kind, `Chunk · ${esc(d.strategy)} · ${esc(d.source)}`, e.ms,
        `<p>${esc(e.message)}</p><div class="chunk-grid">${d.chunks.map(chunkCard).join("")}</div>`);
    case "embed":
      return card(kind, "Embed (local MiniLM)", e.ms, `<p>${esc(e.message)} - first 8 numbers of the first vectors:</p>${vectorPreview(d.preview)}`);
    case "store":
      return card(kind, "Store · Pinecone", e.ms, `<p>${esc(e.message)}</p>`);
    case "query":
      return card(kind, "Query", null, `<p class="answer">${esc(d.question)}</p>
        <p class="muted small">strategy <b>${esc(d.strategy)}</b>${d.strategy === "hybrid_expansion" ? ` · expansion <b>${esc(d.expansion)}</b>` : ""}
        ${d.llm_enabled ? "" : " · offline mode: LLM steps are skipped"}</p>`);
    case "tool_call":
      if (d.info?.mode === "off") return card("warn", "Tool call · skipped", null, `<p class="muted small">${esc(e.message)}</p>`);
      return card(kind, "Tool call · LLM plans the search", e.ms,
        `<pre>${esc(e.message)}</pre>${d.info?.note ? `<p class="muted small">${esc(d.info.note)}</p>` : ""}`);
    case "expand":
      if (e.status === "skipped") return null;
      return card(kind, `Expand · ${d.method === "mqe" ? "MQE (multi-query)" : "HyDE (hypothetical document)"}${retry}`, e.ms,
        d.method === "mqe"
          ? `<ol class="queries">${Object.entries(d.queries).map(([k, q]) => `<li><span class="badge">${esc(k)}</span> ${esc(q)}</li>`).join("")}</ol>`
          : `<p class="muted small">Hypothetical passage written by the LLM (used ONLY for dense search):</p>
             <blockquote>${esc(d.hyde_passage)}</blockquote>
             <p class="muted small">BM25 still uses your query: <b>${esc(d.queries.original)}</b></p>`);
    case "prefilter":
      return card(kind, `Pre-filter · metadata first${retry}`, null, `<pre>${esc(JSON.stringify(d.filter ?? "no filter: search everything"))}</pre>`);
    case "dense":
      if (e.status === "skipped") return null;
      return card(kind, `Dense search · Pinecone${retry}`, e.ms,
        Object.entries(d.lists).map(([label, res]) => `<h4>${esc(label)} <span class="muted">· ${res.length} hits</span></h4>${list(res, 3)}`).join(""));
    case "bm25":
      if (e.status === "skipped") return null;
      return card(kind, `BM25 keyword search${retry}`, e.ms,
        Object.entries(d.lists).map(([label, res]) => {
          const terms = d.query_terms[label.replace("bm25: ", "")] || [];
          return `<h4>${esc(label)} <span class="muted">· terms: ${terms.map((t) => `<code>${esc(t)}</code>`).join(" ")}</span></h4>${list(res, 3)}`;
        }).join(""));
    case "fuse":
      if (e.status === "skipped") return null;
      return card(kind, `Fuse · Reciprocal Rank Fusion${retry}`, e.ms, `<p>${esc(e.message)}</p>${rrfTable(d.results)}`);
    case "postfilter":
      return card(kind, `Post-filter · ${esc(e.message)}${retry}`, e.ms,
        `<p class="muted small">dropped ${d.report.dropped_low_score} weak (cosine &lt; ${d.report.min_score} and no keyword match),
         ${d.report.dropped_duplicate} duplicates, ${d.report.dropped_over_limit} over the limit</p>${list(d.results, 4)}`);
    case "rerank":
      return card(kind, `Re-rank · ${esc(e.message)}${retry}`, e.ms, `<div class="chunk-grid">${d.results.map(resultCard).join("")}</div>`);
    case "prompt":
      return card(kind, `Rendered prompt${retry}`, null, `<p class="muted small">System: ${esc(d.system)}</p><pre>${esc(d.prompt)}</pre>`);
    case "answer":
      return card(kind, `Answer${retry}`, e.ms, `<p class="answer">${esc(d.answer)}</p>`);
    case "reflect": {
      const c = d.check;
      if (e.status === "skipped") return card("warn", "Reflection · skipped", null, `<p class="small">${esc(c.reason)}</p>`);
      const claims = c.unsupported_claims.length ? `<ul>${c.unsupported_claims.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : "";
      return card(c.grounded ? kind : "warn", `Reflection${retry}`, e.ms,
        `<span class="verdict ${c.grounded ? "ok" : "bad"}">${c.grounded ? "Grounded" : "Not grounded"}</span>
         <p class="small">${esc(c.reason)}</p>${claims}`);
    }
    case "retry":
      return card("warn", "Retry", null, `<p>${esc(e.message)}</p>`);
    case "final": {
      const verdict = d.grounded == null ? "not checked" : d.grounded ? "grounded" : "not grounded";
      return card("final", `Final answer · ${verdict} · ${d.attempts} attempt(s)`, null, `<p class="answer">${esc(d.answer)}</p>`);
    }
    case "error":
      return card("warn", "Error", null, `<pre>${esc(e.message)}</pre>`);
  }
  return null;
}
