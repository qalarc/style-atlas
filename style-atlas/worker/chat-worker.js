// style-atlas chat worker — proxies POST /api/chat to Z.AI GLM flash models.
// Serves alongside static assets (see wrangler.toml run_worker_first).
// The catalog digest is injected at build time by scripts/build_static.py.

const ZAI_URL = "https://api.z.ai/api/paas/v4/chat/completions";
const MODELS = ["glm-4.7-flash", "glm-4.5-flash"];
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

const DIGEST = /*__CATALOG_DIGEST__*/[];

function systemPrompt() {
  return (
    "You are the Atlas Concierge for a design style catalog. Help the user choose " +
    "styles by answering questions about colors, typography, mood and use-cases.\n\n" +
    "CATALOG (code|name|project|category|mode|tags):\n" + DIGEST.join("\n") + "\n\n" +
    "RULES:\n" +
    "1. Be brief (2-4 sentences). Cite entries by code.\n" +
    "2. When recommending or narrowing styles ALWAYS finish with a json filter block. " +
    "Allowed keys: category, project, mode (ONLY 'dark','light','both'), tags (list), " +
    "search (substring), codes (list of catalog codes you recommend). Never invent values.\n" +
    '3. Example:\n```json\n{"filter": {"mode": "dark", "codes": ["TZ-001"]}}\n```\n' +
    "4. English only."
  );
}

function sanitizeFilter(f, validCats, validProjects, validCodes) {
  if (!f || typeof f !== "object") return null;
  const out = {};
  if (typeof f.category === "string" && validCats.has(f.category)) out.category = f.category;
  if (typeof f.project === "string" && validProjects.has(f.project)) out.project = f.project;
  if (["dark", "light", "both"].includes(f.mode)) out.mode = f.mode;
  if (Array.isArray(f.tags)) {
    const t = f.tags.map(String).slice(0, 5);
    if (t.length) out.tags = t;
  }
  if (typeof f.search === "string" && f.search.trim()) out.search = f.search.trim().slice(0, 60);
  if (Array.isArray(f.codes)) {
    const c = f.codes.filter((x) => validCodes.has(x)).slice(0, 24);
    if (c.length) out.codes = c;
  }
  return Object.keys(out).length ? out : null;
}

