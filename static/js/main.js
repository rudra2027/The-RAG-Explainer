// main.js - wires the page together. No framework: fetch(), EventSource and DOM updates.
//
// Flow of one run:
//   1. open an SSE stream (/api/ask or /api/ingest) with a random run id
//   2. every StageEvent -> light up the stage, draw a card, update lens / 3D map / funnel,
//      and (in step-by-step mode) play that step's animated scene in the middle of the page
//   3. in step-by-step mode the server sends a "pause" event after each finished stage;
//      the student reads the scene and clicks "Next step", which POSTs /api/continue.

import { activeQuerySteps, EXPANSION_INFO, INGEST_STEPS, NEXT_PREVIEW, QUERY_STEPS, STAGE_BOX, STAGE_LABEL,
         STRATEGY_INFO } from "./explain.js";
import { chunkCard, esc, renderCard } from "./cards.js";
import { lensBm25, lensDense, lensFuse, lensPostfilter, lensRerank, lensReset, lensSetOnDemand, renderLens } from "./lens.js";
import { clearSearch, init3D, setPoints, showBm25, showDense, showFinal } from "./space3d.js";
import { closeTheater, initTheater, noteEvent, resetRun, setContext, setReady, showScene, working, lockButtons } from "./theater.js";
import { currentArch, loadArchitectures, markNode, playExplainer, resetNodes, setKnowledge, showArchitecture, stopExplainer } from "./arch.js";

const $ = (sel) => document.querySelector(sel);
const STAGE_COLOR = { ingest: "var(--ingest)", retrieve: "var(--retrieve)", generate: "var(--generate)", evaluate: "var(--evaluate)" };

let currentRun = null;       // {id, steps, feed, step, arch} while a run is streaming
let status = { limits: {}, knowledge_base: { documents: [] } };
let llmEnabled = false;
let lastAdded = null;
let finalShown = false;

// ---- small UI helpers ---------------------------------------------------------------
function toast(message, ms = 3600) {
  const t = $("#toast");
  t.textContent = message;
  t.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => t.classList.remove("show"), ms);
}

// Disable everything that starts work while a run is going (the stage buttons and tabs stay usable).
function busy(on) {
  document.querySelectorAll("button:not(.tab):not(.th-card button):not(#arch-dd button):not(#arch-menu button):not(#arch-stop)")
    .forEach((b) => (b.disabled = on));
}

function addCard(el, feed) {
  if (!el) return;
  feed.querySelector(".empty")?.remove();
  feed.appendChild(el);
  if (!currentRun?.step) el.scrollIntoView({ behavior: "smooth", block: "nearest" });   // the stage is in front in step mode
}

// ---- tracker + the four stage cards -------------------------------------------------
function buildTracker(rowId, steps) {
  $(rowId).innerHTML = steps.map((s, i) =>
    `${i ? '<span class="sep">›</span>' : ""}<span class="step" id="step-${s}" style="--c:${STAGE_COLOR[STAGE_BOX[s]]}">${STAGE_LABEL[s]}</span>`
  ).join("");
}

function resetTracker(steps, active = steps) {
  steps.forEach((s) => ($(`#step-${s}`).className = active.includes(s) ? "step" : "step skipped"));
  document.querySelectorAll(".stage-card").forEach((b) => b.classList.remove("active", "done"));
}

function lightUp(e) {
  const box = STAGE_BOX[e.stage];
  if (!box) return;
  document.querySelectorAll(".stage-card").forEach((b) => b.classList.remove("active"));
  $(`#box-${box}`).classList.add(e.status === "running" ? "active" : "done");
  const pill = $(`#step-${e.stage}`);
  if (pill) pill.className = `step ${e.status === "info" ? "done" : e.status}`;
}

// ---- funnel: 20 candidates > 8 after filter > top 4 ------------------------------
const funnel = {};
function setFunnel(key, count, label) {
  funnel[key] = { count, label };
  $("#funnel").innerHTML = ["candidates", "filter", "rerank"].filter((k) => funnel[k])
    .map((k) => `<div class="f"><b>${funnel[k].count}</b><small>${funnel[k].label}</small></div>`).join('<span class="arrow">→</span>');
}
function resetFunnel() { Object.keys(funnel).forEach((k) => delete funnel[k]); $("#funnel").innerHTML = ""; }

