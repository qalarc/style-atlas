/* STYLE ATLAS — hub application
   Gallery · filters · collections · picks · theater with arrow-key cycling */
"use strict";

const S = {
  catalog: [],
  byCode: {},
  picks: [],
  pickSet: new Set(),
  ratings: {},                     // code -> {s: sum, c: count}
  myVotes: {},                     // code -> stars (localStorage)
  views: {},                       // code -> count
  filters: {
    categories: new Set(), projects: new Set(), modes: new Set(),
    hues: new Set(), statuses: new Set(), tags: new Set(), search: "",
  },
  codesFilter: null,          // explicit code list from chatbot
  sort: "code",
  view: "gallery",
  filtered: [],
  focusIdx: -1,
  theaterIdx: -1,
  thumbsTried: new Set(),
};

const $ = (id) => document.getElementById(id);
const grid = $("grid");

/* ---------------- utils ---------------- */
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
function toast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(t._to);
  t._to = setTimeout(() => t.classList.remove("show"), 2200);
}
function copyText(txt, what) {
  navigator.clipboard?.writeText(txt).then(
    () => toast(`Copied ${what || "to clipboard"}`),
    () => toast(txt));
}
function avgRating(code) {
  const r = S.ratings[code];
  return r && r.c ? r.s / r.c : 0;
}
function starsHTML(code, interactive) {
  const avg = avgRating(code);
  const n = (S.ratings[code] || {}).c || 0;
  const mine = S.myVotes[code];
  const show = interactive && mine ? mine : Math.round(avg * 2) / 2;
  let out = '<span class="stars' + (interactive ? ' rate' : '') + '" data-code="' + esc(code) + '" title="' +
    (n ? avg.toFixed(1) + '\u2605 from ' + n + ' vote' + (n > 1 ? 's' : '') : 'no votes yet') + '">';
  for (let i = 1; i <= 5; i++) {
    const cls = show >= i ? "full" : show >= i - 0.5 ? "half" : "";
    out += '<i data-stars="' + i + '" class="' + cls + '">\u2605</i>';
  }
  out += '</span><span class="votes-n">' + (n ? avg.toFixed(1) + " (" + n + ")" : "\u2014") + "</span>";
  return out;
}
/* hover fills RIGHT to LEFT: pointing at a star lights it and everything right of it */
function bindStarHover(container) {
  container.querySelectorAll(".stars.rate").forEach((wrap) => {
    if (wrap._rtl) return;
    wrap._rtl = true;
    const stars = [...wrap.querySelectorAll("i")];
    stars.forEach((st) => {
      st.addEventListener("mouseenter", () => {
        const v = +st.dataset.stars;
        stars.forEach((s2) => s2.classList.toggle("pre", +s2.dataset.stars >= v));
      });
    });
    wrap.addEventListener("mouseleave", () =>
      stars.forEach((s2) => s2.classList.remove("pre")));
  });
}
async function castVote(code, stars) {
  S.myVotes[code] = stars;
  localStorage.setItem("atlas.votes", JSON.stringify(S.myVotes));
  try {
    const r = await fetch("/api/rate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, stars }),
    });
    const d = await r.json();
    if (d.ratings) S.ratings = d.ratings;
  } catch {
    toast("Vote saved locally (server offline)");
  }
  renderGrid();
  if (S.theaterIdx >= 0 && S.filtered[S.theaterIdx]?.code === code) renderTheaterMeta();
}
function hexToHsl(hex) {
  const h = (hex || "").replace("#", "");
  if (!/^[0-9a-fA-F]{3,6}$/.test(h)) return null;
  const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  const r = parseInt(full.slice(0, 2), 16) / 255,
        g = parseInt(full.slice(2, 4), 16) / 255,
        b = parseInt(full.slice(4, 6), 16) / 255;
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn;
  let hue = 0;
  if (d) {
    if (mx === r) hue = ((g - b) / d) % 6;
    else if (mx === g) hue = (b - r) / d + 2;
    else hue = (r - g) / d + 4;
    hue *= 60; if (hue < 0) hue += 360;
  }
  const light = (mx + mn) / 2;
  const sat = d ? d / (1 - Math.abs(2 * light - 1)) : 0;
  return { h: hue, s: sat, l: light };
}
const HUE_BUCKETS = [
  ["red", 0, 15], ["orange", 15, 40], ["amber", 40, 65], ["yellow", 65, 80],
  ["green", 80, 160], ["teal", 160, 195], ["cyan", 195, 215], ["blue", 215, 255],
  ["indigo", 255, 285], ["purple", 285, 320], ["pink", 320, 345], ["red", 345, 361],
];
function hueFamily(entry) {
  const pal = entry.palette || {};
  const hex = pal.accent || pal.accent2 || pal.bg;
  const hsl = hexToHsl(hex);
  if (!hsl) return "neutral";
  if (hsl.s < 0.16 || hsl.l > 0.94 || hsl.l < 0.06) return "neutral";
  for (const [name, lo, hi] of HUE_BUCKETS) {
    if (hsl.h >= lo && hsl.h < hi) return name === "red" ? "red" : name;
  }
  return "neutral";
}
function paletteArray(e) {
  const p = e.palette || {};
  return [p.bg, p.surface, p.ink, p.accent, p.accent2, ...(p.extra || [])]
    .filter(Boolean).slice(0, 7);
}
const PROJECT_SITES = {
  "tradez.au": "https://tradez.au",
  "x10.au": "https://x10.au",
  "x10.au (biz)": "https://x10.au",
  "gmux.ai": "https://gmux.ai",
  "gmux app": "https://gmux.ai",
  "gmux systems": "https://gmux.ai",
  "endispute": "https://endispute.com.au",
  "reps_with_friends": "https://rwf.qalarc.com",
  "qalarc.ai": "https://qalarc.ai",
  "volkus.net": "https://volkus.net",
  "chanalyse (monitor)": "https://chanalyse.org",
};
function projectSite(e) {
  return PROJECT_SITES[e.project] || null;
}
function trackedOut(code, url) {
  return `/out/${encodeURIComponent(code)}?to=${encodeURIComponent(url)}`;
}
function hasMount(e) { return !!(e.mount && e.mount.dir && e.mount.file); }
function previewUrl(e) {
  if (hasMount(e)) {
    let u = `/${e.code}/`;
    if (e.category === "hero-module" && e.nativeId) u += `#${e.nativeId}`;
    return u;
  }
  if (e.externalUrl) return e.externalUrl;
  return `/swatch/${e.code}/`;
}
function fontStack(e, which) {
  const f = (e.fonts || {})[which] || (e.fonts || {}).body || "";
  return f ? `"${f}", ` : "";
}

