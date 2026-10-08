// space3d.js - the 3D "embedding space" view (Three.js).
//
// Every chunk is a sphere placed by a PCA projection of its 384-D embedding
// (computed on the server, see app/retrieval/vector_map.py). When a search runs:
//   * each query (or MQE variant / HyDE passage) appears as a glowing diamond,
//   * lines connect it to its nearest dense hits,
//   * BM25 hits get an amber halo, the final top-4 grow and turn gold.
// Drag to rotate; hover a sphere to read its chunk.

import { DEPT_COLOR } from "./explain.js";

const THREE = window.THREE;
let scene, camera, renderer, root, container, tooltip;
let spheres = new Map();      // chunk id -> mesh
let overlay = [];             // query markers + lines, cleared per search
let extras = [];              // spheres for hits outside the sampled map (big knowledge bases)
let dragging = false, lastX = 0, lastY = 0, autoSpin = true;
const raycaster = new THREE.Raycaster();
const mouse = new THREE.Vector2();
const SCALE = 3.2;            // PCA coords are -1..1; spread them out a little

export function init3D(el, tip) {
  container = el;
  tooltip = tip;
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(45, el.clientWidth / el.clientHeight, 0.1, 100);
  camera.position.set(0, 1.2, 9);
  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(el.clientWidth, el.clientHeight);
  el.appendChild(renderer.domElement);

  scene.add(new THREE.AmbientLight(0xffffff, 0.75));
  const sun = new THREE.DirectionalLight(0xffffff, 0.8);
  sun.position.set(4, 6, 8);
  scene.add(sun);

  root = new THREE.Group();
  scene.add(root);
  // A faint wire cube shows the boundaries of the projected space.
  const cube = new THREE.LineSegments(
    new THREE.EdgesGeometry(new THREE.BoxGeometry(SCALE * 2.1, SCALE * 2.1, SCALE * 2.1)),
    new THREE.LineBasicMaterial({ color: 0xc7d2fe, transparent: true, opacity: 0.55 }));
  root.add(cube);

  // Drag to rotate, hover for a tooltip.
  el.addEventListener("pointerdown", (e) => { dragging = true; autoSpin = false; lastX = e.clientX; lastY = e.clientY; });
  window.addEventListener("pointerup", () => (dragging = false));
  el.addEventListener("pointermove", onMove);
  el.addEventListener("pointerleave", () => (tooltip.style.display = "none"));
  new ResizeObserver(resize).observe(el);
  animate();
}

function resize() {
  if (!container.clientWidth) return;
  camera.aspect = container.clientWidth / container.clientHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(container.clientWidth, container.clientHeight);
}

function onMove(e) {
  if (dragging) {
    root.rotation.y += (e.clientX - lastX) * 0.008;
    root.rotation.x += (e.clientY - lastY) * 0.008;
    lastX = e.clientX; lastY = e.clientY;
    return;
  }
  const rect = renderer.domElement.getBoundingClientRect();
  mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
  mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(mouse, camera);
  const hit = raycaster.intersectObjects([...spheres.values(), ...overlay.filter((o) => o.userData.label)])[0];
  if (hit) {
    const d = hit.object.userData;
    tooltip.innerHTML = d.label
      ? `<b>${escapeHtml(d.label)}</b><br>${escapeHtml(d.text || "")}`
      : `<b>${escapeHtml(d.source)} #${d.chunk_index}</b> · ${d.department}<br>${escapeHtml(d.text)}`;
    tooltip.style.display = "block";
    tooltip.style.left = `${e.clientX - rect.left + 14}px`;
    tooltip.style.top = `${e.clientY - rect.top + 14}px`;
  } else {
    tooltip.style.display = "none";
  }
}