function drawLatency(data) {
  const totals = data.totals, max = Math.max(...Object.values(totals), 1);
  $("#latency-bars").innerHTML = Object.entries(totals).map(([stage, ms]) => `
    <div class="bar-row"><div class="lbl"><span>${STAGE_LABEL[stage] || stage}</span><span>${ms >= 1000 ? (ms / 1000).toFixed(1) + " s" : ms + " ms"}</span></div>
    <div class="bar"><i style="width:${(ms / max) * 100}%"></i></div></div>`).join("");
  if (data.chunks) {
    const slowest = Object.entries(totals).sort((a, b) => b[1] - a[1])[0];
    $("#latency-note").innerHTML = `<b>${data.chunks.toLocaleString()} chunks</b> → ${data.ms_per_chunk} ms per chunk overall.
      Slowest step: <b>${STAGE_LABEL[slowest[0]] || slowest[0]}</b> (${(slowest[1] / 1000).toFixed(1)} s).
      Chunking itself takes ${totals.chunk} ms - the time goes to the network calls (embedding API + Pinecone).`;
  }
}

// ---- one handler for every event ----------------------------------------------------
function stepLabel(stage) {
  const i = currentRun.steps.indexOf(stage);
  return i < 0 ? "" : `Step ${i + 1} of ${currentRun.steps.length}`;
}

function handleEvent(e) {
  const run = currentRun, d = e.data || {};
  if (e.stage === "pause") return pauseReached(e.data.after);
  if (e.stage === "latency") return drawLatency(d);
  noteEvent(e);
  lightUp(e);
  if (run.arch) markNode(e.stage, e.status);

  if (e.status === "running") {                 // the computer is working: show the working scene
    if (run.step && STAGE_BOX[e.stage]) working(e.stage, e.message, d);
    return;
  }

  // Lens + 3D map + funnel react to the search stages.
  if (e.stage === "dense" && e.status === "done") { lensDense(d.lists); showDense(d.query_points, d.lists, d.hit_points); }
  if (e.stage === "bm25" && e.status === "done") {
    lensBm25(d.lists);
    showBm25([...new Set(Object.values(d.lists).flat().map((r) => r.id))]);
  }
  if (e.stage === "fuse") { if (e.status === "done") lensFuse(d.results); setFunnel("candidates", d.count, "candidates"); }
  if (e.stage === "postfilter") { lensPostfilter(d.results); setFunnel("filter", d.count, e.status === "done" ? "after post-filter" : "kept (no filter)"); }
  if (e.stage === "rerank") { lensRerank(d.results); showFinal(d.results.map((r) => r.id)); setFunnel("rerank", d.count, e.status === "done" ? "after re-rank" : "used (no re-rank)"); }
  if (e.stage === "retry") { lensReset(); clearSearch(); resetFunnel(); }
  if (e.stage === "store" && e.status === "done") { refreshStatus().then(refreshMap); }
  if (e.stage === "error") { closeTheater(); toast(e.message, 9000); }

  addCard(renderCard(e), run.feed);

  // The animated scene (only for steps that really ran, only in step-by-step mode).
  if (run.step && e.status === "done" && e.stage !== "error") {
    if (e.stage === "final") finalShown = true;
    showScene(e, { step: stepLabel(e.stage) });
  }
}

// The server finished a stage and is waiting: let the student continue when ready.
function pauseReached(stage) {
  const order = currentRun.steps, i = order.indexOf(stage);
  const next = order[i + 1];
  const text = i === -1 ? "" : next ? `${STAGE_LABEL[next]} - ${NEXT_PREVIEW[next]}`
    : currentRun.steps === INGEST_STEPS ? "finish (or load the next file)" : "see the final answer";
  $(`#step-${stage}`)?.classList.add("paused");
  setReady(text);
}

