#!/usr/bin/env python3
"""Render docs/PROJECT_START_TEAM_GUIDE.md → a single-file, navigable HTML guide.

Design: an "engineering field manual" — warm paper, oxblood signal accent, Fraunces
titles + IBM Plex Mono command/labels + IBM Plex Sans body. UX: sticky scroll-spy TOC,
an at-a-glance summary, collapsible sections (expand/collapse-all + hash-open), a live
filter, and copy-to-clipboard on every command block. Self-contained (fonts via CDN with
system fallbacks); regenerate whenever the source markdown changes.

Usage:  python3 scripts/render_project_start_guide.py
"""
from __future__ import annotations

import html
import re
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "PROJECT_START_TEAM_GUIDE.md"
OUT = ROOT / "docs" / "PROJECT_START_TEAM_GUIDE.html"

MD_EXT = ["tables", "fenced_code", "sane_lists", "attr_list"]


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "section"


def inline_md(text: str) -> str:
    """Escape, then render inline `code` spans — for headings that carry markdown."""
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", html.escape(text))


def plain(text: str) -> str:
    """Plain text with markdown ticks stripped — for the TOC labels."""
    return html.escape(text.replace("`", ""))


def split_sections(md: str):
    """Return (intro_md, [(num, title, body_md), ...]) split on H2 headings."""
    lines = md.splitlines()
    # drop the H1 (rendered separately) and capture intro until first H2
    intro, sections = [], []
    cur = None
    for ln in lines:
        m2 = re.match(r"^##\s+(.*)$", ln)
        m1 = re.match(r"^#\s+(.*)$", ln)
        if m1 and cur is None and not sections and not any(s.strip() for s in intro):
            continue  # skip the document H1
        if m2:
            if cur is not None:
                sections.append(cur)
            title = m2.group(1).strip()
            nm = re.match(r"^(\d+)\.\s+(.*)$", title)
            num = nm.group(1) if nm else ""
            clean = nm.group(2) if nm else title
            cur = {"num": num, "title": clean, "body": []}
        elif cur is None:
            intro.append(ln)
        else:
            cur["body"].append(ln)
    if cur is not None:
        sections.append(cur)
    for s in sections:
        s["body"] = "\n".join(s["body"]).strip()
        s["slug"] = slugify(f"{s['num']}-{s['title']}")
    return "\n".join(intro).strip(), sections


def tag_cost(html_str: str) -> str:
    """Wrap $0 / paid / deprecated cues in semantic pills (scannability)."""
    html_str = re.sub(r"(?<![\w])\$0(?![\w])", '<span class="pill pill-free">$0</span>', html_str)
    return html_str


def render_body(md_body: str) -> str:
    body = markdown.markdown(md_body, extensions=MD_EXT, output_format="html5")
    return tag_cost(body)