/* ---------------- mock preview (when no screenshot yet) ---------------- */
function mockHTML(e) {
  const p = e.palette || {};
  const bg = p.bg || "#101418", ink = p.ink || "#E8ECEA",
        accent = p.accent || "#7FB069", accent2 = p.accent2 || accent,
        surface = p.surface || "#1A2027";
  const onAccent = "#0B0E0B";
  const dis = fontStack(e, "display"), bod = fontStack(e, "body");
  const cat = e.category;
  const kicker = `<div class="mk" style="color:${accent};font-family:${fontStack(e, "mono")}monospace">${esc((e.project || "").toUpperCase())}</div>`;
  const title = `<div class="mt two" style="color:${ink};font-family:${dis}Georgia,serif">${esc(e.name)}</div>`;

  if (cat === "chat-app") {
    return `<div class="mock" style="background:${bg}">
      ${kicker}
      <div class="bub" style="background:${surface};color:${ink};align-self:flex-start;border:1px solid ${accent2}33">hey — quick question about the design system</div>
      <div class="bub me" style="background:${accent};color:${onAccent};align-self:flex-end">this palette answers it</div>
      <div class="bub" style="background:${surface};color:${ink};align-self:flex-start;border:1px solid ${accent2}33">typing…</div>
      <div style="margin-top:auto;display:flex;gap:6px">
        <div style="flex:1;border:1px solid ${accent2}44;border-radius:99px;height:24px"></div>
        <div style="width:24px;height:24px;border-radius:50%;background:${accent}"></div>
      </div></div>`;
  }
  if (cat === "dashboard") {
    return `<div class="mock" style="background:${bg}">${kicker}
      <div class="row">${title}</div>
      <div class="row" style="margin-top:4px">
        <div class="stat" style="background:${surface};border:1px solid ${accent2}33"><b style="color:${accent};font-family:${dis}Georgia">+41%</b><span style="color:${ink}99">MOOD</span></div>
        <div class="stat" style="background:${surface};border:1px solid ${accent2}33"><b style="color:${ink};font-family:${dis}Georgia">912</b><span style="color:${ink}99">STYLES</span></div>
        <div class="stat" style="background:${surface};border:1px solid ${accent2}33"><b style="color:${accent2};font-family:${dis}Georgia">0.9</b><span style="color:${ink}99">SCORE</span></div>
      </div>
      <div class="hud" style="background:${surface};margin-top:2px"><div class="hud" style="width:64%;background:${accent}"></div></div>
      <div class="hud" style="background:${surface}"><div class="hud" style="width:38%;background:${accent2}"></div></div>
    </div>`;
  }
  if (cat === "game") {
    return `<div class="mock" style="background:${bg}">
      <div class="row" style="justify-content:space-between">
        <div class="mono-mark" style="background:${accent};color:${onAccent};font-family:${dis}Georgia">${esc((e.name || "?")[0])}</div>
        <div style="text-align:right">
          <div style="color:${ink};font-weight:800;font-size:15px;font-family:${bod}system-ui">SCORE 4210</div>
          <div style="color:${ink}99;font-size:10px;font-family:${fontStack(e, "mono")}monospace">LEVEL 3</div>
        </div></div>
      <div class="hud" style="background:${surface}"><div class="hud" style="width:78%;background:${accent}"></div></div>
      <div class="hud" style="background:${surface}"><div class="hud" style="width:52%;background:${accent2}"></div></div>
      <div class="row" style="margin-top:auto;gap:8px">
        <div class="btn" style="background:${accent};color:${onAccent}">▶ PLAY</div>
        <div class="btn" style="background:transparent;border:1.5px solid ${accent2};color:${ink}">SHOP</div>
      </div></div>`;
  }
  if (cat === "logo") {
    return `<div class="mock" style="background:${bg};align-items:center;justify-content:center">
      <div class="mono-mark" style="background:${surface};color:${accent};width:74px;height:74px;font-size:30px;border:1.5px solid ${accent2}55;font-family:${dis}Georgia">
        ${esc((e.name || "?").replace(/[^A-Za-z0-9]/g, "").slice(0, 2).toUpperCase() || "?")}</div>
      <div class="mt" style="color:${ink};font-family:${dis}Georgia,serif;margin-top:10px">${esc(e.name)}</div>
      <div class="mk" style="color:${accent2}">MARK · ${esc(e.project)}</div></div>`;
  }
  if (cat === "terminal") {
    return `<div class="mock" style="background:${bg};font-family:${fontStack(e, "mono")}monospace">
      <div style="color:${accent}">~/atlas $ list --category=${esc(cat)}</div>
      <div style="color:${ink}99">→ ${esc(e.code)} loaded</div>
      <div style="color:${accent2}">→ tokens OK ▮</div>
      <div style="margin-top:auto;color:${accent}">~/atlas $ <span style="border-bottom:2px solid ${accent}">&nbsp;</span></div>
    </div>`;
  }
  /* website / landing / directory / hero-module / default */
  return `<div class="mock" style="background:${bg}">
    ${kicker}${title}
    <div class="btn" style="background:${accent};color:${onAccent}">Get started</div>
    <div class="row" style="margin-top:auto;gap:8px">
      <div class="btn" style="background:${surface};border:1px solid ${accent2}44;color:${ink}">Browse</div>
      <div class="btn" style="background:transparent;border:1.5px solid ${accent2};color:${ink}">Contact</div>
    </div></div>`;
}