async function continueRun(mode) {
  if (!currentRun) return;
  document.querySelectorAll(".step.paused").forEach((s) => s.classList.remove("paused"));
  lockButtons(mode === "all" ? "Running to the end…" : "Working…");
  await fetch(`/api/continue?run=${currentRun.id}&mode=${mode}`, { method: "POST" });
}

// ---- streaming --------------------------------------------------------------------------
function stream(url, onEvent) {
  return new Promise((resolve) => {
    const source = new EventSource(url);
    source.onmessage = (msg) => {
      const event = JSON.parse(msg.data);
      if (event.stage === "end") { source.close(); resolve(); return; }
      onEvent(event);
    };
    source.onerror = () => { source.close(); resolve(); };
  });
}

async function run(url, steps, { feed = $("#feed"), step = $("#step-mode").checked, arch = false } = {}) {
  currentRun = { id: crypto.randomUUID(), steps, feed, step, arch };
  finalShown = false;
  resetRun();
  busy(true);
  await stream(`${url}&run=${currentRun.id}&step=${step}`, handleEvent);
  if (!finalShown) closeTheater();      // ingestion has no final answer to show: just close the stage
  document.querySelectorAll(".stage-card").forEach((b) => b.classList.remove("active"));
  currentRun = null;
  busy(false);
}

// ---- knowledge base ----------------------------------------------------------------------
async function refreshStatus() {
  status = await (await fetch("/api/status")).json();
  llmEnabled = status.llm_enabled;
  const s = status;
  $("#status-chips").innerHTML = `
    <span class="chip ${s.llm_enabled ? "on" : "off"}">LLM <b>${s.llm_enabled ? esc(s.model.replace("openai/", "")) : "offline"}</b></span>
    <span class="chip pinecone-chip ${s.problem ? "off" : "on"}" id="chip-pinecone" title="Click to test the Pinecone connection">Pinecone <b>${esc(s.vector_db.index)}</b></span>
    <span class="chip">Embeddings <b>${esc(s.embedding.model.split("/").pop())}</b></span>
    <span class="chip ${s.tracing.enabled ? "on" : ""}">LangSmith <b>${s.tracing.enabled ? "on" : "off"}</b></span>`;
  $("#chip-pinecone").onclick = checkPinecone;
  $("#kb-total").textContent = s.knowledge_base.total_chunks.toLocaleString();
  $("#kb-index").textContent = `index "${s.vector_db.index}" · namespace "${s.vector_db.namespace}"`;
  $("#doc-list").innerHTML = s.knowledge_base.documents.map((d) => `
    <li class="${d.source === lastAdded ? "new" : ""}"><span>${esc(d.source)}</span>
    <span class="muted">${d.chunks.toLocaleString()} · ${esc(d.department)}</span></li>`).join("");
  $("#model-info").innerHTML = `<div>Answer: <b>${esc(s.model)}</b></div><div>Fast jobs: <b>${esc(s.fast_model)}</b></div>
    <div>Embeddings: <b>${esc(s.embedding.model)}</b> (${s.embedding.dims} numbers)</div>
    <div class="muted">via OpenRouter · re-ranker runs locally</div>`;
  $("#langsmith-note").textContent = s.tracing.enabled
    ? `LangSmith tracing is ON - every run is logged to project "${s.tracing.project}".`
    : "LangSmith tracing is off. Set LANGSMITH_TRACING=true and LANGSMITH_API_KEY in .env to keep traces of every run.";
  setContext({ docs: s.knowledge_base.documents });
  setKnowledge({ docs: s.knowledge_base.documents });
  const ld = s.loading, box = $("#kb-loading");
  box.hidden = !ld.active;
  if (ld.active) {   // the server is still reading chunk texts back from Pinecone: poll until it is done
    box.textContent = `Reading your knowledge base back from Pinecone… ${ld.done.toLocaleString()} of ${ld.total ? ld.total.toLocaleString() : "?"} chunks. Searching works once this finishes.`;
    setTimeout(() => refreshStatus().then((n) => { if (!n.loading.active) refreshMap(); }), 2500);
  }
  if (s.problem) toast(`Pinecone problem: ${s.problem}`, 12000);
  return s;
}

