/* STYLE ATLAS — Fusion Lab
   Mix palette / typography / buttons / motion from DIFFERENT styles into one
   live preview. Submit combos (FX-###) and star-vote them. */
"use strict";

(function () {
  const $ = (id) => document.getElementById(id);
  let catalog = [];
  let byCode = {};
  let sel = { palette: null, type: null, buttons: null, motion: null };
  let combos = [];

  /* ---------- derivations ---------- */
  function pal(e) { return (e && e.palette) || {}; }
  function fonts(e) { return (e && e.fonts) || {}; }
  function tags(e) { return new Set((e && e.tags) || []); }

  function buttonStyle(e) {
    const t = tags(e); const p = pal(e);
    const radius = t.has("rounded") ? 16 : t.has("brutalist") || t.has("sharp") ? 2 : 10;
    let shadow = "none";
    if (t.has("brutalist")) shadow = `4px 4px 0 ${p.ink || "#111"}`;
    else if (t.has("glass") || t.has("glassmorphism")) shadow = "0 10px 26px rgba(120,140,180,.25)";
    else if (t.has("premium") || t.has("luxury")) shadow = "0 6px 18px rgba(0,0,0,.35)";
    const border = t.has("brutalist") ? `2px solid ${p.ink || "#111"}` : "none";
    const weight = t.has("brutalist") ? 800 : 700;
    const transform = t.has("brutalist") ? "uppercase" : "none";
    const ls = t.has("premium") || t.has("editorial") ? "1.5px" : "0";
    return { radius, shadow, border, weight, transform, ls };
  }

  function motionStyle(e) {
    const t = tags(e);
    if (t.has("kinetic") || t.has("animated"))
      return { curve: "cubic-bezier(.34,1.56,.64,1)", dur: "0.35s", fx: "spring" };
    if (t.has("neon"))
      return { curve: "ease", dur: "0.25s", fx: "glow" };
    if (t.has("retro") || t.has("terminal") || t.has("n64"))
      return { curve: "steps(3, jump-none)", dur: "0.24s", fx: "steps" };
    if (t.has("glass") || t.has("glassmorphism"))
      return { curve: "ease", dur: "0.3s", fx: "blur" };
    if (t.has("minimal") || t.has("editorial"))
      return { curve: "ease", dur: "0.15s", fx: "subtle" };
    return { curve: "ease", dur: "0.22s", fx: "plain" };
  }

  /* ---------- helpers ---------- */
  function lum(hex) {
    const h = (hex || "").replace("#", "");
    if (h.length !== 6) return 0.4;
    const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255);
    const f = (c) => (c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  }

  /* ---------- live preview render ---------- */
  function renderPreview() {
    const eP = byCode[sel.palette], eT = byCode[sel.type],
          eB = byCode[sel.buttons], eM = byCode[sel.motion];
    if (!eP) return;
    const p = pal(eP), f = fonts(eT || eP), b = buttonStyle(eB || eP), m = motionStyle(eM || eP);
    const bg = p.bg || "#10141a", surface = p.surface || "#1a2029";
    const ink = p.ink || (lum(bg) < 0.35 ? "#E8ECEA" : "#16191C");
    const accent = p.accent || "#7FB069", accent2 = p.accent2 || accent;
    const muted = ink + "b0";
    const onA = lum(accent) > 0.45 ? "#0B0E0B" : "#fff";
    const display = f.display || "Georgia", body = f.body || "system-ui", mono = f.mono || "monospace";
    const glowFx = m.fx === "glow" ? `box-shadow:0 0 18px ${accent}66;` : "";
    $("fxPreview").innerHTML = `
    <style>
      #fxPreview .fxroot { all: revert; }
    </style>
    <div class="fxroot" style="background:${bg};color:${ink};font-family:'${body}',system-ui;padding:34px 30px;border-radius:14px;
         transition:background ${m.dur} ${m.curve}">
      <div style="font-family:'${mono}',monospace;font-size:10px;letter-spacing:2px;color:${accent};margin-bottom:10px">
        FUSION PREVIEW · ${esc2(eP.code)} palette · ${esc2((eT||eP).code)} type · ${esc2((eB||eP).code)} buttons · ${esc2((eM||eP).code)} motion
      </div>
      <h2 style="font-family:'${display}',Georgia,serif;font-size:34px;margin:0 0 8px">The fused look</h2>
      <p style="color:${muted};max-width:46ch;margin:0 0 20px">Palette from one style, typography from another, buttons and motion from two more — every value below is real, derived from the selected styles' tokens.</p>
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:22px">
        <button class="fxbtn" style="background:${accent};color:${onA};${glowFx}">Primary action</button>
        <button class="fxbtn" style="background:transparent;color:${accent};border:2px solid ${accent}">Secondary</button>
        <button class="fxbtn" style="background:${surface};color:${ink};border:1px solid ${accent2}44">Ghost</button>
      </div>
      <div style="display:flex;gap:10px;flex-wrap:wrap">
        <div class="fxcard" style="background:${surface};flex:1;min-width:120px">
          <b style="font-family:'${display}',Georgia;font-size:26px;color:${accent}">24</b>
          <span style="font-size:10px;letter-spacing:1px;color:${muted}">STAT CARD</span>
        </div>
        <div class="fxcard" style="background:${surface};flex:1;min-width:120px">
          <b style="font-family:'${display}',Georgia;font-size:26px;color:${accent2}">98</b>
          <span style="font-size:10px;letter-spacing:1px;color:${muted}">ANOTHER</span>
        </div>
        <div class="fxcard" style="background:${surface};flex:1;min-width:120px">
          <b style="font-family:'${display}',Georgia;font-size:26px;color:${ink}">Aa</b>
          <span style="font-size:10px;letter-spacing:1px;color:${muted}">${esc2((f.display || "serif").slice(0, 12)).toUpperCase()}</span>
        </div>
      </div>
      <div style="margin-top:22px;display:flex;gap:8px;align-items:center">
        <div class="fxbub" style="background:${surface};border:1px solid ${accent2}44">bubbles too…</div>
        <div class="fxbub" style="background:${accent};color:${onA};margin-left:auto">they move with ${m.fx} motion</div>
      </div>
    </div>
    <style>
      #fxPreview .fxbtn {
        padding: 12px 22px; font-weight: ${b.weight}; font-size: 13px;
        border-radius: ${b.radius}px; border: ${b.border}; box-shadow: ${b.shadow};
        text-transform: ${b.transform}; letter-spacing: ${b.ls}; cursor: pointer;
        font-family: inherit;
        transition: transform ${m.dur} ${m.curve}, box-shadow ${m.dur} ${m.curve},
                    filter ${m.dur} ${m.curve}, opacity ${m.dur} ${m.curve};
      }
      #fxPreview .fxbtn:hover { transform: translateY(-3px) scale(1.04); filter: brightness(1.08); ${m.fx === "glow" ? `box-shadow:0 0 26px ${accent}aa;` : ""} }
      #fxPreview .fxbtn:active { transform: translateY(0) scale(.97); }
      #fxPreview .fxcard {
        padding: 16px; border-radius: ${b.radius}px; box-shadow: ${b.shadow};
        display: flex; flex-direction: column; gap: 3px;
        transition: transform ${m.dur} ${m.curve}, box-shadow ${m.dur} ${m.curve};
      }
      #fxPreview .fxcard:hover { transform: translateY(-4px); }
      #fxPreview .fxbub {
        padding: 9px 14px; border-radius: ${Math.min(b.radius + 4, 20)}px; font-size: 12px;
        transition: transform ${m.dur} ${m.curve};
      }
      #fxPreview .fxbub:hover { transform: scale(1.05); }
      #fxPreview .fxroot > * { animation: fxin ${m.dur} ${m.curve}; }
      @keyframes fxin { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }
    </style>`;
  }

  function esc2(s) { return String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

  /* ---------- selectors ---------- */
  function buildRows() {
    const rows = [
      ["palette", "Palette", (e) => `${e.code} — ${e.name}`],
      ["type", "Typography", (e) => `${e.code} — ${e.name}`],
      ["buttons", "Buttons", (e) => `${e.code} — ${e.name}`],
      ["motion", "Motion", (e) => `${e.code} — ${e.name}`],
    ];
    $("fxRows").innerHTML = rows.map(([k, label]) => `
      <div class="fxrow">
        <label>${label}</label>
        <input list="fxlist-${k}" id="fxin-${k}" placeholder="type a code or name…">
        <datalist id="fxlist-${k}">${catalog.map((e) =>
          `<option value="${e.code}">${esc2(e.name)} · ${esc2(e.project)}</option>`).join("")}
        </datalist>
        <button class="fxrand" data-k="${k}" title="random">⟳</button>
      </div>`).join("") + `
      <div class="fxrow"><label></label>
        <button id="fxShuffle" class="tbtn primary" style="flex:1">🎲 Shuffle all</button>
        <button id="fxSubmit" class="tbtn">⬆ Submit combo</button>
      </div>`;
    rows.forEach(([k]) => {
      const input = $(`fxin-${k}`);
      input.addEventListener("input", () => {
        const v = input.value.trim().toUpperCase();
        if (byCode[v]) { sel[k] = v; renderPreview(); input.classList.remove("bad"); }
        else if (input.value === "") { sel[k] = null; }
        else input.classList.add("bad");
      });
      input.addEventListener("keydown", (ev) => { ev.stopPropagation(); if (ev.key === "Enter") { const v = input.value.trim().toUpperCase(); if (byCode[v]) input.value = v; } });
    });
    $("fxRows").querySelectorAll(".fxrand").forEach((b) =>
      b.onclick = () => { setRow(b.dataset.k, randomCode()); });
    $("fxShuffle").onclick = shuffleAll;
    $("fxSubmit").onclick = submitCombo;
  }

  function randomCode() { return catalog[Math.floor(Math.random() * catalog.length)].code; }
  function setRow(k, code) { sel[k] = code; $(`fxin-${k}`).value = code; renderPreview(); }
  function shuffleAll() { Object.keys(sel).forEach((k) => setRow(k, randomCode())); }

  /* ---------- combos list ---------- */
  function comboCard(c) {
    const eP = byCode[c.parts.palette], eT = byCode[c.parts.type],
          eB = byCode[c.parts.buttons], eM = byCode[c.parts.motion];
    if (!eP) return "";
    const p = pal(eP);
    const strip = [p.bg, p.surface, p.ink, p.accent, p.accent2].filter(Boolean)
      .map((x) => `<div style="background:${x}"></div>`).join("");
    return `<div class="fxcombo" data-code="${c.code}">
      <div class="fxcombo-top">
        <span class="code">${c.code}</span>
        <b>${esc2(c.name || "Untitled fusion")}</b>
        <span style="margin-left:auto">${window.Atlas ? window.Atlas.starsHTML(c.code, true) : ""}</span>
      </div>
      <div class="strip">${strip}</div>
      <div class="fxcombo-parts">
        <span class="chip">🎨 ${esc2(c.parts.palette)}</span>
        <span class="chip">🔤 ${esc2(c.parts.type)}</span>
        <span class="chip">🔘 ${esc2(c.parts.buttons)}</span>
        <span class="chip">✨ ${esc2(c.parts.motion)}</span>
      </div>
      <div class="fxcombo-load">
        <button class="tbtn" data-load="${c.code}">Load into lab</button>
      </div>
    </div>`;
  }

  function renderCombos() {
    $("fxCombos").innerHTML = combos.length
      ? combos.map(comboCard).join("")
      : `<div class="empty" style="grid-column:1/-1"><h3>No combos yet</h3><div>Be the first — mix four styles and hit Submit.</div></div>`;
    $("fxCombos").querySelectorAll("[data-load]").forEach((b) =>
      b.onclick = () => {
        const c = combos.find((x) => x.code === b.dataset.load);
        if (!c) return;
        Object.entries(c.parts).forEach(([k, v]) => setRow(k, v));
        $("fxLab").scrollIntoView({ behavior: "smooth" });
        window.Atlas?.toast(`Loaded ${c.code} into the lab`);
      });
    if (window.Atlas) window.Atlas.bindStarHover?.($("fxCombos"));
  }

  async function refreshCombos() {
    try {
      const r = await fetch("/api/combos");
      const d = await r.json();
      combos = d.combos || [];
      renderCombos();
    } catch { /* offline */ }
  }

  async function submitCombo() {
    if (!sel.palette || !sel.type || !sel.buttons || !sel.motion) {
      window.Atlas?.toast("Pick all four parts first");
      return;
    }
    const name = ($("fxName").value || "").trim() ||
      `${byCode[sel.palette].name} × ${byCode[sel.buttons].name}`;
    try {
      const r = await fetch("/api/combos", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, parts: { ...sel } }),
      });
      const d = await r.json();
      if (d.combo) {
        combos.unshift(d.combo);
        renderCombos();
        $("fxName").value = "";
        window.Atlas?.toast(`Submitted as ${d.combo.code} — star it!`);
      } else window.Atlas?.toast(d.error || "submit failed");
    } catch { window.Atlas?.toast("Could not submit (server offline)"); }
  }

  /* ---------- boot ---------- */
  async function init() {
    try {
      const r = await fetch(window.STATIC_ATLAS ? "/catalog/atlas.json" : "/api/catalog");
      const d = await r.json();
      catalog = d.entries || [];
    } catch { catalog = []; }
    byCode = Object.fromEntries(catalog.map((e) => [e.code, e]));
    buildRows();
    shuffleAll();
    refreshCombos();
  }

  window.FusionUI = { init, refreshCombos, renderCombos };
  if (document.readyState !== "loading") init();
  else document.addEventListener("DOMContentLoaded", init);
})();
