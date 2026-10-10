"use strict";

/* Selecting the area that scrolls. Python freezes the screen; this page
 * draws the rectangle and hands it back when the mouse is released. */

const pending = new Map();
let nextId = 1;
function call(cmd, ...args) {
  const id = nextId++;
  return new Promise((resolve) => {
    pending.set(id, resolve);
    window.webkit.messageHandlers.app.postMessage({ id, cmd, args });
  });
}
const on = {};
window.App = {
  resolve(id, result) { const r = pending.get(id); pending.delete(id); if (r) r(result); },
  emit(name, data) { if (on[name]) on[name](data); },
};

const $ = (s) => document.querySelector(s);
const MIN = 40;           // smaller than this can't hold enough to match steps
let drag = null;

function reset() {
  drag = null;
  document.body.className = "";
  $("#region").hidden = true;
}

function showShot(shot) {
  reset();
  const img = $("#screen");
  img.onload = () => {
    img.style.width = `${shot.width}px`;
    img.style.height = `${shot.height}px`;
    // Decoded and in place: Python can show the window now.
    // (Not requestAnimationFrame: a hidden window never gets frames.)
    call("drawn");
  };
  img.src = shot.url;
}
on.shot = showShot;

function setRegion(r) {
  const el = $("#region");
  Object.assign(el.style, { left: `${r.x}px`, top: `${r.y}px`, width: `${r.w}px`, height: `${r.h}px` });
  $("#size").textContent = `${r.w} × ${r.h}`;
  el.hidden = false;
}

function rect(e) {
  return { x: Math.min(drag.x0, e.clientX), y: Math.min(drag.y0, e.clientY),
           w: Math.abs(e.clientX - drag.x0), h: Math.abs(e.clientY - drag.y0) };
}

document.addEventListener("mousedown", (e) => {
  if (e.button !== 0) return;
  drag = { x0: e.clientX, y0: e.clientY };
  document.body.classList.add("selecting");
  setRegion({ x: e.clientX, y: e.clientY, w: 0, h: 0 });
  e.preventDefault();
});

document.addEventListener("mousemove", (e) => {
  if (drag) setRegion(rect(e));
});

document.addEventListener("mouseup", (e) => {
  if (!drag || e.button !== 0) return;
  const r = rect(e);
  drag = null;
  if (r.w < MIN || r.h < MIN) { reset(); return; }
  reset();
  call("start", r.x, r.y, r.w, r.h);
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { e.preventDefault(); reset(); call("close"); }
});

(async () => {
  const first = await call("ready");
  if (first) showShot(first);
})();