function extractFilter(text) {
  let m = text.match(/```json\s*(\{[\s\S]*?\})\s*```/);
  let obj = null;
  if (m) { try { obj = JSON.parse(m[1]); } catch {} }
  if (!obj) {
    m = text.match(/\{\s*\"filter\"\s*:[\s\S]*\}/);
    if (m) { try { obj = JSON.parse(m[0]); } catch {} }
  }
  if (!obj) {
    m = text.match(/\"codes\"\s*:\s*\[([^\]]*)\]/);
    if (m) {
      const codes = (m[1].match(/[A-Z]{1,4}-[A-Z0-9]{1,4}\d{1,3}/g) || []);
      return codes.length ? { codes: codes.slice(0, 12) } : null;
    }
    return null;
  }
  return obj.filter || obj;
}

async function zaiChat(message, history, key) {
  const body = {
    model: MODELS[0],
    temperature: 0.2,
    max_tokens: 900,
    thinking: { type: "disabled" },  // 4.5-flash: skip reasoning, answer directly
    messages: [
      { role: "system", content: systemPrompt() },
      ...(history || []).slice(-6).map((h) => ({
        role: h.role === "assistant" ? "assistant" : "user",
        content: String(h.content || "").slice(0, 500),
      })),
      { role: "user", content: message },
    ],
  };
  let lastErr = "";
  for (const model of MODELS) {
    body.model = model;
    try {
      const r = await fetch(ZAI_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: "Bearer " + key },
        body: JSON.stringify(body),
      });
      const d = await r.json().catch(() => null);
      if (!r.ok || d?.error) {
        const code = d?.error?.code;
        lastErr = model + " → " + (code || "HTTP " + r.status);
        if ((code === "1305" || code === "1302") && model === MODELS[0]) {
          await new Promise((res) => setTimeout(res, 2500)); // overloaded — retry once
          continue;
        }
        continue;
      }

      const msg = d?.choices?.[0]?.message || {};
      const content = msg.content && msg.content.trim()
        ? msg.content
        : (msg.reasoning_content || "").trim().replace(/^\s*(Final|Answer)[::]?\s*/i, "");
      if (content) return content;
      lastErr = model + " \u2192 empty content";
    } catch (e) { lastErr = model + " → " + String(e).slice(0, 120); }
  }
  throw new Error(lastErr);
}

async function loadKV(env, key) {
  try {
    const v = await env.RATINGS.get(key);
    return v ? JSON.parse(v) : {};
  } catch { return {}; }
}
async function loadRatings(env) {
  try {
    const v = await env.RATINGS.get("all");
    return v ? JSON.parse(v) : {};
  } catch { return {}; }
}
async function saveRatings(env, all) {
  await env.RATINGS.put("all", JSON.stringify(all));
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS });
    }
    if (url.pathname === "/api/chat" && request.method === "GET") {
      return new Response(JSON.stringify({ ok: true, models: MODELS }), {
        headers: { "Content-Type": "application/json", ...CORS },
      });
    }
    // ---------- ratings: GET aggregate, POST a vote ----------
    // ---------- tracked outbound links: /out/<CODE>?to=<url> ----------
    const ALLOWED_OUT = [
      "qalarc.com", "tradez.au", "x10.au", "gmux.ai", "endispute.com.au",
      "volkus.net", "chanalyse.org", "rwf.qalarc.com", "qalarc.ai",
      "github.com/qalarc", "sahha.com", "healthapi.fit", "qalnet",
    ];
    const mOut = url.pathname.match(/^\/out\/([A-Za-z0-9-]+)\/?$/);
    if (mOut && request.method === "GET") {
      const code = mOut[1];
      const validCodes = new Set(DIGEST.map((l) => l.split("|")[0]));
      const to = url.searchParams.get("to") || "";
      let host = "";
      try { host = new URL(to).hostname; } catch {}
      const allowed = ALLOWED_OUT.some((d) =>
        host === d || host.endsWith("." + d) || (host + "/").startsWith(d + "/"));
      if (!validCodes.has(code) || !to || !allowed) {
        return new Response("blocked outbound link", { status: 400 });
      }
      // record follow-on interest
      const out = await loadKV(env, "out");
      const slot = out[code] || {};
      slot[to] = (slot[to] || 0) + 1;
      out[code] = slot;
      await env.RATINGS.put("out", JSON.stringify(out));
      // decorated destination so the qalarc concierge sees the origin
      const u = new URL(to);
      u.searchParams.set("ref", "style-atlas");
      u.searchParams.set("style", code);
      return Response.redirect(u.toString(), 302);
    }

    // ---------- view counter ----------
    if (url.pathname === "/api/view" && request.method === "POST") {
      let code = "";
      try { code = String((await request.json()).code || ""); } catch {}
      const validCodes = new Set(DIGEST.map((l) => l.split("|")[0]));
      if (!validCodes.has(code)) {
        return new Response(JSON.stringify({ error: "bad code" }),
          { status: 400, headers: { "Content-Type": "application/json", ...CORS } });
      }
      const views = await loadKV(env, "views");
      views[code] = (views[code] || 0) + 1;
      await env.RATINGS.put("views", JSON.stringify(views));
      return new Response(JSON.stringify({ views }), {
        headers: { "Content-Type": "application/json", ...CORS } });
    }
    if (url.pathname === "/api/views" && request.method === "GET") {
      return new Response(JSON.stringify({ views: await loadKV(env, "views") }), {
        headers: { "Content-Type": "application/json", ...CORS } });
    }
    // concierge-facing aggregate: views + outbound interest per style
    if (url.pathname === "/api/interest" && request.method === "GET") {
      const [views, out] = await Promise.all([loadKV(env, "views"), loadKV(env, "out")]);
      return new Response(JSON.stringify({ views, outbound: out }), {
        headers: { "Content-Type": "application/json", ...CORS } });
    }

    // ---------- fusion combos ----------
    if (url.pathname === "/api/combos" && request.method === "GET") {
      const cl = await loadKV(env, "combosList");
        return new Response(JSON.stringify({ combos: Array.isArray(cl) ? cl : [] }),
        { headers: { "Content-Type": "application/json", ...CORS } });
    }
    if (url.pathname === "/api/combos" && request.method === "POST") {
      let body = {};
      try { body = await request.json(); } catch {}
      const parts = body.parts || {};
      const validCodes = new Set(DIGEST.map((l) => l.split("|")[0]));
      const needed = ["palette", "type", "buttons", "motion"];
      if (!needed.every((k) => validCodes.has(parts[k]))) {
        return new Response(JSON.stringify({ error: "parts must be 4 valid style codes" }),
          { status: 400, headers: { "Content-Type": "application/json", ...CORS } });
      }
      const raw = await loadKV(env, "combosList");
      const list = Array.isArray(raw) ? raw : [];
      const nxt = 1 + list.reduce((m, c) => {
        const n = parseInt(String(c.code || "").slice(3), 10);
        return isNaN(n) ? m : Math.max(m, n);
      }, 0);
      const combo = {
        code: "FX-" + String(nxt).padStart(3, "0"),
        name: String(body.name || "Untitled fusion").slice(0, 80),
        parts: Object.fromEntries(needed.map((k) => [k, parts[k]])),
        ts: Date.now() / 1000 | 0,
      };
      list.unshift(combo);
      await env.RATINGS.put("combosList", JSON.stringify(list));
      return new Response(JSON.stringify({ combo }), {
        headers: { "Content-Type": "application/json", ...CORS } });
    }

    if (url.pathname === "/api/ratings" && request.method === "GET") {
      const all = await loadRatings(env);
      return new Response(JSON.stringify({ ratings: all }), {
        headers: { "Content-Type": "application/json", ...CORS },
      });
    }
    if (url.pathname === "/api/rate" && request.method === "POST") {
      let code = "", stars = 0;
      try {
        const b = await request.json();
        code = String(b.code || "");
        stars = parseInt(b.stars, 10);
      } catch {}
      const validCodes = new Set(DIGEST.map((l) => l.split("|")[0]));
      const cbs = await loadKV(env, "combosList");
      if (Array.isArray(cbs)) cbs.forEach((c) => validCodes.add(c.code));
      if (!validCodes.has(code) || !(stars >= 1 && stars <= 5)) {
        return new Response(JSON.stringify({ error: "bad vote" }), {
          status: 400, headers: { "Content-Type": "application/json", ...CORS },
        });
      }
      const all = await loadRatings(env);
      const r = all[code] || { s: 0, c: 0 };
      r.s += stars;
      r.c += 1;
      all[code] = r;
      await saveRatings(env, all);
      return new Response(JSON.stringify({ ratings: all, your: { code, stars } }), {
        headers: { "Content-Type": "application/json", ...CORS },
      });
    }

    if (url.pathname === "/api/chat" && request.method === "POST") {
      const key = env.ZAI_API_KEY;
      let msg = "", history = [];
      try {
        const b = await request.json();
        msg = String(b.message || "");
        history = Array.isArray(b.history) ? b.history : [];
      } catch {}
      if (!msg.trim()) {
        return new Response(JSON.stringify({ reply: "Ask me about styles, colors or use-cases." }),
          { status: 200, headers: { "Content-Type": "application/json", ...CORS } });
      }
      if (!key) {
        return new Response(JSON.stringify({ reply: "Chat not configured (missing ZAI_API_KEY).", matcher: "none" }),
          { status: 200, headers: { "Content-Type": "application/json", ...CORS } });
      }
      try {
        const reply = await zaiChat(msg, history, key);
        const validCodes = new Set(DIGEST.map((l) => l.split("|")[0]));
        const validCats = new Set(DIGEST.map((l) => l.split("|")[3]));
        const validProjects = new Set(DIGEST.map((l) => l.split("|")[2]));
        let filt = sanitizeFilter(extractFilter(reply), validCats, validProjects, validCodes);
        if (!filt) {
          // model recommended styles in prose but skipped the json block —
          // salvage every catalog code it mentioned
          const seen = new Set();
          const mentioned = (reply.match(/[A-Z]{1,4}-[A-Z]{0,4}\d{1,4}/g) || [])
            .filter((c) => validCodes.has(c) && !seen.has(c) && seen.add(c));
          if (mentioned.length) filt = { codes: mentioned.slice(0, 12) };
        }
        const clean = reply.replace(/```json[\s\S]*?```/g, "").trim();
        return new Response(JSON.stringify({ reply: clean, filter: filt, model: "zai-flash" }), {
          status: 200, headers: { "Content-Type": "application/json", ...CORS },
        });
      } catch (e) {
        return new Response(JSON.stringify({ reply: "Chat backend error: " + e.message, matcher: "error" }), {
          status: 200, headers: { "Content-Type": "application/json", ...CORS },
        });
      }
    }
    // everything else → static assets
    return env.ASSETS.fetch(request);
  },
};