async function checkPinecone() {
  toast("Testing the Pinecone connection…");
  const r = await (await fetch("/api/pinecone-check")).json();
  toast(r.ok ? `✓ Pinecone connected: index "${r.index}" (${r.dimension} dimensions), ${r.vectors_in_namespace.toLocaleString()} vectors in our namespace, ${r.vectors_in_index.toLocaleString()} in the whole index · answered in ${r.ms} ms`
             : `✗ Pinecone is NOT connected: ${r.error}`, 9000);
}

async function refreshMap() {
  const info = await (await fetch("/api/vector-map")).json();
  setPoints(info.points);
  const limit = status.limits.lens_max_tiles || 120;
  renderLens($("#lens"), info.points, info.total, limit, $("#lens-note"));
  lensSetOnDemand(!(info.total <= limit && !info.sampled));
  $("#space-note").textContent = info.sampled
    ? `a sample of ${info.points.length} of ${info.total.toLocaleString()} chunks · drag to rotate`
    : "3D PCA of the vectors · drag to rotate";
  setContext({ points: info.points });
  setKnowledge({ points: info.points });
}

function chunkParams() {
  return `strategy=${$("#strategy").value}&size=${$("#size").value}&overlap=${$("#overlap").value}&whole=${$("#big-scope").value === "whole"}`;
}

function startIngest() {
  $("#feed").innerHTML = "";
  resetTracker(INGEST_STEPS);
}

async function ingestUploaded(filename) {
  lastAdded = filename;
  startIngest();
  await run(`/api/ingest?file=${encodeURIComponent(filename)}&${chunkParams()}`, INGEST_STEPS);
  await refreshStatus();
  await refreshMap();
  toast(`${filename} is now searchable - click "✨ Suggest from my files" and ask about it.`);
}

async function uploadFile(file) {
  if (!file) return;
  const note = $("#upload-note");
  note.hidden = false;
  note.textContent = `Uploading ${file.name} (${(file.size / 1e6).toFixed(1)} MB)…`;
  const form = new FormData();
  form.append("file", file);
  const res = await fetch("/api/upload", { method: "POST", body: form });
  if (!res.ok) {
    const detail = (await res.json().catch(() => ({}))).detail || res.statusText;
    note.textContent = `✗ ${detail}`;
    return toast(detail, 8000);
  }
  const info = await res.json();
  const limit = status.limits.max_ingest_chars, whole = $("#big-scope").value === "whole";
  const big = info.size_mb * 1e6 > limit && info.estimate;
  note.textContent = `✓ Uploaded ${info.size_mb} MB in ${info.upload_ms} ms.` + (!big ? "" : whole
    ? ` Whole file: about ${info.estimate.chunks.toLocaleString()} chunks, ~${info.estimate.minutes} min, ~$${info.estimate.cost_usd}.`
    : ` Fast option: only the first ${limit.toLocaleString()} characters (~${info.estimate_fast.minutes} min). Choose "The whole file" for ~${info.estimate.minutes} min and ~$${info.estimate.cost_usd}.`);
  if (big && whole && info.estimate.minutes >= 2 &&
      !confirm(`Ingest the WHOLE file?

≈ ${info.estimate.chunks.toLocaleString()} chunks · about ${info.estimate.minutes} minutes · about $${info.estimate.cost_usd} of embedding cost.

You can keep using the page; progress is shown on the stage.`)) return;
  await ingestUploaded(info.filename);
}

