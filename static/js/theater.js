// theater.js - the animated "stage" in the middle of the page.
//
// For every pipeline step there is one SCENE: a small animation built from the REAL data of
// that step (your file name, your chunks, the judge's scores...) plus a story for a 13-year-old.
// While the computer is still working the stage shows a "working" scene instead, so there is
// never a dead moment (an LLM call can take several seconds).
//
// Flow, driven by main.js:
//   working(stage, ...)   -> a StageEvent with status "running" arrived
//   showScene(event)      -> a stage finished: play its scene
//   setReady(...)         -> the server paused: enable "Next step" (the student clicks when ready)
//
// Animations use the Web Animations API (element.animate): no library, easy to read.

import { DEPT_COLOR, STAGE_ICON, STAGE_KID, STAGE_LABEL, STAGE_INFO, WORKING } from "./explain.js";

// ---- tiny helpers ---------------------------------------------------------------------
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const short = (t, n = 60) => (String(t).length > n ? String(t).slice(0, n - 1).trimEnd() + "…" : String(t));
const make = (html) => { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstElementChild; };
const EASE = "cubic-bezier(.2,.8,.2,1)";
const go = (node, frames, options = {}) =>
  node.animate(frames, { duration: 600, easing: EASE, fill: "both", ...options }).finished.catch(() => {});
const label = (src, idx) => `${src.replace(/\.(md|txt|pdf)$/, "")} #${idx}`;
const chip = (r) => `<span class="chip-c" style="--c:${DEPT_COLOR[r.department] || "#64748b"}">${esc(short(label(r.source, r.chunk_index), 26))}</span>`;
const CARD_COLORS = ["#4f46e5", "#0891b2", "#059669", "#d97706", "#e11d48", "#7c3aed", "#0d9488", "#db2777"];

