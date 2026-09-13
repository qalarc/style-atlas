#!/usr/bin/env python3
"""
build_static.py — build a fully self-contained dist/ of the Style Atlas
for static hosting (Cloudflare Pages / any file server).

Static mode differences vs the local server:
  - no live-mounted /CODE/ previews  → cards + theater use thumbnails/swatch images
  - catalog embedded (atlas.json copied)
  - chatbot: deterministic in-browser matcher (no Ollama from the public web)
  - picks: localStorage instead of server file

Usage: python3 scripts/build_static.py [--out dist]
Then:  cd dist && npx wrangler pages deploy . --project-name style-atlas
   or: python3 -m http.server -d dist 8090
"""

import argparse
import json
import os
import re
import shutil

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HUB = os.path.join(HERE, "hub")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "dist"))
    args = ap.parse_args()
    out = args.out

    os.makedirs(os.path.join(out, "thumbs"), exist_ok=True)
    os.makedirs(os.path.join(out, "catalog"), exist_ok=True)

    # copy hub files
    for f in os.listdir(HUB):
        if f.endswith((".html", ".css", ".js")):
            shutil.copy2(os.path.join(HUB, f), os.path.join(out, f))

    # copy catalog
    shutil.copy2(
        os.path.join(HERE, "catalog", "atlas.json"),
        os.path.join(out, "catalog", "atlas.json"),
    )

    # copy thumbs that exist
    tdir = os.path.join(HERE, "thumbs")
    n = 0
    if os.path.isdir(tdir):
        for f in os.listdir(tdir):
            if f.endswith(".png"):
                shutil.copy2(os.path.join(tdir, f), os.path.join(out, "thumbs", f))
                n += 1

    # static-mode flags + offline chat fallback
    idx = os.path.join(out, "index.html")
    html = open(idx, encoding="utf-8").read()
    html = html.replace(
        "<body>", "<body>\n<script>window.STATIC_ATLAS=true;</script>", 1
    )
    open(idx, "w", encoding="utf-8").write(html)

    prj = os.path.join(out, "projects.html")
    html = open(prj, encoding="utf-8").read()
    html = html.replace(
        "<body>", "<body>\n<script>window.STATIC_ATLAS=true;</script>", 1
    )
    open(prj, "w", encoding="utf-8").write(html)

    # static chatbot fallback (appended, overrides fetch target)
    fallback = """
<script>
/* static-mode: local deterministic chat (no backend) */
(function(){
  if (!window.STATIC_ATLAS) return;
  const CAT = (window.ATLAS_CATALOG||[]); let CATL=null;
  fetch("/catalog/atlas.json").then(r=>r.json()).then(c=>{CATL=c.entries||[]});
  window.ATLAS_CHAT_FALLBACK = async function(message){
    await new Promise(r=>setTimeout(r,150));
    const msg=message.toLowerCase(); const f={}; const codes=[];
    if(/dark/.test(msg)) f.mode="dark"; if(/light|bright/.test(msg)) f.mode="light";
    for(const c of ["website","landing","directory","phone-app","chat-app","game","dashboard","theme-kit","logo","hero-module","terminal","poster","email"]){
      if(msg.includes(c)||msg.includes(c.replace("-"," "))){f.category=c;break;}
    }
    for(const w of ["gold","green","blue","navy","neon","red","purple","teal","warm","cool","pink","orange","serif","mono","minimal","brutalist","glass","retro"]){
      if(msg.includes(w)){f.search=w;break;}
    }
    const list=(CATL||[]).filter(e=>{
      if(f.mode&&e.mode!==f.mode)return false;
      if(f.category&&e.category!==f.category)return false;
      if(f.search){const hay=[e.name,e.code,e.project,(e.tags||[]).join(" "),JSON.stringify(e.palette||{})].join(" ").toLowerCase();if(!hay.includes(f.search))return false;}
      return true;
    });
    list.slice(0,12).forEach(e=>codes.push(e.code));
    const nm=list.length?list.length:0;
    return {reply:"Static mode — deterministic matcher.\\n"+(nm?nm+" matching styles"+(codes.length?" (showing "+codes.slice(0,8).join(", ")+(codes.length>8?"…":"")+")":""):"No matches — try 'dark gold', 'chat app', 'logo'."), filter:Object.assign({},f,codes.length?{codes}:{}), fallback:true};
  };
})();
</script>
"""
    idx2 = os.path.join(out, "index.html")
    html = open(idx2, encoding="utf-8").read()
    html = html.replace("</body>", fallback + "</body>")
    open(idx2, "w", encoding="utf-8").write(html)

    # app.js static adjustments: catalog fetch path, picks localStorage, preview → thumb image
    # static mode: previews are thumbnails (or the external URL); no live mounts
    app = os.path.join(out, "app.js")
    js = open(app, encoding="utf-8").read()
    js = js.replace(
        "function previewUrl(e) {",
        """function previewUrl(e) {
  if (window.STATIC_ATLAS) {
    if (e.externalUrl) return e.externalUrl;
    return "/thumbs/" + e.code + ".png";
  }""",
        1,
    )
    js = js.replace(
        'fetch("/api/catalog")',
        'fetch(window.STATIC_ATLAS?"/catalog/atlas.json":"/api/catalog")',
    )
    js = js.replace(
        'await fetch("/api/picks")',
        'window.STATIC_ATLAS?{json:async()=>({picks:JSON.parse(localStorage.getItem("atlas.picks")||"[]")})}:await fetch("/api/picks")',
    )
    # picks persistence → localStorage in static mode
    js = js.replace(
        'async function apiPick(action, code, note = "") {',
        """async function apiPick(action, code, note = "") {
  if (window.STATIC_ATLAS) {
    let picks = JSON.parse(localStorage.getItem("atlas.picks") || "[]");
    picks = picks.filter((x) => x.code !== code);
    if (action === "add" || action === "note")
      picks.unshift({ code, note: note || "", ts: Date.now() / 1000 | 0 });
    localStorage.setItem("atlas.picks", JSON.stringify(picks));
    S.picks = picks; S.pickSet = new Set(picks.map((x) => x.code));
    renderPickCount(); if (S.view === "picks") renderPicks();
    return true;
  }""",
    )
    # count / stats fetches
    open(app, "w", encoding="utf-8").write(js)

    # projects.html catalog fetch path
    prj2 = os.path.join(out, "projects.html")
    html = open(prj2, encoding="utf-8").read()
    html = html.replace('fetch("/api/catalog")', 'fetch("/catalog/atlas.json")')
    open(prj2, "w", encoding="utf-8").write(html)

    # chat + ratings worker: copy and inject the catalog digest
    worker_src = os.path.join(HERE, "worker", "chat-worker.js")
    worker_dst = os.path.join(out, "chat-worker.js")
    if os.path.exists(worker_src):
        wf = open(worker_src, encoding="utf-8").read()
        digest = []
        with open(os.path.join(HERE, "catalog", "atlas.json"), encoding="utf-8") as f:
            for e in json.load(f)["entries"]:
                digest.append("|".join(str(x) for x in [
                    e["code"], e.get("name", "")[:28], e.get("project", ""),
                    e.get("category", ""), e.get("mode", ""),
                    ",".join((e.get("tags") or [])[:3])]))
        wf = wf.replace("/*__CATALOG_DIGEST__*/[]",
                        json.dumps(digest, ensure_ascii=False))
        open(worker_dst, "w", encoding="utf-8").write(wf)

    # wrangler config (workers-style: assets + worker-first for /api/*)
    wr = os.path.join(out, "wrangler.toml")
    with open(wr, "w") as f:
        f.write(
            "name = \"style-atlas\"\n"
            "compatibility_date = \"2026-09-01\"\n"
            "main = \"chat-worker.js\"\n\n"

            "[assets]\n"
            "directory = \"./\"\n"
            "run_worker_first = [\"/api/*\"]\n\n"
            "[[kv_namespaces]]\n"
            "binding = \"RATINGS\"\n"
            "id = \"a5e0962dd18446d593b6e5d027d6aa41\"\n"
        )

    size = (
        sum(
            os.path.getsize(os.path.join(dp, f))
            for dp, _, fs in os.walk(out)
            for f in fs
        )
        / 1e6
    )
    print(f"dist built: {out}  ({size:.1f} MB, {n} thumbs)")
    print("deploy:  cd dist && npx wrangler pages deploy . --project-name style-atlas")
    print("preview: python3 -m http.server -d dist 8090")


if __name__ == "__main__":
    main()