async function emptyKnowledgeBase() {
  const total = $("#kb-total").textContent;
  if (!confirm(`Delete all ${total} chunks from the Pinecone namespace "${status.vector_db?.namespace}"?`)) return;
  busy(true);
  const res = await fetch("/api/reset", { method: "POST" });
  busy(false);
  if (!res.ok) return toast("Could not empty the knowledge base - see the server log.");
  const data = await res.json();
  lastAdded = null;
  $("#feed").innerHTML = `<div class="empty">Knowledge base emptied - removed ${data.removed.toLocaleString()} chunks from Pinecone.<br>Ingest documents to start again.</div>`;
  $("#latency-bars").innerHTML = '<div class="muted small">Run something to see timings.</div>';
  resetFunnel();
  resetTracker(INGEST_STEPS);
  resetTracker(QUERY_STEPS);
  await refreshStatus();
  await refreshMap();
  toast(`Emptied: ${data.removed.toLocaleString()} chunks deleted.`);
}

// ---- ask --------------------------------------------------------------------------------
async function ask(question) {
  if (!question.trim()) return;
  if ($("#kb-total").textContent === "0") return toast("The knowledge base is empty - ingest the sample docs first.");
  const strategy = $("#search-strategy").value, expansion = $("#expansion").value;
  $("#feed").innerHTML = "";
  resetFunnel();
  lensReset();
  clearSearch();
  const steps = activeQuerySteps(strategy);
  resetTracker(QUERY_STEPS, steps);
  await run(`/api/ask?q=${encodeURIComponent(question)}&strategy=${strategy}&expansion=${expansion}`, steps);
}

async function runArchitecture() {
  const arch = currentArch();
  if (!arch) return;
  if ($("#kb-total").textContent === "0") return toast("The knowledge base is empty - ingest some files on the Pipeline page first.");
  const question = $("#arch-question").value.trim() || arch.example;
  $("#arch-question").value = question;
  $("#arch-feed").innerHTML = "";
  stopExplainer();
  resetNodes();
  resetFunnel();
  lensReset();
  clearSearch();
  resetTracker(QUERY_STEPS, arch.stages);
  await run(`/api/ask?q=${encodeURIComponent(question)}&arch=${arch.id}`, arch.stages,
            { feed: $("#arch-feed"), step: $("#arch-step").checked, arch: true });
}

async function suggestInto(input) {
  toast("Reading a few chunks of your files…");
  const res = await fetch("/api/suggest-question");
  if (!res.ok) return toast("Could not suggest a question - is the knowledge base empty?");
  input.value = (await res.json()).question;
  input.focus();
}

function updateExplainer() {
  const strategy = $("#search-strategy").value;
  const usesExpansion = strategy === "hybrid_expansion";
  $("#expansion").disabled = !usesExpansion;
  const s = STRATEGY_INFO[strategy], x = EXPANSION_INFO[$("#expansion").value];
  $("#explainer").innerHTML = `
    <div class="ex"><b>${s.title}</b>${s.text}</div>
    <div class="ex ${usesExpansion ? "" : "off"}"><b>${x.title}</b>${x.text}
      ${usesExpansion ? "" : '<br><i class="small">Choose "Hybrid + query expansion" to use it.</i>'}</div>`;
  resetTracker(QUERY_STEPS, activeQuerySteps(strategy));
}

// ---- tabs (including the architecture pages) -------------------------------------------------
function showTab(name) {
  document.querySelectorAll(".tab, .tab-panel").forEach((x) => x.classList.remove("active"));
  $(`.tab[data-tab="${name}"]`)?.classList.add("active");
  $(`#tab-${name}`).classList.add("active");
  $("#arch-dd").classList.toggle("active", name === "arch");
  if (name === "lab") refreshLabFiles();
  // The hero + stage cards sit above the tabs, so bring the chosen page into view.
  if (name !== "pipeline") $(`#tab-${name}`).scrollIntoView({ behavior: "smooth", block: "start" });
}

// ---- chunking lab -------------------------------------------------------------------------
async function refreshLabFiles() {
  const current = $("#lab-file").value;
  const { files } = await refreshStatus();
  $("#lab-file").innerHTML = files.map((f) => `<option ${f === current ? "selected" : ""}>${esc(f)}</option>`).join("");
  refreshLab();
}