// Count a number up (for "N chunks stored").
function countUp(node, to, ms = 900) {
  const start = performance.now();
  const tick = (now) => {
    const t = Math.min(1, (now - start) / ms);
    node.textContent = Math.round(to * (1 - Math.pow(1 - t, 3))).toLocaleString();
    if (t < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

// FLIP: animate an element from where it WAS (a DOMRect) to where it is now.
function flyFrom(node, fromRect, options = {}) {
  const to = node.getBoundingClientRect();
  const dx = fromRect.left + fromRect.width / 2 - (to.left + to.width / 2);
  const dy = fromRect.top + fromRect.height / 2 - (to.top + to.height / 2);
  return go(node, [{ transform: `translate(${dx}px, ${dy}px) scale(.35)`, opacity: 0 }, { transform: "none", opacity: 1 }], options);
}

// ---- state --------------------------------------------------------------------------------
let box, sceneEl, titleEl, stepEl, kidEl, techEl, nextEl, btnNext, btnAll, btnClose;
let token = 0;                     // bumped whenever a new scene starts; old scenes stop animating
let ctx = { points: [], docs: [] };// what the knowledge base looks like (set by main.js)
let last = {};                     // data from earlier events of this run that later scenes need

export function initTheater() {
  box = document.getElementById("theater");
  sceneEl = document.getElementById("th-scene");
  titleEl = document.getElementById("th-title");
  stepEl = document.getElementById("th-step");
  kidEl = document.getElementById("th-kid");
  techEl = document.getElementById("th-tech");
  nextEl = document.getElementById("th-next");
  btnNext = document.getElementById("btn-next");
  btnAll = document.getElementById("btn-run-all");
  btnClose = document.getElementById("btn-th-close");
  document.getElementById("btn-th-min").onclick = () => box.classList.toggle("min");
}

export const setContext = (c) => { ctx = { ...ctx, ...c }; };
export const resetRun = () => { last = {}; };

// Remember what later scenes need (for example the fuse scene shows the dense + BM25 lists).
export function noteEvent(e) {
  const d = e.data || {};
  if (e.status === "done" || e.status === "skipped") {
    if (e.stage === "chunk") last.chunk = d;
    if (e.stage === "dense") last.dense = d;
    if (e.stage === "bm25") last.bm25 = d;
    if (e.stage === "postfilter") last.postfilter = d;
    if (e.stage === "prompt") last.prompt = d;
    if (e.stage === "query") last.query = d;
    if (e.stage === "tool_call") last.tool = d;
    if (e.stage === "answer") last.answer = d;
  }
}

function open() { box.hidden = false; requestAnimationFrame(() => box.classList.add("open")); }
export function closeTheater() { token++; box.classList.remove("open", "min"); setTimeout(() => (box.hidden = true), 250); }

function setButtons(ready, nextText = "") {
  btnNext.disabled = btnAll.disabled = !ready;
  btnNext.hidden = btnAll.hidden = false;
  btnClose.hidden = true;
  nextEl.innerHTML = ready && nextText ? `<b>Next:</b> ${esc(nextText)}` : ready ? "" : "";
}

// After a click on "Next step": lock the buttons until the next step is ready.
export function lockButtons(text = "Working…") {
  btnNext.disabled = btnAll.disabled = true;
  nextEl.textContent = text;
}

// ---- WORKING state (a stage is still running) --------------------------------------------------
export function working(stage, message, data = {}) {
  open();
  titleEl.textContent = `${STAGE_ICON[stage] || "⚙️"} ${STAGE_LABEL[stage] || stage}`;
  const pct = data.total ? Math.round((data.done / data.total) * 100) : null;
  const existing = sceneEl.querySelector(`.sc-work[data-stage="${stage}"]`);
  if (existing) {   // same stage, just a progress update: don't restart the animation
    existing.querySelector(".work-msg").textContent = message;
    if (pct != null) { existing.querySelector(".pbar i").style.width = `${pct}%`; existing.querySelector(".pcount").textContent = `${data.done.toLocaleString()} of ${data.total.toLocaleString()}`; }
    return;
  }
  token++;
  sceneEl.innerHTML = `<div class="sc sc-work" data-stage="${stage}"><div class="gear">⚙️</div>
    <div class="work-msg">${esc(message || WORKING[stage] || "Working…")}</div>
    ${pct != null ? `<div class="pbar"><i style="width:${pct}%"></i></div><div class="pcount muted small">${data.done.toLocaleString()} of ${data.total.toLocaleString()}</div>`
                   : '<div class="dots"><i></i><i></i><i></i></div>'}</div>`;
  kidEl.textContent = WORKING[stage] || "";
  techEl.textContent = "";
  setButtons(false);
}

// ---- scenes ---------------------------------------------------------------------------------------
// Each scene: (data, event) -> { html, kid?, tech?, run?(root, alive) }
const SCENES = {
  // ======================= INGEST =======================
  load: (d) => ({
    html: `<div class="sc sc-load">
        <div class="doc" id="a-doc"><b>${esc(d.doc_type.toUpperCase())}</b><span>${esc(short(d.source, 22))}</span>${"<i></i>".repeat(6)}</div>
        <div class="letters" id="a-letters"></div>
        <div class="actor" id="a-bot">🤖</div>
        <div class="stat" id="a-stat" style="opacity:0">
          ${d.pages} page${d.pages === 1 ? "" : "s"} · <b>${d.used_chars.toLocaleString()}</b> characters read
          ${d.truncated ? `<div class="warn-note">✂️ Big file! ${d.size_mb} MB = ${d.file_chars.toLocaleString()} characters. You chose the fast option, so we only read the first
             <b>${Math.max(0.1, d.used_chars / d.file_chars * 100).toFixed(1)}%</b>. Pick "The whole file" under <i>Big files</i> to read everything
             (about ${d.estimate_whole?.minutes ?? "?"} min).</div>` : ""}
        </div></div>`,
    tech: d.truncated ? `The cut is made at a paragraph break (MAX_INGEST_CHARS in .env sets the size of the fast option).` : "",
    run: async (root, alive) => {
      const doc = root.querySelector("#a-doc"), bot = root.querySelector("#a-bot"), letters = root.querySelector("#a-letters");
      await go(doc, [{ transform: "translateX(-90px)", opacity: 0 }, { transform: "none", opacity: 1 }], { duration: 500 });
      for (let i = 0; i < 16 && alive(); i++) {   // letters fly from the page into the robot's head
        const l = make(`<span class="lt">${"abcdefghijklmnopqrstuvwxyz"[Math.floor(Math.random() * 26)]}</span>`);
        letters.appendChild(l);
        go(l, [{ transform: "translate(0,0)", opacity: 1 }, { transform: `translate(${150 + Math.random() * 30}px, ${-20 + Math.random() * 40}px)`, opacity: 0 }], { duration: 650 });
        await sleep(60);
      }
      go(bot, [{ transform: "scale(1)" }, { transform: "scale(1.3) rotate(-6deg)" }, { transform: "scale(1)" }], { duration: 450 });
      go(root.querySelector("#a-stat"), [{ opacity: 0, transform: "translateY(8px)" }, { opacity: 1, transform: "none" }]);
    },
  }),

  chunk: (d) => {
    const cards = d.chunks.slice(0, 8);
    return {
      html: `<div class="sc sc-chunk">
        <div class="sheet" id="a-sheet">${"<i></i>".repeat(10)}${[1, 2, 3, 4, 5, 6, 7].map((n) => `<u class="cut" style="top:${n * 12}%"></u>`).join("")}<span class="scissors" id="a-scis">✂️</span></div>
        <div class="cards" id="a-cards">${cards.map((c, i) => `
          <div class="mini" style="--c:${CARD_COLORS[i % 8]}">
            ${i > 0 && c.overlap ? `<u class="ov" title="shared with the previous card">${esc(short(c.text.slice(0, c.overlap), 34))}</u>` : ""}
            <b>#${c.index}</b><small>${c.size} chars</small><p>${esc(short(c.text.slice(c.overlap || 0), 62))}</p></div>`).join("")}
          ${d.total > cards.length ? `<div class="mini ghost"><b>+ ${(d.total - cards.length).toLocaleString()}</b><small>more cards</small></div>` : ""}</div>
        <div class="stat" id="a-stat" style="opacity:0"><span class="big" id="a-count">0</span> flash cards · about ${d.avg_size} characters each</div></div>`,
      tech: `Strategy "${d.strategy}". The yellow strip on a card is the overlap it shares with the card before it.`,
      run: async (root, alive) => {
        const sheet = root.querySelector("#a-sheet"), cardsEl = root.querySelector("#a-cards"), scis = root.querySelector("#a-scis");
        const minis = [...cardsEl.children];
        cardsEl.style.visibility = "hidden";
        await go(sheet, [{ opacity: 0, transform: "scale(.8)" }, { opacity: 1, transform: "none" }], { duration: 450 });
        const cuts = [...sheet.querySelectorAll(".cut")];
        for (let i = 0; i < cuts.length && alive(); i++) {            // the scissors cut line after line
          go(scis, [{ top: `${i * 12 + 4}%` }, { top: `${i * 12 + 16}%` }], { duration: 240 });
          await go(cuts[i], [{ transform: "scaleX(0)" }, { transform: "scaleX(1)" }], { duration: 240 });
        }
        if (!alive()) return;
        const from = sheet.getBoundingClientRect();
        cardsEl.style.visibility = "visible";
        go(sheet, [{ opacity: 1 }, { opacity: 0, transform: "scale(.85)" }], { duration: 400 });
        minis.forEach((m, i) => flyFrom(m, from, { duration: 650, delay: i * 80 }));   // the sheet breaks into cards
        await sleep(650 + minis.length * 80);
        root.querySelectorAll(".ov").forEach((o) => go(o, [{ opacity: 0 }, { opacity: 1 }], { duration: 500 }));
        go(root.querySelector("#a-stat"), [{ opacity: 0 }, { opacity: 1 }]);
        countUp(root.querySelector("#a-count"), d.total);
      },
    };
  },

  embed: (d) => {
    const rows = (last.chunk?.chunks || []).slice(0, 3);
    const colour = (v) => (v < 0 ? `rgba(8,145,178,${Math.min(1, Math.abs(v) * 7 + .15)})` : `rgba(124,58,237,${Math.min(1, v * 7 + .15)})`);
    return {
      html: `<div class="sc sc-embed">${rows.map((c, i) => `
        <div class="erow" style="opacity:0"><div class="mini sm" style="--c:${CARD_COLORS[i]}"><b>#${c.index}</b><p>${esc(short(c.text, 46))}</p></div>
          <span class="arrow">🔢 →</span>
          <div class="nums">${(d.preview[i] || []).map((v) => `<s style="background:${colour(v)}">${v}</s>`).join("")}<em>… ${(d.dims - 8).toLocaleString()} more numbers</em></div></div>`).join("")}
        <div class="stat" style="opacity:0" id="a-stat"><b>${d.total.toLocaleString()}</b> cards × <b>${d.dims.toLocaleString()}</b> numbers = <b>${(d.total * d.dims).toLocaleString()}</b> numbers</div></div>`,
      tech: "Purple cells are positive numbers, blue cells negative. Similar meaning gives similar patterns.",
      run: async (root, alive) => {
        for (const row of root.querySelectorAll(".erow")) {
          if (!alive()) return;
          go(row, [{ opacity: 0, transform: "translateX(-30px)" }, { opacity: 1, transform: "none" }], { duration: 450 });
          const cells = [...row.querySelectorAll("s")];
          for (const c of cells) { go(c, [{ transform: "scale(0)" }, { transform: "scale(1)" }], { duration: 220 }); await sleep(45); }
        }
        go(root.querySelector("#a-stat"), [{ opacity: 0 }, { opacity: 1 }]);
      },
    };
  },

  store: (d) => {
    const total = d.total || 0, n = Math.min(6, total || 6);
    return {
      html: `<div class="sc sc-store">
        <div class="stack">${Array.from({ length: n }, (_, i) => `<div class="mini sm" style="--c:${CARD_COLORS[i]}"><b>🔢</b></div>`).join("")}</div>
        <div class="vault" id="a-vault"><div class="cyl"><span>🗄️</span></div><b>Pinecone</b><small>the locker room</small>
          <div class="stat"><span class="big" id="a-count">0</span> cards stored</div></div>
        <div class="clock" id="a-clock" style="opacity:0">⏱️ searchable after <b>${d.freshness_wait_s}s</b><small>Pinecone needs a moment to file new cards</small></div></div>`,
      tech: d.knowledge_base ? `Knowledge base now holds ${d.knowledge_base.total_chunks.toLocaleString()} chunks from ${d.knowledge_base.documents.length} file(s).` : "",
      run: async (root, alive) => {
        const vault = root.querySelector("#a-vault").getBoundingClientRect();
        const slips = [...root.querySelectorAll(".stack .mini")];
        for (const [i, s] of slips.entries()) {
          if (!alive()) return;
          const r = s.getBoundingClientRect();
          const dx = vault.left + vault.width / 2 - (r.left + r.width / 2), dy = vault.top + 40 - (r.top + r.height / 2);
          go(s, [{ transform: "none", opacity: 1 }, { transform: `translate(${dx / 2}px, ${dy - 50}px) scale(.8)`, opacity: 1 }, { transform: `translate(${dx}px, ${dy}px) scale(.2)`, opacity: 0 }], { duration: 700 });
          await sleep(180);
          if (i === 1) go(root.querySelector(".cyl"), [{ transform: "scale(1)" }, { transform: "scale(1.08)" }, { transform: "scale(1)" }], { duration: 500, iterations: 2 });
        }
        countUp(root.querySelector("#a-count"), total, 1000);
        await sleep(700);
        go(root.querySelector("#a-clock"), [{ opacity: 0, transform: "translateY(10px)" }, { opacity: 1, transform: "none" }]);
      },
    };
  },

  // ======================= RETRIEVE =======================
  query: (d) => ({
    html: `<div class="sc sc-query"><div class="bubble" id="a-bubble"><span id="a-typed"></span><i class="caret"></i></div>
      <div class="badges"><span class="badge s-d">${esc(d.strategy)}</span>${d.strategy === "hybrid_expansion" ? `<span class="badge s-f">${esc(d.expansion)}</span>` : ""}
      ${d.architecture ? `<span class="badge">${esc(d.architecture)}</span>` : ""}</div></div>`,
    run: async (root, alive) => {
      const typed = root.querySelector("#a-typed");
      go(root.querySelector("#a-bubble"), [{ opacity: 0, transform: "scale(.7)" }, { opacity: 1, transform: "none" }], { duration: 400 });
      for (const ch of d.question) { if (!alive()) return; typed.textContent += ch; await sleep(22); }
    },
  }),

  tool_call: (d) => {
    const a = d.args || {};
    const off = d.info?.mode === "off";
    return {
      html: `<div class="sc sc-tool"><div class="bubble sm">${esc(short(last.query?.question || "", 70))}</div>
        <div class="actor" id="a-bot">🕵️</div>
        <div class="ticket" id="a-ticket" style="opacity:0"><h5>🎫 Search ticket</h5>
          <p>🔎 search for: <b>${esc(a.query || "")}</b></p>
          <p>🗂️ shelf: <b>${a.department ? esc(a.department) : "any - look everywhere"}</b></p>
          <p>📄 file type: <b>${a.doc_type ? esc(a.doc_type) : "any"}</b></p>
          ${off ? '<p class="muted small">(This architecture skips planning: your question is used as written.)</p>' : ""}</div></div>`,
      tech: d.info?.note || "Tool arguments are validated by the Pydantic class ToolArgs.",
      run: async (root) => {
        go(root.querySelector("#a-bot"), [{ transform: "rotate(-10deg)" }, { transform: "rotate(10deg)" }, { transform: "rotate(0)" }], { duration: 700 });
        await sleep(500);
        go(root.querySelector("#a-ticket"), [{ opacity: 0, transform: "translateX(-40px) rotate(-4deg)" }, { opacity: 1, transform: "none" }], { duration: 600 });
      },
    };
  },

  expand: (d) => {
    if (d.method === "mqe") {
      const qs = Object.entries(d.queries || {});
      return {
        kid: "Sometimes the book uses different words than you do. So the AI asks your question again in other ways - and every version goes searching.",
        html: `<div class="sc sc-mqe"><div class="bubble center" id="a-main">${esc(short(qs[0]?.[1] || "", 70))}</div>
          <div class="fan">${qs.slice(1).map(([k, q]) => `<div class="bubble sm" style="opacity:0"><small>${esc(k)}</small>${esc(short(q, 80))}</div>`).join("")}</div></div>`,
        tech: `${qs.length} queries will each be searched with dense + BM25, and all lists are fused later.`,
        run: async (root, alive) => {
          for (const b of root.querySelectorAll(".fan .bubble")) { if (!alive()) return; go(b, [{ opacity: 0, transform: "translateY(-30px) scale(.8)" }, { opacity: 1, transform: "none" }], { duration: 500 }); await sleep(260); }
        },
      };
    }
    return {
      kid: "The AI writes a PRETEND answer first. Real cards that look like the pretend answer are probably the right ones - and the pretend answer is never shown as the real answer!",
      html: `<div class="sc sc-hyde"><div class="bubble sm">${esc(short(last.query?.question || "", 60))}</div><div class="actor" id="a-bot">✏️</div>
        <div class="paper"><div class="stamp">PRETEND - only used for searching</div><p id="a-typed"></p></div></div>`,
      tech: "HyDE: dense search uses the embedding of this passage; BM25 keeps your real words.",
      run: async (root, alive) => {
        const p = root.querySelector("#a-typed");
        for (const ch of (d.hyde_passage || "")) { if (!alive()) return; p.textContent += ch; await sleep(10); }
      },
    };
  },

  prefilter: (d) => {
    const counts = {};
    (ctx.docs || []).forEach((doc) => (counts[doc.department] = (counts[doc.department] || 0) + doc.chunks));
    const depts = Object.keys(counts).length ? Object.keys(counts) : Object.keys(DEPT_COLOR);
    const f = JSON.stringify(d.filter || {});
    const chosen = depts.find((k) => f.includes(`"${k}"`));
    return {
      html: `<div class="sc sc-shelves">${depts.map((k) => `<div class="shelf" data-k="${k}" style="--c:${DEPT_COLOR[k] || "#64748b"}">
          <div class="books">${"<i></i>".repeat(5)}</div><b>${esc(k)}</b><small>${(counts[k] || 0).toLocaleString()} cards</small></div>`).join("")}</div>
        <div class="note-line">${chosen ? `Only the <b>${esc(chosen)}</b> shelf stays open.` : "No filter: every shelf stays open - we search everywhere."}</div>`,
      kid: chosen ? STAGE_KID.prefilter.kid : "No shelf was closed this time: the AI did not pick a department, so we search everywhere.",
      tech: `Filter sent to Pinecone: ${f}`,
      run: async (root) => {
        await sleep(300);
        root.querySelectorAll(".shelf").forEach((s) => {
          if (chosen && s.dataset.k !== chosen) { s.classList.add("closed"); go(s, [{ opacity: 1 }, { opacity: .25, transform: "translateY(14px) scale(.94)" }], { duration: 600 }); }
          else s.classList.add("open");
        });
      },
    };
  },

  dense: (d) => {
    const pts = ctx.points || [];
    const lists = Object.values(d.lists || {});
    const hits = (lists[0] || []).slice(0, 5);
    const q = (d.query_points || [])[0];
    const W = 340, H = 260, X = (x) => W / 2 + x * 145, Y = (y) => H / 2 + y * 105;
    const pos = (id) => { const p = pts.find((p) => p.id === id); return p ? [p.x, p.y] : d.hit_points?.[id]?.slice(0, 2); };
    const hitSet = new Set(hits.map((h) => h.id));
    const lines = hits.map((h) => { const p = pos(h.id); return q && p ? `<line class="ln" x1="${X(q.xyz[0])}" y1="${Y(q.xyz[1])}" x2="${X(p[0])}" y2="${Y(p[1])}"/>` : ""; }).join("");
    return {
      html: `<div class="sc sc-dense">
        <svg viewBox="0 0 ${W} ${H}" class="map">
          ${pts.map((p) => `<circle class="dot ${hitSet.has(p.id) ? "hit" : ""}" cx="${X(p.x)}" cy="${Y(p.y)}" r="${hitSet.has(p.id) ? 6 : 3.6}" fill="${DEPT_COLOR[p.department] || "#64748b"}" opacity=".55"/>`).join("")}
          ${hits.filter((h) => !hitSet.has(h.id) || !pts.find((p) => p.id === h.id)).map((h) => { const p = pos(h.id); return p ? `<circle class="dot hit" cx="${X(p[0])}" cy="${Y(p[1])}" r="6" fill="${DEPT_COLOR[h.department]}" opacity=".7"/>` : ""; }).join("")}
          ${lines}
          ${q ? `<g class="qpt" transform="translate(${X(q.xyz[0])},${Y(q.xyz[1])})"><circle class="ripple" r="10"/><circle class="ripple r2" r="10"/><rect x="-8" y="-8" width="16" height="16" rx="3" transform="rotate(45)"/></g>` : ""}
        </svg>
        <div class="hitlist"><h5>Closest in meaning</h5>${hits.map((h) => `<div class="hrow" style="opacity:0">${chip(h)}
          <div class="mk"><i style="width:${Math.max(4, h.dense_score * 100)}%"></i></div><b>${h.dense_score.toFixed(2)}</b></div>`).join("") || '<p class="muted">Nothing close enough.</p>'}
          <p class="muted small">Score = cosine similarity: 1.0 means identical meaning.</p></div></div>`,
      tech: `${lists.length} query vector(s) searched. The map is a 2D squash of the real ${ctx.dims || ""} dimensions, so distances are approximate.`,
      run: async (root, alive) => {
        const dots = [...root.querySelectorAll(".dot")];
        dots.forEach((c, i) => go(c, [{ opacity: 0, transform: "scale(0)" }, { opacity: c.classList.contains("hit") ? .9 : .55, transform: "scale(1)" }], { duration: 300, delay: Math.min(i * 6, 500) }));
        await sleep(Math.min(dots.length * 6, 500) + 200);
        const qpt = root.querySelector(".qpt");
        if (qpt) go(qpt, [{ opacity: 0, transform: qpt.getAttribute("transform") + " scale(0)" }, { opacity: 1, transform: qpt.getAttribute("transform") + " scale(1)" }], { duration: 500 });
        await sleep(450);
        root.querySelectorAll(".ln").forEach((l, i) => { const len = 400; l.style.strokeDasharray = len; go(l, [{ strokeDashoffset: len }, { strokeDashoffset: 0 }], { duration: 600, delay: i * 120 }); });
        for (const row of root.querySelectorAll(".hrow")) { if (!alive()) return; go(row, [{ opacity: 0, transform: "translateX(24px)" }, { opacity: 1, transform: "none" }], { duration: 400 }); await sleep(150); }
      },
    };
  },

  bm25: (d) => {
    const first = Object.keys(d.lists || {})[0];
    const terms = (d.query_terms?.[first?.replace("bm25: ", "")] || []);
    const hits = ((d.lists || {})[first] || []).slice(0, 3);
    const mark = (r) => { let h = esc(short(r.text, 150)); (r.matched_terms || []).forEach((t) => { h = h.replace(new RegExp(`\\b(${t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})\\b`, "gi"), '<mark class="m">$1</mark>'); }); return h; };
    return {
      html: `<div class="sc sc-bm25"><div class="terms"><h5>Words we hunt for</h5>${terms.map((t) => `<span class="term">${esc(t)}</span>`).join("")}
          <p class="muted small">Common words like "the" are ignored.</p></div>
        <div class="hits">${hits.map((r) => `<div class="bcard" style="opacity:0">${chip(r)} <b class="sc-pts">${r.bm25_score.toFixed(1)} pts</b><p>${mark(r)}</p></div>`).join("")
          || '<div class="empty-note">🤷 No card contains these words, so BM25 finds nothing. (A meaning search might still help!)</div>'}</div></div>`,
      tech: "BM25 gives more points for rare words, with diminishing returns for repeats, and slightly punishes very long chunks.",
      run: async (root, alive) => {
        root.querySelectorAll(".term").forEach((t, i) => go(t, [{ transform: "scale(0)" }, { transform: "scale(1.15)" }, { transform: "scale(1)" }], { duration: 400, delay: i * 90 }));
        await sleep(300 + terms.length * 90);
        for (const c of root.querySelectorAll(".bcard")) {
          if (!alive()) return;
          go(c, [{ opacity: 0, transform: "translateY(14px)" }, { opacity: 1, transform: "none" }], { duration: 450 });
          await sleep(350);
          c.querySelectorAll("mark.m").forEach((m, i) => go(m, [{ backgroundColor: "transparent" }, { backgroundColor: "#fde047" }], { duration: 400, delay: i * 120 }));
          await sleep(250);
        }
      },
    };
  },

  fuse: (d) => {
    const dense = Object.values(last.dense?.lists || {})[0] || [];
    const bm = Object.values(last.bm25?.lists || {})[0] || [];
    const top = (d.results || []).slice(0, 6);
    const row = (r, extra = "") => `<div class="frow" data-id="${r.id}">${chip(r)}${extra}</div>`;
    const formula = (r) => r.found_by.map((f) => `1/(60+${f.split("#").pop()})`).join(" + ");
    return {
      html: `<div class="sc sc-fuse">
        <div class="col"><h5>🧭 Meaning list</h5>${dense.slice(0, 6).map((r, i) => row(r, `<em>#${i + 1}</em>`)).join("") || "<p class='muted small'>(not used)</p>"}</div>
        <div class="col"><h5>🔤 Word list</h5>${bm.slice(0, 6).map((r, i) => row(r, `<em>#${i + 1}</em>`)).join("") || "<p class='muted small'>(no matches)</p>"}</div>
        <div class="col merged"><h5>🤝 Merged</h5>${top.map((r, i) => `<div class="frow m" data-id="${r.id}" style="opacity:0"><em>#${i + 1}</em>${chip(r)}<small>${formula(r)} = <b>${r.fused_score.toFixed(4)}</b></small></div>`).join("")}</div></div>`,
      tech: `${(d.lists || []).length} list(s) fused. A chunk found by several lists collects several 1/(60 + rank) scores.`,
      run: async (root, alive) => {
        for (const m of root.querySelectorAll(".frow.m")) {
          if (!alive()) return;
          const id = m.dataset.id;
          root.querySelectorAll(`.col:not(.merged) .frow[data-id="${id}"]`).forEach((n) => go(n, [{ background: "transparent" }, { background: "#fef08a" }, { background: "#fef9c3" }], { duration: 700 }));
          go(m, [{ opacity: 0, transform: "translateX(-24px)" }, { opacity: 1, transform: "none" }], { duration: 450 });
          await sleep(420);
        }
      },
    };
  },

  postfilter: (d) => {
    const kept = (d.results || []).slice(0, 8), dropped = (d.dropped || []).slice(0, 5);
    const card = (r, bad) => `<div class="pcard ${bad ? "bad" : "ok"}" data-bad="${bad ? 1 : 0}">${chip(r)}<p>${esc(short(r.text, 54))}</p>
      <small>${bad ? `too weak${r.dense_score != null ? ` (cos ${r.dense_score.toFixed(2)})` : ""}` : "✓ strong"}</small></div>`;
    const order = [...kept, ...dropped].sort((a, b) => ((b.fused_score ?? b.dense_score ?? 0) - (a.fused_score ?? a.dense_score ?? 0)));
    return {
      html: `<div class="sc sc-sieve"><div class="pool">${order.map((r) => card(r, dropped.some((x) => x.id === r.id))).join("")}</div>
        <div class="sieve"><span>🧹 sieve</span></div>
        <div class="stat"><b>${kept.length}</b> strong cards stay${(d.report?.dropped_duplicate || 0) ? ` · ${d.report.dropped_duplicate} copies removed` : ""}${d.report?.dropped_low_score ? ` · ${d.report.dropped_low_score} weak dropped` : ""}</div></div>`,
      tech: `Rule: keep a card if its cosine ≥ ${d.report?.min_score ?? "?"} OR it shares a keyword; drop near-duplicates; keep at most 8.`,
      run: async (root) => {
        const cards = [...root.querySelectorAll(".pcard")];
        cards.forEach((c, i) => go(c, [{ opacity: 0, transform: "translateY(-20px)" }, { opacity: 1, transform: "none" }], { duration: 350, delay: i * 50 }));
        await sleep(450 + cards.length * 50);
        for (const c of cards.filter((c) => c.dataset.bad === "1")) {
          go(c, [{ transform: "none", opacity: 1 }, { transform: "translateX(-5px)" }, { transform: "translateX(5px)" }, { transform: "translateY(150px) rotate(14deg)", opacity: 0 }], { duration: 900, easing: "ease-in" });
          await sleep(220);
        }
        cards.filter((c) => c.dataset.bad === "0").forEach((c) => go(c, [{ boxShadow: "0 0 0 0 #86efac" }, { boxShadow: "0 0 0 4px #86efac" }], { duration: 500 }));
      },
    };
  },

  rerank: (d) => {
    const rows = d.ranking || d.results || [];
    const byBefore = [...rows].sort((a, b) => (a.before_rank ?? 0) - (b.before_rank ?? 0));
    const scores = rows.map((r) => r.rerank_score ?? 0), lo = Math.min(...scores), hi = Math.max(...scores), span = hi - lo || 1;
    const keep = d.keep ?? d.results?.length ?? rows.length;
    return {
      html: `<div class="sc sc-rank"><div class="qline">❓ <b>${esc(short(last.query?.question || "", 90))}</b></div>
        <div class="legend-line"><span>before</span><span>⚖️ the judge's marks (how well each card answers the question)</span><span>after</span></div>
        <div class="rlist" id="a-rlist">${byBefore.map((r) => `<div class="rrow" data-id="${r.id}" data-score="${r.rerank_score}" data-bar="${((r.rerank_score - lo) / span * 100).toFixed(0)}">
          <span class="rk b">#${r.before_rank}</span>${chip(r)}<span class="txt">${esc(short(r.text, 46))}</span>
          <span class="mark"><i style="width:0"></i></span><b class="num"></b><span class="rk a"></span></div>`).join("")}</div></div>`,
      tech: `Cross-encoder scores are raw logits (higher = better). The top ${keep} are kept; the rest are discarded.`,
      run: async (root, alive) => {
        const list = root.querySelector("#a-rlist");
        const els = [...list.querySelectorAll(".rrow")];
        els.forEach((r, i) => go(r, [{ opacity: 0, transform: "translateX(-20px)" }, { opacity: 1, transform: "none" }], { duration: 300, delay: i * 40 }));
        await sleep(350 + els.length * 40);
        for (const r of els) {                         // the judge reads one card at a time and gives marks
          if (!alive()) return;
          r.classList.add("scan");
          await sleep(220);
          r.querySelector(".mark i").style.width = `${Math.max(4, r.dataset.bar)}%`;
          r.querySelector(".num").textContent = (+r.dataset.score).toFixed(1);
          r.classList.remove("scan");
        }
        await sleep(500);
        if (!alive()) return;
        const first = new Map(els.map((r) => [r, r.getBoundingClientRect()]));    // FLIP: remember where each row is
        els.sort((a, b) => b.dataset.score - a.dataset.score).forEach((r) => list.appendChild(r));   // re-sort the DOM
        els.forEach((r, i) => {                                                    // animate each row to its new place
          const dy = first.get(r).top - r.getBoundingClientRect().top;
          go(r, [{ transform: `translateY(${dy}px)` }, { transform: "none" }], { duration: 1100, easing: "cubic-bezier(.5,0,.2,1)" });
          const a = r.querySelector(".rk.a"); a.textContent = i < keep ? `★ ${i + 1}` : `#${i + 1}`;
          r.classList.add(i < keep ? "keep" : "toss");
        });
      },
    };
  },

  prompt: (d) => {
    const chunks = (d.chunks || []).slice(0, 4);
    return {
      html: `<div class="sc sc-prompt"><div class="slips">
          <div class="slip rules">📜 Rules: "use ONLY these cards, cite [1], [2]…"</div>
          ${chunks.map((c, i) => `<div class="slip" style="--c:${CARD_COLORS[i]}">[${i + 1}] ${chip(c)} <p>${esc(short(c.text, 50))}</p></div>`).join("")}
          <div class="slip q">❓ ${esc(short(last.query?.question || "", 60))}</div></div>
        <div class="letter" id="a-letter"><div class="flap">✉️</div><b>The letter for the AI writer</b>
          <div class="stat"><span class="big" id="a-count">0</span> characters</div></div></div>`,
      tech: "Everything the model sees is in this letter. Open the 'Rendered prompt' card below to read it.",
      run: async (root, alive) => {
        const letter = root.querySelector("#a-letter").getBoundingClientRect();
        for (const s of root.querySelectorAll(".slip")) {
          if (!alive()) return;
          const r = s.getBoundingClientRect();
          go(s, [{ transform: "none", opacity: 1 }, { transform: `translate(${letter.left - r.left + 40}px, ${letter.top - r.top + 30}px) scale(.3) rotate(6deg)`, opacity: 0 }], { duration: 650, easing: "ease-in" });
          await sleep(300);
        }
        countUp(root.querySelector("#a-count"), +(d.prompt || "").length || 0, 700);
        go(root.querySelector("#a-letter"), [{ transform: "scale(1)" }, { transform: "scale(1.06)" }, { transform: "scale(1)" }], { duration: 500 });
      },
    };
  },

  // ======================= GENERATE =======================
  answer: (d) => ({
    html: `<div class="sc sc-answer"><div class="actor" id="a-bot">✍️</div><div class="paper wide"><p id="a-typed"></p><i class="caret"></i></div></div>`,
    tech: "Each [n] points at the numbered card in the prompt.",
    run: async (root, alive) => {
      const p = root.querySelector("#a-typed");
      const text = d.answer || "";
      for (let i = 0; i < text.length && alive(); i += 2) { p.textContent = text.slice(0, i + 2); await sleep(14); }
      if (!alive()) return;
      const chunks = last.prompt?.chunks || [];
      p.innerHTML = esc(text).replace(/\[(\d+)\]/g, (m, n) => `<span class="cite" title="${esc(chunks[n - 1] ? label(chunks[n - 1].source, chunks[n - 1].chunk_index) : "")}">${n}</span>`);
      root.querySelector(".caret")?.remove();
    },
  }),

  reflect: (d) => {
    const c = d.check || {};
    const ok = c.grounded;
    return {
      html: `<div class="sc sc-reflect"><div class="paper wide"><p>${esc(short(last.answer?.answer || "", 260))}</p><span class="lens-sweep" id="a-mag">🔍</span></div>
        <div class="stampbig ${ok ? "ok" : "bad"}" id="a-stamp" style="opacity:0">${ok ? "✅ GROUNDED" : "❌ NOT GROUNDED"}</div>
        <p class="why-line" id="a-why" style="opacity:0">${esc(c.reason || "")}</p>
        ${(c.unsupported_claims || []).map((x) => `<p class="claim" style="opacity:0">⚠️ ${esc(x)}</p>`).join("")}</div>`,
      tech: ok ? "Every claim is supported by the retrieved cards." : "The pipeline will now retry once with a rewritten query.",
      run: async (root) => {
        await go(root.querySelector("#a-mag"), [{ left: "0%" }, { left: "88%" }], { duration: 1100, easing: "ease-in-out" });
        go(root.querySelector("#a-stamp"), [{ opacity: 0, transform: "scale(2.2) rotate(-12deg)" }, { opacity: 1, transform: "scale(1) rotate(-6deg)" }], { duration: 500 });
        await sleep(450);
        root.querySelectorAll(".why-line, .claim").forEach((n) => go(n, [{ opacity: 0 }, { opacity: 1 }], { duration: 500 }));
      },
    };
  },

  retry: (d) => ({
    html: `<div class="sc"><div class="loop">🔁</div><p class="why-line">New search words: <b>${esc(d.rewritten_query || "")}</b></p></div>`,
    run: async (root) => go(root.querySelector(".loop"), [{ transform: "rotate(0)" }, { transform: "rotate(360deg)" }], { duration: 1200 }),
  }),

  final: (d) => ({
    html: `<div class="sc sc-final"><div class="spark">✨</div><div class="paper wide"><p>${esc(short(d.answer || "", 420))}</p></div>
      <p class="muted small">${d.grounded == null ? "Not fact-checked" : d.grounded ? "Fact-checked: grounded" : "Could not be fully grounded"} · ${d.attempts} attempt(s)</p></div>`,
    run: async (root) => go(root.querySelector(".spark"), [{ transform: "scale(0) rotate(0)" }, { transform: "scale(1.4) rotate(180deg)" }, { transform: "scale(1) rotate(360deg)" }], { duration: 900 }),
  }),
};