CSS = r"""
:root{
  --paper:#f4efe4; --paper2:#efe8d9; --card:#faf6ec; --ink:#211c15; --muted:#6f6555;
  --line:#ddd2bd; --line2:#cabfa6; --accent:#b0432a; --accent-soft:#e9d3c6;
  --free:#3f7d4e; --paid:#a9791a; --dep:#8a8172;
  --term-bg:#221d17; --term-ink:#ece3d2; --term-dim:#9b917c;
  --shadow:0 1px 2px rgba(33,28,21,.06),0 8px 30px rgba(33,28,21,.06);
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--paper);color:var(--ink);
  font:16px/1.62 "IBM Plex Sans",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  background-image:radial-gradient(rgba(120,100,70,.05) 1px,transparent 1px);
  background-size:22px 22px;}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline;text-underline-offset:2px}
code{font-family:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;font-size:.86em;
  background:#ece3d1;border:1px solid var(--line);border-radius:5px;padding:.06em .38em}

/* layout */
.shell{display:grid;grid-template-columns:288px minmax(0,1fr);gap:0;max-width:1240px;margin:0 auto;
  align-items:start}
/* sidebar */
.side{position:sticky;top:0;height:100vh;overflow-y:auto;padding:34px 22px 40px 30px;
  border-right:1px solid var(--line)}
.brand{font-family:"IBM Plex Mono",monospace;font-size:12px;letter-spacing:.16em;text-transform:uppercase;
  color:var(--accent);font-weight:600}
.brand .sub{display:block;color:var(--muted);letter-spacing:.05em;margin-top:6px;font-size:11px}
.filter{margin:22px 0 14px;position:relative}
.filter input{width:100%;padding:9px 12px 9px 32px;border:1px solid var(--line2);border-radius:9px;
  background:var(--card);color:var(--ink);font:13px/1 "IBM Plex Sans",sans-serif}
.filter input:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
.filter svg{position:absolute;left:10px;top:9px;width:14px;height:14px;stroke:var(--muted);fill:none}
nav.toc{margin-top:6px}
nav.toc a{display:flex;gap:10px;align-items:baseline;padding:7px 10px;border-radius:8px;color:var(--ink);
  font-size:13.5px;line-height:1.35;transition:background .12s,color .12s}
nav.toc a .n{font-family:"IBM Plex Mono",monospace;font-size:11px;color:var(--muted);min-width:20px;font-weight:600}
nav.toc a:hover{background:var(--paper2);text-decoration:none}
nav.toc a.active{background:var(--accent);color:#fff}
nav.toc a.active .n{color:#f4d9cd}
nav.toc a.hide{display:none}
.side-foot{margin-top:22px;padding-top:16px;border-top:1px dashed var(--line2);color:var(--muted);font-size:11.5px}

/* main */
main{padding:44px 56px 90px;min-width:0}
.masthead h1{font-family:"Fraunces",Georgia,serif;font-weight:600;font-size:40px;line-height:1.08;
  letter-spacing:-.01em;margin:0 0 6px}
.masthead .kicker{font-family:"IBM Plex Mono",monospace;font-size:11.5px;letter-spacing:.22em;
  text-transform:uppercase;color:var(--accent);font-weight:600;margin-bottom:14px}
.masthead .lede{font-size:16.5px;color:var(--muted);max-width:64ch}
.masthead .lede b{color:var(--ink)}

/* summary card */
.summary{margin:30px 0 8px;background:linear-gradient(180deg,var(--card),#f6f0e2);
  border:1px solid var(--line2);border-radius:16px;padding:26px 28px;box-shadow:var(--shadow)}
.summary h2{font-family:"IBM Plex Mono",monospace;font-size:12px;letter-spacing:.16em;text-transform:uppercase;
  color:var(--accent);margin:0 0 16px;font-weight:600}
.flow{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:20px}
.flow .step{font-family:"IBM Plex Mono",monospace;font-size:12.5px;background:var(--paper);border:1px solid var(--line2);
  border-radius:999px;padding:6px 13px;font-weight:500}
.flow .arr{color:var(--line2);font-size:14px}
.sgrid{display:grid;grid-template-columns:1fr 1fr;gap:16px 26px}
@media(max-width:720px){.sgrid{grid-template-columns:1fr}}
.sgrid h3{font-size:13px;margin:0 0 7px;color:var(--ink);font-weight:600;
  font-family:"IBM Plex Mono",monospace;letter-spacing:.02em}
.sgrid p{margin:0;font-size:13.7px;color:var(--muted);line-height:1.5}
.rules{display:flex;gap:10px;flex-wrap:wrap;margin-top:4px}
.rule{flex:1 1 220px;background:var(--paper);border:1px solid var(--line);border-left:3px solid var(--accent);
  border-radius:0 9px 9px 0;padding:11px 14px;font-size:13px;color:var(--muted)}
.rule b{color:var(--ink)}

/* toolbar */
.toolbar{display:flex;align-items:center;gap:10px;margin:30px 0 10px;
  position:sticky;top:0;z-index:5;padding:12px 0;background:linear-gradient(var(--paper) 78%,rgba(244,239,228,0))}
.toolbar .label{font-family:"IBM Plex Mono",monospace;font-size:11px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--muted);margin-right:auto}
.btn{font:12.5px/1 "IBM Plex Sans",sans-serif;background:var(--card);color:var(--ink);
  border:1px solid var(--line2);border-radius:8px;padding:7px 13px;cursor:pointer;transition:all .12s}
.btn:hover{border-color:var(--accent);color:var(--accent)}

/* sections (collapsible) */
details.sec{border:1px solid var(--line);border-radius:14px;margin:12px 0;background:var(--card);
  overflow:hidden;transition:box-shadow .15s,border-color .15s}
details.sec[open]{box-shadow:var(--shadow);border-color:var(--line2)}
details.sec.hide{display:none}
details.sec>summary{cursor:pointer;list-style:none;display:flex;align-items:center;gap:15px;
  padding:17px 22px;user-select:none}
details.sec>summary::-webkit-details-marker{display:none}
.sec .num{font-family:"IBM Plex Mono",monospace;font-weight:600;font-size:13px;color:#fff;
  background:var(--accent);min-width:30px;height:30px;display:grid;place-items:center;border-radius:8px}
.sec[open] .num{background:var(--ink)}
.sec .stitle{font-family:"Fraunces",Georgia,serif;font-size:22px;font-weight:600;flex:1;line-height:1.15}
.sec .chev{color:var(--muted);transition:transform .18s;font-size:13px}
.sec[open] .chev{transform:rotate(90deg)}
.sec .inner{padding:2px 24px 24px;border-top:1px solid var(--line);margin-top:0}
.sec .inner>*:first-child{margin-top:16px}

/* content typography inside sections */
.inner h3{font-size:15px;margin:1.5em 0 .4em;font-family:"IBM Plex Mono",monospace;letter-spacing:.01em}
.inner p{margin:.65em 0}
.inner ul,.inner ol{padding-left:1.4em}
.inner li{margin:.3em 0}
.inner blockquote{margin:1.1em 0;padding:.5em 1.1em;border-left:3px solid var(--line2);
  background:var(--paper);border-radius:0 8px 8px 0;color:var(--muted)}
.inner table{border-collapse:collapse;width:100%;margin:1.1em 0;font-size:14px;display:block;overflow-x:auto}
.inner th,.inner td{border:1px solid var(--line);padding:8px 12px;text-align:left;vertical-align:top}
.inner th{background:var(--paper2);font-family:"IBM Plex Mono",monospace;font-size:12px;
  letter-spacing:.03em;text-transform:uppercase;color:var(--muted)}
.inner tr:nth-child(even) td{background:#f6f1e6}

/* terminal command blocks */
.inner pre{position:relative;background:var(--term-bg);border-radius:11px;padding:16px 18px;
  margin:1.1em 0;overflow-x:auto;box-shadow:inset 0 0 0 1px rgba(255,255,255,.04)}
.inner pre code{background:none;border:0;padding:0;color:var(--term-ink);font-size:13px;line-height:1.62;
  display:block;font-family:"IBM Plex Mono",monospace}
.inner pre .copy{position:absolute;top:9px;right:9px;background:rgba(236,227,210,.1);color:#cabfa6;
  border:1px solid rgba(236,227,210,.16);border-radius:7px;padding:4px 9px;font:11px/1 "IBM Plex Mono",monospace;
  cursor:pointer;opacity:0;transition:opacity .14s,background .14s}
.inner pre:hover .copy{opacity:1}
.inner pre .copy:hover{background:rgba(236,227,210,.2);color:#fff}
.inner pre .copy.ok{color:#8fd6a3;border-color:#8fd6a3}

/* pills */
.pill{display:inline-block;font-family:"IBM Plex Mono",monospace;font-size:11px;font-weight:600;
  padding:1px 7px;border-radius:6px;vertical-align:middle;line-height:1.5}
.pill-free{background:#e4efe2;color:var(--free);border:1px solid #bcd8bf}

hr{border:0;border-top:1px solid var(--line);margin:1.6em 0}
.filter-empty{display:none;color:var(--muted);font-style:italic;padding:20px 4px}
mark{background:#f7e3a8;color:inherit;border-radius:2px;padding:0 1px}

@media(max-width:900px){
  .shell{grid-template-columns:1fr}
  .side{position:static;height:auto;border-right:0;border-bottom:1px solid var(--line);padding:22px}
  main{padding:26px 20px 70px}
  .masthead h1{font-size:31px}
}
"""