/* ---------------- data load ---------------- */
async function boot() {
  try {
    const r = await fetch("/api/catalog");
    const cat = await r.json();
    S.catalog = cat.entries || [];
  } catch {
    S.catalog = [];
  }
  S.catalog.forEach((e) => {
    S.byCode[e.code] = e;
    e._hue = hueFamily(e);
    e._pal = paletteArray(e);
  });
  try {
    const r = await fetch("/api/picks");
    const p = await r.json();
    S.picks = p.picks || [];
    S.pickSet = new Set(S.picks.map((x) => x.code));
  } catch { /* no picks yet */ }
  try {
    const r = await fetch("/api/ratings");
    const d = await r.json();
    S.ratings = d.ratings || {};
  } catch { S.ratings = {}; }
  try { S.myVotes = JSON.parse(localStorage.getItem("atlas.votes") || "{}"); }
  catch { S.myVotes = {}; }
  try {
    const r = await fetch("/api/views");
    S.views = (await r.json()).views || {};
  } catch { S.views = {}; }
  buildSidebar();
  renderPickCount();
  const m = location.hash.match(/^#([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*)$/);
  const projLink = sessionStorage.getItem("atlas.project");
  if (projLink) {
    sessionStorage.removeItem("atlas.project");
    if (S.catalog.some((e) => e.project === projLink)) {
      S.filters.projects = new Set([projLink]);
      buildSidebar();
    }
  }
  if (m && S.byCode[m[1]]) {
    apply();
    openTheaterByCode(m[1]);
  } else {
    apply();
  }
  $("brandSub").textContent =
    `${S.catalog.length} styles · ${new Set(S.catalog.map((e) => e.project)).size} projects`;
  if (!S.catalog.length) {
    grid.innerHTML = `<div class="empty"><h3>Catalog is building…</h3>
      <div class="mono">run scripts/merge_catalog.py when scans finish</div></div>`;
  }
}

/* ---------------- filtering + sorting ---------------- */
function apply() {
  const f = S.filters;
  const q = f.search.trim().toLowerCase();
  let list = S.catalog.filter((e) => {
    if (S.codesFilter) return S.codesFilter.has(e.code);
    if (f.categories.size && !f.categories.has(e.category)) return false;
    if (f.projects.size && !f.projects.has(e.project)) return false;
    if (f.modes.size && !f.modes.has(e.mode)) return false;
    if (f.hues.size && !f.hues.has(e._hue)) return false;
    if (f.statuses.size && !f.statuses.has(e.status)) return false;
    if (f.tags.size && !(e.tags || []).some((t) => f.tags.has(t))) return false;
    if (q) {
      const hay = [e.code, e.name, e.project, e.category, e.description,
        ...(e.tags || []), ...(e._pal || [])].join(" ").toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  const cmp = {
    code: (a, b) => a.code.localeCompare(b.code),
    name: (a, b) => (a.name || "").localeCompare(b.name || ""),
    project: (a, b) => a.project.localeCompare(b.project) || a.code.localeCompare(b.code),
    category: (a, b) => a.category.localeCompare(b.category) || a.code.localeCompare(b.code),
    mode: (a, b) => (a.mode || "").localeCompare(b.mode || "") || a.code.localeCompare(b.code),
    hue: (a, b) => a._hue.localeCompare(b._hue) || a.code.localeCompare(b.code),
    era: (a, b) => (b.era || "").localeCompare(a.era || "") || a.code.localeCompare(b.code),
    rating: (a, b) => (avgRating(b.code) - avgRating(a.code)) ||
      ((S.ratings[b.code] || {}).c || 0) - ((S.ratings[a.code] || {}).c || 0) ||
      a.code.localeCompare(b.code),
  }[S.sort];
  list.sort(cmp);
  S.filtered = list;
  S.focusIdx = list.length ? 0 : -1;
  renderGrid();
}

/* ---------------- grid ---------------- */
function cardHTML(e, i) {
  const pal = e._pal && e._pal.length ? e._pal : ["#2A313A", "#3A434F", "#E8ECEA", "#7FB069"];
  const strip = pal.slice(0, 6).map((c) => `<div style="background:${esc(c)}" title="${esc(c)}"></div>`).join("");
  const tags = (e.tags || []).slice(0, 3).map((t) => `<span class="chip">${esc(t)}</span>`).join("");
  const starred = S.pickSet.has(e.code);
  return `<div class="card" data-i="${i}" data-code="${esc(e.code)}" id="card-${i}">
    <div class="shot">${mockHTML(e)}
      <img loading="lazy" src="/thumbs/${esc(e.code)}.png" alt=""
           onload="this.style.opacity=1" style="position:absolute;inset:0;opacity:0;transition:opacity .3s"
           onerror="this.remove()">
    </div>
    <div class="strip">${strip}</div>
    <div class="meta">
      <div class="r1">
        <span class="code">${esc(e.code)}</span>
        <span class="name">${esc(e.name)}</span>
        <span class="mode-dot ${esc(e.mode || "")}" title="${esc(e.mode || "?")}"></span>
      </div>
      <div class="r2">
        <span class="chip cat">${esc(e.category)}</span>
        <span class="chip">${esc(e.project)}</span>
        ${tags}
      </div>
      <div class="r3">${starsHTML(e.code, false)}</div>
    </div>
    ${e.status && e.status !== "candidate" ? `<span class="status-rib ${esc(e.status)}">${esc(e.status.toUpperCase())}</span>` : ""}
    <button class="star ${starred ? "on" : ""}" data-code="${esc(e.code)}" title="Star (S)">${starred ? "★" : "☆"}</button>
  </div>`;
}

function renderGrid() {
  if (S.view !== "gallery") return;
  $("collections").style.display = "none";
  $("picksWrap").style.display = "none";
  grid.style.display = "grid";
  if (!S.filtered.length) {
    grid.innerHTML = `<div class="empty"><h3>No styles match</h3>
      <div>Loosen the filters or ask the Concierge ✦</div></div>`;
  } else {
    grid.innerHTML = S.filtered.map((e, i) => cardHTML(e, i)).join("");
  }
  $("count").innerHTML = `<b>${S.filtered.length}</b> / ${S.catalog.length} styles`;
  focusCard(S.focusIdx, false);
}

function focusCard(i, scroll = true) {
  S.focusIdx = i;
  document.querySelectorAll(".card.focus").forEach((c) => c.classList.remove("focus"));
  if (i < 0) return;
  const el = $(`card-${i}`);
  if (el) {
    el.classList.add("focus");
    if (scroll) el.scrollIntoView({ block: "nearest", inline: "nearest" });
  }
}

/* ---------------- sidebar ---------------- */
function buildSidebar() {
  const counts = (key) => {
    const m = new Map();
    S.catalog.forEach((e) => {
      const v = typeof key === "function" ? key(e) : e[key];
      if (v) m.set(v, (m.get(v) || 0) + 1);
    });
    return [...m.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  };
  const mkGroup = (gid, setKey, entries, colors) => {
    const g = $(gid);
    const h = g.querySelector("h4");
    if (!h.querySelector(".clr")) {
      const b = document.createElement("button");
      b.className = "clr"; b.textContent = "reset";
      b.onclick = () => { S.filters[setKey].clear(); buildSidebar(); apply(); };
      h.appendChild(b);
    }
    g.querySelectorAll(".fitem").forEach((x) => x.remove());
    entries.forEach(([val, n]) => {
      const d = document.createElement("div");
      d.className = "fitem" + (S.filters[setKey].has(val) ? " on" : "");
      const color = colors ? colors[val] : null;
      d.innerHTML = `<span class="dot" style="${color ? `background:${color}` : ""}"></span>
        ${esc(val)}<span class="n">${n}</span>`;
      d.onclick = () => {
        const s = S.filters[setKey];
        s.has(val) ? s.delete(val) : s.add(val);
        S.codesFilter = null;
        d.classList.toggle("on");
        apply();
      };
      g.appendChild(d);
    });
  };
  mkGroup("fgCategory", "categories", counts("category"));
  mkGroup("fgProject", "projects", counts("project"));
  mkGroup("fgMode", "modes", counts("mode"), {
    dark: "#333940", light: "#E9EDF1", both: "linear-gradient(90deg,#E9EDF1 50%,#444 50%)",
  });
  mkGroup("fgHue", "hues", counts((e) => e._hue), {
    red: "#D96A6A", orange: "#D98E5A", amber: "#C9A24E", yellow: "#D9C95A",
    green: "#7FB069", teal: "#6ABFAE", cyan: "#6AC3D9", blue: "#6AA6D9",
    indigo: "#7A8AD9", purple: "#A77FD9", pink: "#D97AB8", neutral: "#8B95A0",
  });
  mkGroup("fgStatus", "statuses", counts("status"), {
    candidate: "#8B95A0", final: "#7FB069", shipped: "#6AA6D9", rejected: "#D96A6A",
  });

  /* tag cloud: top 34 tags */
  const tm = new Map();
  S.catalog.forEach((e) => (e.tags || []).forEach((t) => tm.set(t, (tm.get(t) || 0) + 1)));
  const top = [...tm.entries()].sort((a, b) => b[1] - a[1]).slice(0, 34);
  const cloud = $("tagCloud");
  cloud.innerHTML = "";
  top.forEach(([t, n]) => {
    const s = document.createElement("span");
    s.className = "tag" + (S.filters.tags.has(t) ? " on" : "");
    s.textContent = `${t} ${n}`;
    s.onclick = () => {
      S.filters.tags.has(t) ? S.filters.tags.delete(t) : S.filters.tags.add(t);
      S.codesFilter = null;
      s.classList.toggle("on");
      apply();
    };
    cloud.appendChild(s);
  });
}

/* ---------------- collections view ---------------- */
function renderCollections() {
  const byProject = new Map();
  S.catalog.forEach((e) => {
    if (!byProject.has(e.project)) byProject.set(e.project, []);
    byProject.get(e.project).push(e);
  });
  const projects = [...byProject.entries()].sort((a, b) => b[1].length - a[1].length);
  $("collections").innerHTML = projects.map(([proj, entries]) => {
    const pal = [];
    entries.forEach((e) => (e._pal || []).slice(0, 2).forEach((c) => {
      if (pal.length < 7 && !pal.includes(c)) pal.push(c);
    }));
    const cats = [...new Set(entries.map((e) => e.category))].slice(0, 6);
    return `<div class="coll" data-proj="${esc(proj)}">
      <div class="pal">${pal.map((c) => `<div style="background:${esc(c)}"></div>`).join("")}</div>
      <h3>${esc(proj)} <span style="color:var(--faint);font-weight:400;font-size:13px">${entries.length}</span></h3>
      <div class="sub">${[...new Set(entries.map((e) => e.prefix))].join(" · ")} prefixes · ${entries.filter((e) => hasMount(e)).length} live-previewable</div>
      <div class="cats">${cats.map((c) => `<span class="chip cat">${esc(c)}</span>`).join("")}</div>
    </div>`;
  }).join("");
  document.querySelectorAll(".coll").forEach((el) => {
    el.onclick = () => {
      S.filters.projects = new Set([el.dataset.proj]);
      S.codesFilter = null;
      buildSidebar();
      setView("gallery");
      apply();
      toast(`Filtered to ${el.dataset.proj}`);
    };
  });
}

/* ---------------- picks view ---------------- */
function renderPickCount() {
  $("pickCount").textContent = S.pickSet.size ? `(${S.pickSet.size})` : "";
}
function renderPicks() {
  const wrap = $("picksWrap");
  if (!S.picks.length) {
    wrap.innerHTML = `<div class="empty"><h3>No picks yet</h3>
      <div>Star styles with <kbd>S</kbd> or the ☆ button to build a shortlist</div></div>`;
    return;
  }
  wrap.innerHTML = S.picks.map((p) => {
    const e = S.byCode[p.code];
    if (!e) return "";
    const pal = (e._pal || []).slice(0, 6);
    return `<div class="pickrow" data-code="${esc(p.code)}">
      <div class="strip">${pal.map((c) => `<div style="background:${esc(c)}"></div>`).join("")}</div>
      <div class="info">
        <div class="r1"><span class="code">${esc(e.code)}</span>
          <b style="font-size:14px">${esc(e.name)}</b>
          <span class="chip cat">${esc(e.category)}</span>
          <span class="chip">${esc(e.project)}</span>
          <span class="chip">hue: ${esc(e._hue)}</span></div>
        <div style="color:var(--muted);font-size:12.5px;margin-top:5px">${esc(e.description || "")}</div>
        <div class="note"><textarea rows="2" placeholder="note…">${esc(p.note || "")}</textarea></div>
      </div>
      <div style="display:flex;flex-direction:column;gap:6px">
        <button class="tbtn" data-open="${esc(e.code)}">View</button>
        <button class="tbtn" data-unstar="${esc(e.code)}" style="color:var(--red)">Remove</button>
      </div>
    </div>`;
  }).join("");
  wrap.querySelectorAll("textarea").forEach((ta) => {
    ta.addEventListener("blur", () => {
      const code = ta.closest(".pickrow").dataset.code;
      apiPick("note", code, ta.value);
    });
  });
  wrap.querySelectorAll("[data-open]").forEach((b) =>
    b.onclick = () => { openTheaterByCode(b.dataset.open); });
  wrap.querySelectorAll("[data-unstar]").forEach((b) =>
    b.onclick = () => toggleStar(b.dataset.unstar, false));
}

/* ---------------- star / picks ---------------- */
async function apiPick(action, code, note = "") {
  try {
    const r = await fetch("/api/picks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, code, note }),
    });
    const p = await r.json();
    S.picks = p.picks || [];
    S.pickSet = new Set(S.picks.map((x) => x.code));
    renderPickCount();
    if (S.view === "picks") renderPicks();
    return true;
  } catch { toast("Could not save pick (server offline?)"); return false; }
}
async function toggleStar(code, force) {
  const e = S.byCode[code];
  if (!e) return;
  const want = force !== undefined ? force : !S.pickSet.has(code);
  await apiPick(want ? "add" : "remove", code);
  document.querySelectorAll(`.star[data-code="${code}"]`).forEach((b) => {
    b.classList.toggle("on", want);
    b.textContent = want ? "★" : "☆";
  });
  if (S.theaterIdx >= 0) renderTheaterMeta();
  toast(want ? `★ ${code} added to picks` : `${code} removed`);
}

/* ---------------- theater ---------------- */
function recordView(code) {
  try {
    const k = "atlas.seen." + code;
    if (sessionStorage.getItem(k)) return;   // once per session per style
    sessionStorage.setItem(k, "1");
  } catch {}
  fetch("/api/view", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
    keepalive: true,
  }).then((r) => r.ok ? r.json() : null)
    .then((d) => { if (d && d.views) S.views = d.views; })
    .catch(() => {});
}

function openTheater(i) {
  if (i < 0 || i >= S.filtered.length) return;
  S.theaterIdx = i;
  $("theater").classList.add("open");
  engageShield();
  recordView(S.filtered[i].code);
  const e = S.filtered[i];
  history.replaceState(null, "", `#${e.code}`);
  const url = previewUrl(e);
  const ext = !!e.externalUrl && !hasMount(e);
  if (ext) {
    $("tFrame").style.display = "none";
    $("tExt").style.display = "grid";
    $("tExtLink").href = e.externalUrl;
    $("tExt").querySelector("p").textContent = `${e.name} — external site (${e.externalUrl})`;
  } else {
    $("tFrame").style.display = "block";
    $("tExt").style.display = "none";
    $("tFrame").src = url;
  }
  renderTheaterMeta();
}
function openTheaterByCode(code) {
  const i = S.filtered.findIndex((e) => e.code === code);
  if (i >= 0) openTheater(i);
  else toast(`${code} not in current filter`);
}
function navTheater(dir) {
  const n = S.filtered.length;
  if (!n) return;
  openTheater(((S.theaterIdx + dir) % n + n) % n);
}
/* iframe-focus shield: while visible, the page keeps keyboard focus so
   ←/→ always cycle; click the shield once to interact with the preview. */
function engageShield() {
  const sh = $("tShield");
  if (!sh) return;
  sh.style.display = "grid";
  try { document.activeElement && document.activeElement.blur(); } catch {}
  document.body.focus && document.body.focus();
}
$("tShield") && ($("tShield").onclick = () => { $("tShield").style.display = "none"; });
function closeTheater() {
  $("theater").classList.remove("open");
  $("tFrame").src = "about:blank";
  history.replaceState(null, "", location.pathname);
  S.theaterIdx = -1;
}
function renderTheaterMeta() {
  const e = S.filtered[S.theaterIdx];
  if (!e) return;
  const pal = e._pal || [];
  const fonts = e.fonts || {};
  const fline = ["display", "body", "mono"].filter((k) => fonts[k])
    .map((k) => `<div class="kv"><b>${k}</b><span>${esc(fonts[k])}</span></div>`).join("");
  $("tPanel").innerHTML = `
    <div class="bigcode">${esc(e.code)}</div>
    <div id="tViews"></div><div id="tLinks"></div>
    <h2>${esc(e.name)}</h2>
    <div class="proj">${esc(e.project)} · ${esc(e.category)} · ${esc(e.mode || "")}${e.status && e.status !== "candidate" ? ` · <span style="color:var(--gold)">${esc(e.status)}</span>` : ""}</div>
    <div class="trate"><span style="color:var(--faint);font-size:12px">RATE</span>
      ${starsHTML(e.code, true)}<span style="font-size:11px;color:var(--faint)">click a star to vote — votes are public</span></div>
    <div id="tPalWrap"><div id="tPal">${pal.map((c) => `<div style="background:${esc(c)}" data-hex="${esc(c)}" title="click to copy"></div>`).join("")}</div>
    <div style="font-family:var(--mono);font-size:10px;color:var(--faint);margin-top:8px">click a swatch to copy its hex</div></div>
    ${fline ? `<div style="margin-bottom:10px">${fline}</div>` : ""}
    <div id="tTags">${(e.tags || []).map((t) => `<span class="tag on">${esc(t)}</span>`).join("")}</div>
    <div id="tDesc">${esc(e.description || "")}</div>
    ${e.signature ? `<div id="tSig"><b>Signature</b> ${esc(e.signature)}</div>` : ""}
    ${e.lineage ? `<div id="tLineage"><b>Lineage</b> ${esc(e.lineage)}</div>` : ""}
    <div id="tSrc" title="click to copy source path">src: ${esc(e.source || "?")}</div>
    <div class="tbtns">
      <button class="tbtn primary" id="tOpen">Open full ↗</button>
      <button class="tbtn ${S.pickSet.has(e.code) ? "starred" : ""}" id="tStar">${S.pickSet.has(e.code) ? "★ Picked" : "☆ Star"}</button>
    </div>`;
  const site = projectSite(e);
  const ext = e.externalUrl && !hasMount(e) ? e.externalUrl
            : (e.externalUrl && e.externalUrl !== previewUrl(e) ? e.externalUrl : null);
  let links = "";
  if (site) links += `<a class="tlink" href="${esc(trackedOut(e.code, site))}" target="_blank" rel="noopener">🌐 ${esc(e.project)} site ↗</a>`;
  if (ext && ext !== site) links += `<a class="tlink" href="${esc(trackedOut(e.code, ext))}" target="_blank" rel="noopener">🔗 Live page ↗</a>`;
  const views = S.views[e.code] || 0;
  const viewHtml = `<div class="tviews">👁 ${views} view${views === 1 ? "" : "s"} · rated by ${(S.ratings[e.code] || {}).c || 0}</div>`;
  $("tLinks").innerHTML = links;
  $("tViews").innerHTML = viewHtml;
  $("tIdx").innerHTML = `<b>${S.theaterIdx + 1}</b> / ${S.filtered.length} · ${esc(e.code)}`;
  document.querySelectorAll("#tPal div").forEach((d) =>
    d.onclick = () => copyText(d.dataset.hex, d.dataset.hex));
  document.querySelectorAll("#tPanel .stars.rate i").forEach((i) =>
    i.onclick = () => castVote(e.code, +i.dataset.stars));
  bindStarHover($("tPanel"));
  $("tSrc").onclick = () => copyText(e.source, "source path");
  $("tOpen").onclick = () => window.open(previewUrl(e), "_blank");
  $("tStar").onclick = () => toggleStar(e.code);
}
$("tPrev").onclick = () => navTheater(-1);
$("tNext").onclick = () => navTheater(1);
$("tRandom").onclick = () => { if (S.filtered.length) openTheater(Math.floor(Math.random() * S.filtered.length)); };

/* ---------------- views ---------------- */
function setView(v) {
  S.view = v;
  document.querySelectorAll(".tabs button").forEach((b) =>
    b.classList.toggle("on", b.dataset.view === v));
  grid.style.display = v === "gallery" ? "grid" : "none";
  $("collections").style.display = v === "collections" ? "grid" : "none";
  $("picksWrap").style.display = v === "picks" ? "block" : "none";
  if (v === "gallery") renderGrid();
  if (v === "collections") { renderCollections(); $("count").innerHTML = `<b>${S.catalog.length}</b> styles · ${new Set(S.catalog.map((e) => e.project)).size} projects`; }
  if (v === "picks") renderPicks();
}
document.querySelectorAll(".tabs button").forEach((b) =>
  b.onclick = () => setView(b.dataset.view));

/* ---------------- inputs ---------------- */
let searchTimer;
$("search").addEventListener("input", (ev) => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    S.filters.search = ev.target.value;
    S.codesFilter = null;
    apply();
  }, 120);
});
$("search").addEventListener("keydown", (ev) => {
  if (ev.key === "Escape") { ev.target.value = ""; S.filters.search = ""; apply(); ev.target.blur(); }
  ev.stopPropagation();
});
$("sort").onchange = (ev) => { S.sort = ev.target.value; apply(); };
$("clearAll").onclick = () => {
  const f = S.filters;
  f.categories.clear(); f.projects.clear(); f.modes.clear();
  f.hues.clear(); f.statuses.clear(); f.tags.clear();
  f.search = ""; $("search").value = "";
  S.codesFilter = null;
  buildSidebar(); apply();
  toast("Filters cleared");
};