// ---- play one scene ----------------------------------------------------------------------------------
export async function showScene(e, meta = {}) {
  const build = SCENES[e.stage];
  if (!build) return;
  open();
  const my = ++token, alive = () => my === token;
  const info = STAGE_KID[e.stage] || {};
  const scene = build(e.data || {}, e);
  titleEl.textContent = `${STAGE_ICON[e.stage] || ""} ${info.title || STAGE_LABEL[e.stage] || e.stage}`;
  stepEl.textContent = meta.step || "";
  sceneEl.innerHTML = scene.html;
  kidEl.textContent = scene.kid || info.kid || "";
  techEl.innerHTML = scene.tech ? `<b>Under the hood:</b> ${esc(scene.tech)}` : (STAGE_INFO[e.stage] ? `<b>Under the hood:</b> ${esc(STAGE_INFO[e.stage].what)}` : "");
  if (e.stage === "final") {   // nothing more to approve: offer to close
    btnNext.hidden = btnAll.hidden = true; btnClose.hidden = false; nextEl.textContent = "";
  } else {
    setButtons(false);
  }
  try { await scene.run?.(sceneEl, alive); } catch (err) { console.warn("scene error", e.stage, err); }
}

// The server paused: let the student continue whenever they are ready.
export function setReady(nextText) {
  setButtons(true, nextText);
  btnNext.focus({ preventScroll: true });
}

export function isOpen() { return box && !box.hidden; }