async function refreshLab() {
  const file = $("#lab-file").value;
  const size = +$("#lab-size").value, overlap = Math.min(+$("#lab-overlap").value, size - 20);
  $("#lab-size-out").textContent = size;
  $("#lab-overlap-out").textContent = overlap;
  if (!file) return;
  const res = await fetch(`/api/chunk-preview?file=${encodeURIComponent(file)}&size=${size}&overlap=${overlap}`);
  if (!res.ok) return toast("Could not preview that file.");
  const data = await res.json();
  const blurb = { fixed: "cuts every N characters - fast, but splits words", recursive: "paragraph › line › sentence › word", markdown: "never crosses a heading" };
  $("#lab-columns").innerHTML = Object.entries(data).map(([name, chunks]) => `
    <div class="lab-col panel"><h2>${name} <span>· ${chunks.length} chunks · ${blurb[name]}</span></h2>
    ${chunks.slice(0, 40).map(chunkCard).join("")}${chunks.length > 40 ? `<p class="muted small">…and ${chunks.length - 40} more chunks</p>` : ""}</div>`).join("");
}

// ---- evals ---------------------------------------------------------------------------------
async function runEval(framework) {
  const feed = $("#eval-feed");
  if (!llmEnabled) {
    feed.innerHTML = `<article class="card warn">Evals need an LLM judge. Add OPENROUTER_API_KEY to .env and restart the server.</article>`;
    return;
  }
  busy(true);
  feed.innerHTML = "";
  document.querySelectorAll(".stage-card").forEach((b) => b.classList.remove("active", "done"));
  const strat = $("#eval-strategy").value;
  await stream(`/api/eval?framework=${framework}&strategy=${strat === "hybrid_expansion" ? "hybrid_expansion&expansion=mqe" : strat}`, (e) => {
    lightUp(e);
    const el = document.createElement("article");
    el.className = `card ${e.status === "error" ? "warn" : "evaluate"}`;
    if (e.stage === "eval" && e.status === "done") {
      const rows = e.data.scores.map((s) => `<tr><td>${esc(s.metric)}</td><td><b>${s.score.toFixed(2)}</b></td>
        <td>${s.passed == null ? "" : `<span class="${s.passed ? "pass" : "fail"}">${s.passed ? "PASS" : "FAIL"}</span> (≥ ${s.threshold})`}</td>
        <td class="muted">${esc(s.reason || "")}</td></tr>`).join("");
      el.innerHTML = `<header><b>${esc(e.data.question)}</b><span class="ms">${e.ms ?? ""} ms</span></header>
        <p class="small">Answer: ${esc(e.data.answer)}</p>
        <table><tr><th>Metric</th><th>Score</th><th>Pass?</th><th>Reason</th></tr>${rows}</table>`;
    } else if (e.stage === "eval_summary") {
      el.innerHTML = `<header><b>Summary · ${esc(framework)} · ${esc(strat)}</b></header><table>${Object.entries(e.data.averages)
        .map(([m, v]) => `<tr><td>${esc(m)}</td><td><b>${v.toFixed(2)}</b></td></tr>`).join("")}</table>
        ${e.data.pass_rate != null ? `<p>Pass rate: <b>${Math.round(e.data.pass_rate * 100)}%</b></p>` : ""}`;
    } else {
      el.innerHTML = `<p class="small">${esc(e.message)}</p>`;
    }
    feed.appendChild(el);
  });
  busy(false);
}

