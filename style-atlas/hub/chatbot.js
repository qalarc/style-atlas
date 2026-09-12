/* STYLE ATLAS — Atlas Concierge chatbot
   Talks to /api/chat (Ollama glm-4.7-flash locally, rule fallback in server).
   Applies filter actions to the gallery live. */
"use strict";

(function () {
  const $ = (id) => document.getElementById(id);
  const log = $("chatlog");
  const input = $("chatInput");
  const send = $("chatSend");
  let history = [];
  let busy = false;

  const QUICK = [
    "dark themes with gold",
    "chat app styles",
    "logo concepts",
    "light minimal websites",
    "game UIs",
    "dashboard looks",
    "surprise me",
  ];

  function addMsg(text, who, filter) {
    const d = document.createElement("div");
    d.className = "msg " + who;
    d.textContent = text;
    if (filter) {
      const chip = document.createElement("span");
      chip.className = "fchip";
      const keys = Object.entries(filter)
        .filter(([, v]) => v && (!Array.isArray(v) || v.length))
        .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.slice(0, 4).join(",") + (v.length > 4 ? "…" : "") : v}`)
        .join(" · ");
      chip.textContent = `▸ apply filter — ${keys || "clear"}`;
      chip.title = "click to apply these filters";
      chip.onclick = () => {
        window.Atlas.applyFilter(filter);
        window.Atlas.toast("Filters applied from chat");
      };
      d.appendChild(document.createElement("br"));
      d.appendChild(chip);
    }
    log.appendChild(d);
    log.scrollTop = log.scrollHeight;
    return d;
  }

  function addChips() {
    const chips = $("chips");
    chips.innerHTML = "";
    QUICK.forEach((q) => {
      const s = document.createElement("span");
      s.className = "tag";
      s.textContent = q;
      s.onclick = () => { input.value = q; doSend(); };
      chips.appendChild(s);
    });
  }

  async function doSend() {
    const msg = input.value.trim();
    if (!msg || busy) return;
    input.value = "";
    addMsg(msg, "user");
    history.push({ role: "user", content: msg });
    busy = true;
    send.disabled = true;
    const thinking = addMsg("…", "bot");
    try {
      const r = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg, history: history.slice(0, -1) }),
      });
      const data = await r.json();
      thinking.remove();
      const reply = data.reply || "(no reply)";
      addMsg(reply + (data.fallback ? "\n\n_(local model offline — deterministic matcher)_" : ""), "bot", data.filter);
      history.push({ role: "assistant", content: reply });
      if (history.length > 20) history = history.slice(-20);
      /* auto-apply the filter so chat narrows the gallery live */
      if (data.filter) {
        setTimeout(() => {
          window.Atlas.applyFilter(data.filter);
        }, 350);
      }
    } catch (ex) {
      thinking.remove();
      addMsg("Chat backend unreachable — is atlas_server.py running?", "bot");
    }
    busy = false;
    send.disabled = false;
  }

  function open() {
    $("chat").classList.add("open");
    if (!log.children.length) {
      addMsg("Hi — I'm the Atlas Concierge. Ask me about any style, color mood, or use-case and I'll narrow the catalog.\n\nTry: “dark + gold for a law firm”, “which chat themes are light?”, “show GM versions with serif type”.", "bot");
      addChips();
    }
    setTimeout(() => input.focus(), 50);
  }
  function close() { $("chat").classList.remove("open"); }

  $("chatFab").onclick = () => $("chat").classList.contains("open") ? close() : open();
  $("chatClose").onclick = close;
  send.onclick = doSend;
  input.addEventListener("keydown", (ev) => {
    ev.stopPropagation();
    if (ev.key === "Enter") doSend();
  });

  window.ChatUI = { open, close, toggle: () => $("chat").classList.contains("open") ? close() : open() };
})();