function animate() {
  requestAnimationFrame(animate);
  if (autoSpin) root.rotation.y += 0.0025;
  const t = performance.now() / 400;
  overlay.forEach((o) => { if (o.userData.pulse) o.scale.setScalar(1 + 0.15 * Math.sin(t)); });
  renderer.render(scene, camera);
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

const v = (p) => new THREE.Vector3(p[0] * SCALE, p[1] * SCALE, p[2] * SCALE);

// ---- public API ------------------------------------------------------------------
export function setPoints(points) {
  spheres.forEach((m) => root.remove(m));
  spheres = new Map();
  clearSearch();
  const geo = new THREE.SphereGeometry(0.11, 24, 24);
  points.forEach((p) => {
    const mat = new THREE.MeshStandardMaterial({ color: DEPT_COLOR[p.department] || "#64748b", roughness: 0.35, metalness: 0.1 });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.copy(v([p.x, p.y, p.z]));
    mesh.userData = p;
    root.add(mesh);
    spheres.set(p.id, mesh);
  });
}

export function clearSearch() {
  overlay.forEach((o) => root.remove(o));
  overlay = [];
  extras.forEach((m) => { root.remove(m); spheres.delete(m.userData.id); });
  extras = [];
  spheres.forEach((m) => {
    m.scale.setScalar(1);
    m.material.color.set(DEPT_COLOR[m.userData.department] || "#64748b");
    m.material.emissive.set(0x000000);
    m.material.opacity = 1; m.material.transparent = false;
  });
}

const QUERY_COLORS = [0x4f46e5, 0x0891b2, 0xdb2777, 0x16a34a, 0xea580c];

// Dense stage: draw each query point and connect it to its top-5 dense hits.
export function showDense(queryPoints, lists, hitPoints = {}) {
  const listValues = Object.values(lists);
  // A hit that is not in the sampled map gets its own sphere at its projected position.
  Object.values(lists).flat().forEach((h) => {
    const xyz = hitPoints[h.id];
    if (spheres.has(h.id) || !xyz) return;
    const m = new THREE.Mesh(new THREE.SphereGeometry(0.11, 24, 24),
      new THREE.MeshStandardMaterial({ color: DEPT_COLOR[h.department] || "#64748b", roughness: 0.35 }));
    m.position.copy(v(xyz));
    m.userData = { id: h.id, source: h.source, chunk_index: h.chunk_index, department: h.department, text: h.text.slice(0, 160) };
    root.add(m); spheres.set(h.id, m); extras.push(m);
  });
  queryPoints.forEach((q, i) => {
    const color = q.label === "original question" ? 0x94a3b8 : QUERY_COLORS[i % QUERY_COLORS.length];
    const marker = new THREE.Mesh(new THREE.OctahedronGeometry(0.2),
      new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 0.45 }));
    marker.position.copy(v(q.xyz));
    marker.userData = { label: q.label, pulse: true, text: "query position in embedding space" };
    root.add(marker); overlay.push(marker);
    const hits = (listValues[i] || []).slice(0, 5);
    hits.forEach((h) => {
      const target = spheres.get(h.id);
      if (!target) return;
      const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints([marker.position, target.position]),
        new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.7 }));
      root.add(line); overlay.push(line);
      target.scale.setScalar(1.35);
    });
  });
}

// BM25 stage: amber halo around every chunk that shared a keyword.
export function showBm25(ids) {
  ids.forEach((id) => {
    const target = spheres.get(id);
    if (!target) return;
    const halo = new THREE.Mesh(new THREE.TorusGeometry(0.2, 0.025, 8, 32),
      new THREE.MeshBasicMaterial({ color: 0xf59e0b }));
    halo.position.copy(target.position);
    halo.lookAt(camera.position);
    root.add(halo); overlay.push(halo);
  });
}

// Re-rank stage: fade everything except the final top chunks, which turn gold.
export function showFinal(ids) {
  spheres.forEach((m, id) => {
    if (ids.includes(id)) {
      m.scale.setScalar(1.9);
      m.material.emissive.set(0xf59e0b);
      m.material.emissiveIntensity = 0.55;
    } else {
      m.material.transparent = true;
      m.material.opacity = 0.28;
    }
  });
}