// ---- wire everything up -----------------------------------------------------------------------
async function init() {
  buildTracker("#track-ingest", INGEST_STEPS);
  buildTracker("#track-query", QUERY_STEPS);
  init3D($("#space3d"), $("#space-tip"));
  initTheater();
  const s = await refreshStatus();
  await refreshMap();
  await loadArchitectures();

  $("#strategy").innerHTML = s.strategies.map((x) => `<option ${x === s.defaults.strategy ? "selected" : ""}>${x}</option>`).join("");
  $("#size").value = s.defaults.size;
  $("#overlap").value = s.defaults.overlap;
  const syncOut = () => { $("#size-out").textContent = $("#size").value; $("#overlap-out").textContent = $("#overlap").value; };
  ["#size", "#overlap"].forEach((id) => $(id).addEventListener("input", syncOut));
  syncOut();

  $("#btn-ingest-samples").onclick = () => { startIngest(); run(`/api/ingest-samples?${chunkParams()}`, INGEST_STEPS).then(() => refreshStatus().then(refreshMap)); };
  $("#btn-reset").onclick = emptyKnowledgeBase;
  $("#btn-demo-upload").onclick = async () => {
    const { filename } = await (await fetch("/api/upload-demo", { method: "POST" })).json();
    await ingestUploaded(filename);
  };
  $("#drop").onclick = () => $("#file-input").click();
  $("#file-input").onchange = (ev) => { uploadFile(ev.target.files[0]); ev.target.value = ""; };
  const drop = $("#drop");
  drop.ondragover = (ev) => { ev.preventDefault(); drop.classList.add("over"); };
  drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = (ev) => { ev.preventDefault(); drop.classList.remove("over"); uploadFile(ev.dataTransfer.files[0]); };

  // the stage buttons
  $("#btn-next").onclick = () => continueRun("next");
  $("#btn-run-all").onclick = () => continueRun("all");
  $("#btn-th-close").onclick = closeTheater;
  document.addEventListener("keydown", (ev) => {   // → or Enter also advances when the stage is waiting
    if (!$("#theater").hidden && !$("#btn-next").disabled && (ev.key === "ArrowRight" || ev.key === "Enter")) { ev.preventDefault(); continueRun("next"); }
  });

  $("#ask-form").onsubmit = (ev) => { ev.preventDefault(); ask($("#question").value); };
  // Each example is chosen to make one strategy shine (hover a chip to see which).
  const examples = [
    ["How much time off after my kid is born?", "Dense wins: no shared words with 'parental leave', but same meaning"],
    ["Who do I call on extension 4400?", "BM25 wins: an exact number that embeddings barely notice"],
    ["Can I use SMS codes for MFA?", "Hybrid: both methods agree on the right chunk"],
    ["Which floor is the new head office on?", "Unanswerable until you upload the demo file"],
  ];
  $("#examples").innerHTML = examples.map(([q, tip]) => `<button type="button" title="${esc(tip)}">${esc(q)}</button>`).join("")
    + '<button type="button" id="btn-suggest" title="The AI reads a few chunks of YOUR files and writes a question they can answer">✨ Suggest from my files</button>';
  $("#examples").querySelectorAll("button:not(#btn-suggest)").forEach((b) => (b.onclick = () => { $("#question").value = b.textContent; ask(b.textContent); }));
  $("#btn-suggest").onclick = () => suggestInto($("#question"));
  $("#search-strategy").onchange = updateExplainer;
  $("#expansion").onchange = updateExplainer;
  updateExplainer();

  // tabs + the architecture menu in the top bar
  document.querySelectorAll(".tab").forEach((t) => (t.onclick = () => showTab(t.dataset.tab)));
  $("#arch-dd-btn").onclick = (ev) => { ev.stopPropagation(); $("#arch-dd").classList.toggle("show"); };
  document.addEventListener("click", () => $("#arch-dd").classList.remove("show"));
  $("#arch-menu").onclick = (ev) => {
    const b = ev.target.closest("button");
    if (!b) return;
    showArchitecture(b.dataset.id);
    showTab("arch");
    $("#arch-dd").classList.remove("show");
  };
  $("#arch-play").onclick = playExplainer;
  $("#arch-stop").onclick = () => stopExplainer();
  $("#arch-run").onclick = runArchitecture;
  $("#arch-suggest").onclick = () => suggestInto($("#arch-question"));
  showArchitecture(location.hash.startsWith("#arch=") ? location.hash.slice(6) : "naive");

  ["#lab-file", "#lab-size", "#lab-overlap"].forEach((id) => $(id).addEventListener("input", refreshLab));
  $("#btn-ragas").onclick = () => runEval("ragas");
  $("#btn-deepeval").onclick = () => runEval("deepeval");
}

init();