SUMMARY_HTML = """
<section class="summary" id="summary">
  <h2>At a glance</h2>
  <div class="flow">
    <span class="step">Orient</span><span class="arr">→</span>
    <span class="step">Onboard</span><span class="arr">→</span>
    <span class="step">Draft</span><span class="arr">→</span>
    <span class="step">Facilitate</span><span class="arr">→</span>
    <span class="step">View</span><span class="arr">→</span>
    <span class="step">Generate</span>
  </div>
  <div class="sgrid">
    <div>
      <h3>Greenfield (no schema/app)</h3>
      <p>Orient with <code>kickoff assess</code>, author the input package with
      <code>kickoff instantiate&nbsp;--apply</code>, then turn prose into a schema with
      <code>generate contract&nbsp;--promote</code>.</p>
    </div>
    <div>
      <h3>Brownfield (existing code)</h3>
      <p>Triage with <code>kickoff survey</code>, derive the contract from your models with
      <code>kickoff derive&nbsp;--apply</code>, then run the VIPP ground-truth loop
      (<code>vipp negotiate</code> → <code>apply</code>).</p>
    </div>
  </div>
  <div class="rules">
    <div class="rule"><b>$0 vs paid.</b> Almost everything is <span class="pill pill-free">$0</span>,
      deterministic, no&nbsp;LLM. Paid = <code>guided --agent</code>, <code>panel ask</code>, and the
      <code>--roles</code> passes. The CLI labels each.</div>
    <div class="rule"><b>Preview vs write.</b> Reads preview by default; writing needs
      <code>--apply</code> or an <code>approve</code> verb. Nothing runs your app or authors your content.</div>
  </div>
</section>
"""


