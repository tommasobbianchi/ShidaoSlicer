#!/usr/bin/env python3
"""Tiny web server for browsing validation screenshots.

Binds to 0.0.0.0 so Tailscale peers (e.g. thinkpad) can reach it via the
nativedev tailscale IP/hostname.

Run:
  python3 validation/screenshots_server.py [--port 9876]

Reachable from thinkpad as:
  http://nativedev.tail7d3518.ts.net:9876/
  http://<DEV_HOST>:9876/
"""

import argparse
import json
import html
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent / "screenshots"

CSS = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body {
    margin: 0; padding: 20px 30px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #0d1117; color: #c9d1d9;
}
h1 { margin: 0 0 6px 0; font-size: 22px; }
.sub { color: #7d8590; font-size: 13px; margin-bottom: 30px; }
h2 {
    font-size: 18px; color: #f0f6fc; margin: 40px 0 14px 0;
    padding-bottom: 6px; border-bottom: 1px solid #30363d;
}
.grid {
    display: grid; gap: 18px;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
}
.card {
    background: #161b22; border: 1px solid #30363d; border-radius: 8px;
    overflow: hidden; display: flex; flex-direction: column;
}
.card a.thumb {
    display: block; background: #000; aspect-ratio: 4/3; overflow: hidden;
}
.card img {
    width: 100%; height: 100%; object-fit: contain;
    display: block; transition: transform 0.2s;
}
.card:hover img { transform: scale(1.02); }
.meta { padding: 12px 14px; font-size: 13px; }
.meta .fname {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 11px; color: #7d8590; margin-bottom: 6px; word-break: break-all;
}
.tags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.tag {
    background: #21262d; color: #c9d1d9; padding: 2px 8px; border-radius: 10px;
    font-size: 11px; border: 1px solid #30363d;
}
.tag.phase { background: #1f2937; color: #60a5fa; border-color: #1e40af; }
.tag.view  { background: #1e293b; color: #a78bfa; border-color: #4c1d95; }
.tag.state { background: #1f2937; color: #34d399; border-color: #064e3b; }
.badge {
    display: inline-block; padding: 3px 10px; border-radius: 12px;
    font-size: 11px; font-weight: 600;
}
.badge.PASS { background: #033a2b; color: #3fb950; border: 1px solid #2ea043; }
.badge.WARN { background: #3b2e04; color: #d29922; border: 1px solid #9e6a03; }
.badge.FAIL { background: #490202; color: #f85149; border: 1px solid #b62324; }
.notes { margin-top: 8px; color: #8b949e; font-size: 12px; line-height: 1.4; }
.notes em { color: #c9d1d9; font-style: normal; }
.links { margin-top: 10px; display: flex; gap: 10px; font-size: 12px; }
.links a { color: #58a6ff; text-decoration: none; }
.links a:hover { text-decoration: underline; }
.empty { color: #6e7681; font-style: italic; padding: 40px; text-align: center; }
footer { color: #6e7681; font-size: 11px; margin-top: 60px; text-align: center; }
"""


def build_index_html(root: Path) -> str:
    if not root.exists():
        entries_html = '<div class="empty">No screenshots yet.</div>'
    else:
        day_dirs = sorted([p for p in root.iterdir() if p.is_dir()], reverse=True)
        sections = []
        total_count = 0
        for dd in day_dirs:
            cards = []
            pngs = sorted(dd.glob("phase*_seq*_*.png"))
            for png in pngs:
                meta_path = png.with_suffix(".json")
                meta = {}
                if meta_path.exists():
                    try:
                        meta = json.loads(meta_path.read_text())
                    except Exception:
                        meta = {}
                rel = f"/files/{dd.name}/{png.name}"
                rel_meta = f"/files/{dd.name}/{meta_path.name}"
                validation = meta.get("validation", {})
                vresult = validation.get("result", "")
                badge = f'<span class="badge {html.escape(vresult)}">{html.escape(vresult)}</span>' if vresult else ""
                notes = html.escape(meta.get("notes", "") or "")
                tags_html = "".join([
                    f'<span class="tag phase">{html.escape(meta.get("phase",""))}</span>',
                    f'<span class="tag view">{html.escape(meta.get("view",""))}</span>',
                    f'<span class="tag state">{html.escape(meta.get("tag","") or "")}</span>' if meta.get("tag") else "",
                    f'<span class="tag">seq{meta.get("seq","?"):03d}</span>' if isinstance(meta.get("seq"), int) else "",
                ])
                layers = ""
                if validation:
                    layers = f'&nbsp;·&nbsp;{validation.get("layers", "?")} layers&nbsp;·&nbsp;{validation.get("total_moves", "?")} moves'
                cards.append(f"""
                    <div class="card">
                        <a class="thumb" href="{rel}" target="_blank"><img src="{rel}" alt="{html.escape(png.name)}" loading="lazy"></a>
                        <div class="meta">
                            <div class="fname">{html.escape(png.name)}</div>
                            <div><strong>{html.escape(meta.get("object","?"))}</strong>{badge and " " + badge}{layers}</div>
                            <div class="tags">{tags_html}</div>
                            {f'<div class="notes">{notes}</div>' if notes else ''}
                            <div class="links">
                                <a href="{rel}" target="_blank">open image</a>
                                <a href="{rel_meta}" target="_blank">sidecar.json</a>
                            </div>
                        </div>
                    </div>
                """)
                total_count += 1
            if cards:
                sections.append(f'<h2>{dd.name} <span style="color:#6e7681;font-size:13px">· {len(cards)} screenshot{"s" if len(cards)!=1 else ""}</span></h2>\n<div class="grid">{"".join(cards)}</div>')
        entries_html = "\n".join(sections) if sections else '<div class="empty">No screenshots yet.</div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ORCA_BELT — validation screenshots</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>{CSS}</style>
</head>
<body>
<h1>ORCA_BELT validation screenshots</h1>
<div class="sub">Belt printer (IdeaFormer IR3 V2) slicing & print validation · auto-generated</div>
{entries_html}
<footer>served from nativedev · <code>{html.escape(str(ROOT))}</code></footer>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # quieter logs
        pass

    def do_GET(self):
        path = unquote(self.path.split("?", 1)[0])
        if path in ("/", "/index.html"):
            body = build_index_html(ROOT).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path.startswith("/files/"):
            rel = path[len("/files/"):]
            target = (ROOT / rel).resolve()
            if ROOT.resolve() not in target.parents and target != ROOT.resolve():
                self.send_error(403)
                return
            if not target.is_file():
                self.send_error(404)
                return
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=60")
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_error(404)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9876)
    ap.add_argument("--bind", default="0.0.0.0")
    args = ap.parse_args()
    server = ThreadingHTTPServer((args.bind, args.port), Handler)
    print(f"Serving {ROOT} on http://{args.bind}:{args.port}/")
    print(f"Tailscale: http://nativedev.tail7d3518.ts.net:{args.port}/  or  http://<DEV_HOST>:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