/* card clicks (delegated) */
grid.addEventListener("click", (ev) => {
  const rateI = ev.target.closest(".stars.rate i");
  if (rateI) { castVote(rateI.parentElement.dataset.code, +rateI.dataset.stars); return; }
  const star = ev.target.closest(".star");
  if (star) { toggleStar(star.dataset.code); return; }
  const card = ev.target.closest(".card");
  if (card) openTheater(+card.dataset.i);
});

/* ---------------- keyboard ---------------- */
document.addEventListener("keydown", (ev) => {
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(ev.target.tagName);
  const theaterOpen = $("theater").classList.contains("open");
  const helpOpen = $("help").classList.contains("open");
  const chatOpen = $("chat").classList.contains("open");

  if (ev.key === "Escape") {
    if (helpOpen) { $("help").classList.remove("open"); return; }
    if (theaterOpen) { closeTheater(); return; }
    if (chatOpen) { window.ChatUI?.close(); return; }
    return;
  }
  if (typing) return;
  if (helpOpen) return;

  if (theaterOpen) {
    if (ev.key === "ArrowLeft") { ev.preventDefault(); navTheater(-1); }
    else if (ev.key === "ArrowRight") { ev.preventDefault(); navTheater(1); }
    else if (ev.key.toLowerCase() === "s") { ev.preventDefault(); toggleStar(S.filtered[S.theaterIdx].code); }
    else if (ev.key.toLowerCase() === "r") { ev.preventDefault(); $("tRandom").click(); }
    return;
  }

  switch (ev.key) {
    case "ArrowLeft": case "ArrowRight": case "ArrowUp": case "ArrowDown": {
      if (S.view !== "gallery" || !S.filtered.length) return;
      ev.preventDefault();
      const cols = Math.max(1, Math.round(grid.clientWidth / 300));
      const cur = S.focusIdx;
      let next = cur;
      if (ev.key === "ArrowLeft") next = cur - 1;
      if (ev.key === "ArrowRight") next = cur + 1;
      if (ev.key === "ArrowUp") next = cur - cols;
      if (ev.key === "ArrowDown") next = cur + cols;
      next = Math.max(0, Math.min(S.filtered.length - 1, next));
      focusCard(next);
      break;
    }
    case "Enter":
      if (S.view === "gallery" && S.focusIdx >= 0) openTheater(S.focusIdx);
      break;
    case "/":
      ev.preventDefault(); $("search").focus();
      break;
    case "?":
      $("help").classList.add("open");
      break;
    default: {
      const k = ev.key.toLowerCase();
      if (k === "s" && S.focusIdx >= 0 && S.view === "gallery") toggleStar(S.filtered[S.focusIdx].code);
      else if (k === "r" && S.filtered.length) openTheater(Math.floor(Math.random() * S.filtered.length));
      else if (k === "c") window.ChatUI?.toggle();
      else if (k === "g") setView("gallery");
      else if (k === "v") setView("collections");
      else if (k === "p") setView("picks");
    }
  }
});

/* expose for chatbot */
window.Atlas = {
  S, apply, setView, openTheaterByCode, toast,
  setCodesFilter(codes) {
    if (!codes || !codes.length) { S.codesFilter = null; apply(); return; }
    S.codesFilter = new Set(codes);
    apply();
    setView("gallery");
    toast(`Concierge narrowed to ${S.filtered.length} styles`);
  },
  applyFilter(f) {
    const fl = S.filters;
    fl.categories = new Set(f.category ? [f.category] : []);
    fl.projects = new Set(f.project ? [f.project] : []);
    fl.modes = new Set(f.mode ? [f.mode] : []);
    fl.tags = new Set(f.tags || []);
    fl.search = f.search || "";
    $("search").value = fl.search;
    S.codesFilter = f.codes ? new Set(f.codes) : null;
    buildSidebar();
    apply();
    setView("gallery");
    toast(`Filters applied — ${S.filtered.length} styles`);
  },
};

boot();