def build() -> str:
    md = SRC.read_text(encoding="utf-8")
    intro_md, sections = split_sections(md)
    intro_html = markdown.markdown(intro_md, extensions=MD_EXT, output_format="html5")

    toc = []
    body_parts = []
    for i, s in enumerate(sections):
        num = s["num"] or "•"
        toc.append(
            f'<a href="#{s["slug"]}" data-slug="{s["slug"]}">'
            f'<span class="n">{html.escape(num)}</span>'
            f'<span>{plain(s["title"])}</span></a>'
        )
        open_attr = " open" if i == 0 else ""
        body_parts.append(
            f'<details class="sec" id="{s["slug"]}"{open_attr}>'
            f'<summary><span class="num">{html.escape(num)}</span>'
            f'<span class="stitle">{inline_md(s["title"])}</span>'
            f'<span class="chev">▶</span></summary>'
            f'<div class="inner">{render_body(s["body"])}</div>'
            f"</details>"
        )

    fonts = (
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link href="https://fonts.googleapis.com/css2?'
        "family=Fraunces:opsz,wght@9..144,500;9..144,600&"
        "family=IBM+Plex+Mono:wght@400;500;600&"
        'family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">'
    )

    js = r"""
(function(){
  // copy buttons on command blocks
  document.querySelectorAll('.inner pre').forEach(function(pre){
    var b=document.createElement('button'); b.className='copy'; b.textContent='copy';
    b.addEventListener('click',function(e){
      e.preventDefault();
      navigator.clipboard.writeText(pre.querySelector('code').innerText).then(function(){
        b.textContent='copied'; b.classList.add('ok');
        setTimeout(function(){b.textContent='copy';b.classList.remove('ok');},1400);
      });
    });
    pre.appendChild(b);
  });
  var secs=[].slice.call(document.querySelectorAll('details.sec'));
  var links=[].slice.call(document.querySelectorAll('nav.toc a'));
  function bySlug(s){return links.filter(function(l){return l.dataset.slug===s;})[0];}
  // expand / collapse all
  document.getElementById('exp').addEventListener('click',function(){secs.forEach(function(d){d.open=true;});});
  document.getElementById('col').addEventListener('click',function(){secs.forEach(function(d){d.open=false;});});
  // TOC click → open + scroll
  links.forEach(function(l){l.addEventListener('click',function(){
    var d=document.getElementById(l.dataset.slug); if(d) d.open=true;
  });});
  // open on hash
  if(location.hash){var d=document.getElementById(location.hash.slice(1)); if(d&&d.tagName==='DETAILS') d.open=true;}
  // scroll-spy
  var io=new IntersectionObserver(function(ents){
    ents.forEach(function(e){
      if(e.isIntersecting){
        links.forEach(function(l){l.classList.remove('active');});
        var a=bySlug(e.target.id); if(a) a.classList.add('active');
      }
    });
  },{rootMargin:'-15% 0px -75% 0px',threshold:0});
  secs.forEach(function(d){io.observe(d);});
  // live filter
  var f=document.getElementById('filter'), empty=document.getElementById('filter-empty');
  f.addEventListener('input',function(){
    var q=f.value.trim().toLowerCase(); var any=false;
    secs.forEach(function(d){
      // textContent (not innerText) so collapsed sections are still searchable
      var hit=!q||d.textContent.toLowerCase().indexOf(q)>-1;
      d.classList.toggle('hide',!hit);
      var a=bySlug(d.id); if(a) a.classList.toggle('hide',!hit);
      if(hit){any=true; if(q) d.open=true;}
    });
    empty.style.display=any?'none':'block';
  });
})();
"""

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>StartD8 Project Start — Team Guide</title>
{fonts}
<style>{CSS}</style></head>
<body>
<div class="shell">
  <aside class="side">
    <div class="brand">StartD8<span class="sub">Project-Start Field Manual</span></div>
    <div class="filter">
      <svg viewBox="0 0 24 24" stroke-width="2"><circle cx="11" cy="11" r="7"></circle><path d="M21 21l-4.3-4.3"></path></svg>
      <input id="filter" type="search" placeholder="Filter sections…" aria-label="Filter sections">
    </div>
    <nav class="toc">{''.join(toc)}</nav>
    <div class="side-foot">Rendered from <code>PROJECT_START_TEAM_GUIDE.md</code> — the source of
      truth. Regenerate with <code>scripts/render_project_start_guide.py</code>.</div>
  </aside>
  <main>
    <header class="masthead">
      <div class="kicker">StartD8 · Project Start</div>
      <h1>Project-Start Team Guide</h1>
      <div class="lede">{intro_html}</div>
    </header>
    {SUMMARY_HTML}
    <div class="toolbar">
      <span class="label">{len(sections)} sections</span>
      <button class="btn" id="exp">Expand all</button>
      <button class="btn" id="col">Collapse all</button>
    </div>
    {''.join(body_parts)}
    <div class="filter-empty" id="filter-empty">No sections match that filter.</div>
  </main>
</div>
<script>{js}</script>
</body></html>"""


def main() -> None:
    OUT.write_text(build(), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
