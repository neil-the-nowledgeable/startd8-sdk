"""Standalone, offline, dependency-free HTML template for the kickoff-panel viewer.

A single module-level constant with one ``__SESSION_JSON__`` placeholder that
:func:`startd8.kickoff_view.view.render_html` substitutes with escape-first JSON. The page
runs from ``file://`` with no CDN/build. Two-axis navigation (round × role) is a pure
client-side view transform over the identical entry set (FR-UX-4/5/6). The security helpers
(``esc`` / ``inline`` / ``renderMarkdown``) are the hardened consult webview helpers verbatim
(FR-UX-22): untrusted transcript text is escaped, then a whitelist Markdown renderer runs — a
``</script>`` inside any answer can never break out.
"""

WEBVIEW_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kickoff Panel — viewer</title>
<style>
  :root{
    --bg:#0e1116; --panel:#161b22; --panel2:#1c232d; --line:#2b3440;
    --ink:#e6edf3; --faint:#9aa7b4; --dim:#6b7684;
    --claude:#d98c5f; --gpt:#3fb27f; --gemini:#6ea8ff; --other:#b08cd9;
    --adv:#e5534b; --warn:#e3b341; --ok:#3fb27f;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
    font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
  a{color:var(--gemini)}
  .wrap{max-width:1100px;margin:0 auto;padding:0 20px 80px}
  .banner{background:linear-gradient(90deg,#3a2a12,#2a2410);border-bottom:1px solid var(--warn);
    color:var(--warn);padding:9px 20px;font-size:12.5px;text-align:center;position:sticky;top:0;z-index:20}
  .banner b{color:#f4d67a}
  header.top{padding:22px 0 8px}
  h1{font-size:18px;margin:0 0 3px;font-weight:600}
  .sid{color:var(--dim);font-size:12px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
  .meta-grid{display:grid;grid-template-columns:auto 1fr;gap:2px 14px;margin:12px 0;
    font-size:13px;color:var(--faint)}
  .meta-grid .k{color:var(--dim)}
  .fams{display:flex;gap:6px;flex-wrap:wrap;margin-top:4px}
  .toolbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;
    margin:14px 0 8px;padding:10px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
  .seg{display:inline-flex;border:1px solid var(--line);border-radius:7px;overflow:hidden}
  .seg button{background:var(--panel);color:var(--faint);border:0;padding:6px 13px;cursor:pointer;font-size:13px}
  .seg button.on{background:var(--panel2);color:var(--ink);font-weight:600}
  .btn{background:var(--panel);color:var(--faint);border:1px solid var(--line);border-radius:7px;
    padding:6px 11px;cursor:pointer;font-size:12.5px}
  .btn:hover{color:var(--ink)}
  .spacer{flex:1}
  .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin:14px 0}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:13px 15px}
  .card h3{margin:0 0 6px;font-size:12px;letter-spacing:.04em;text-transform:uppercase;color:var(--dim)}
  .card .md{font-size:13px;color:var(--faint)}
  .halt{background:#2a1414;border:1px solid var(--adv);border-radius:10px;padding:15px 18px;margin:16px 0;color:#f0b3ae}
  .halt b{color:#ff8b82}
  details.round,details.role{background:var(--panel);border:1px solid var(--line);border-radius:10px;margin:10px 0;overflow:hidden}
  details.round>summary,details.role>summary{cursor:pointer;padding:12px 15px;list-style:none;
    display:flex;align-items:center;gap:10px;user-select:none}
  summary::-webkit-details-marker{display:none}
  .fold{color:var(--dim);transition:transform .12s;display:inline-block;width:12px}
  details[open]>summary .fold{transform:rotate(90deg)}
  .rtitle{font-weight:600}
  .rkind{color:var(--dim);font-size:12px;font-family:ui-monospace,monospace}
  .prog{color:var(--faint);font-size:12px}
  .rbody{padding:2px 15px 12px}
  details.entry{border:1px solid var(--line);border-radius:8px;margin:8px 0;background:var(--panel2)}
  details.entry>summary{cursor:pointer;padding:9px 12px;list-style:none;display:flex;align-items:center;gap:9px;flex-wrap:wrap}
  .ename{font-weight:600}
  .emodel{color:var(--dim);font-size:12px;font-family:ui-monospace,monospace}
  .ebody{padding:2px 13px 12px}
  .answer{font-size:13.5px}
  .answer h1,.answer h2,.answer h3{font-size:14px;margin:11px 0 5px;color:var(--ink)}
  .answer p{margin:6px 0}
  .answer code{background:#0c1117;border:1px solid var(--line);border-radius:4px;padding:1px 5px;font-size:12px}
  .answer pre{background:#0c1117;border:1px solid var(--line);border-radius:7px;padding:11px;overflow:auto}
  .answer ul,.answer ol{margin:6px 0 6px 20px}
  .badge{display:inline-flex;align-items:center;gap:4px;font-size:11px;padding:2px 8px;border-radius:999px;
    border:1px solid var(--line);color:var(--faint);background:#0d1219}
  .badge .dot{width:7px;height:7px;border-radius:50%}
  .fam-Claude{border-color:var(--claude)} .fam-Claude .dot{background:var(--claude)}
  .fam-GPT{border-color:var(--gpt)} .fam-GPT .dot{background:var(--gpt)}
  .fam-Gemini{border-color:var(--gemini)} .fam-Gemini .dot{background:var(--gemini)}
  .fam-Other{border-color:var(--other)} .fam-Other .dot{background:var(--other)}
  .badge.adv{border-color:var(--adv);color:#f0918a;background:#1e1010}
  .badge.ground-grounded{color:var(--ok)} .badge.ground-uncertain{color:var(--warn)}
  .badge.ground-deferred,.badge.ground-unavailable{color:var(--dim)}
  .badge.synth{border-color:var(--warn);color:var(--warn)}
  .disc{margin-top:9px;border-top:1px dashed var(--line);padding-top:7px}
  .disc>summary{cursor:pointer;color:var(--dim);font-size:12px;list-style:none}
  .kv{display:grid;grid-template-columns:auto 1fr;gap:1px 12px;font-size:12px;color:var(--faint);margin:6px 0}
  .kv .k{color:var(--dim)}
  .promptbox{white-space:pre-wrap;background:#0c1117;border:1px solid var(--line);border-radius:7px;
    padding:10px;font-size:12px;color:var(--faint);max-height:340px;overflow:auto;margin-top:6px}
  section.synth{margin-top:22px}
  section.synth h2{font-size:15px;border-bottom:1px solid var(--line);padding-bottom:6px}
  .tensions{background:#1a1508;border:1px solid var(--warn);border-radius:9px;padding:10px 14px;margin:12px 0;color:#e8cf94}
  footer{margin-top:34px;padding-top:14px;border-top:1px solid var(--line);color:var(--dim);font-size:12px}
  .empty{color:var(--dim);padding:18px 0;font-style:italic}
</style>
</head>
<body>
<div class="banner">⚠ <b>SYNTHETIC PANEL</b> — every persona output below is model-generated and
  <b>unratified</b>. Observe and navigate only; nothing here is a decision.</div>
<div class="wrap">
  <header class="top">
    <h1 id="proj">Kickoff Panel</h1>
    <div class="sid" id="sid"></div>
    <div class="meta-grid" id="meta"></div>
    <div class="fams" id="fams"></div>
  </header>

  <div class="toolbar">
    <span class="seg" role="tablist" aria-label="navigation axis">
      <button id="ax-round" class="on" aria-pressed="true">By round</button>
      <button id="ax-role" aria-pressed="false">By role</button>
    </span>
    <span class="spacer"></span>
    <button class="btn" id="expand-all">Expand all</button>
    <button class="btn" id="collapse-all">Collapse all</button>
  </div>

  <div id="prep"></div>
  <div id="halt"></div>
  <div id="main"></div>
  <div id="synth"></div>

  <footer>
    <div id="foot"></div>
    <div style="margin-top:5px">Read-only viewer · re-rendering is $0 · transcript is the source of truth.</div>
  </footer>
</div>

<!-- Embedded transcript (application/json is never executed; render_html escapes "<" on embed). -->
<script type="application/json" id="session-data">
__SESSION_JSON__
</script>

<script>
(function(){
  "use strict";

  // ---- security: escape-first, then a whitelist markdown renderer (FR-UX-22, verbatim consult) ----
  function esc(s){
    return String(s==null?"":s)
      .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
      .replace(/"/g,"&quot;").replace(/'/g,"&#39;");
  }
  function inline(escaped){
    return escaped
      .replace(/`([^`]+)`/g,'<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>')
      .replace(/(^|[^*])\*([^*\n]+)\*/g,'$1<em>$2</em>')
      .replace(/_([^_\n]+)_/g,'<em>$1</em>');
  }
  function renderMarkdown(raw){
    var src=String(raw==null?"":raw);
    var lines=src.replace(/\r\n?/g,"\n").split("\n");
    var out=[],i=0;
    function flushList(tag,items){ if(items.length){ out.push("<"+tag+">"+items.map(function(x){return "<li>"+inline(x)+"</li>";}).join("")+"</"+tag+">"); } }
    while(i<lines.length){
      var ln=lines[i];
      if(/^```/.test(ln)){ var buf=[]; i++; while(i<lines.length && !/^```/.test(lines[i])){ buf.push(esc(lines[i])); i++; } i++; out.push("<pre><code>"+buf.join("\n")+"</code></pre>"); continue; }
      var h=/^(#{1,3})\s+(.*)$/.exec(ln);
      if(h){ var lvl=h[1].length; out.push("<h"+lvl+">"+inline(esc(h[2]))+"</h"+lvl+">"); i++; continue; }
      if(/^\s*\d+\.\s+/.test(ln)){ var oi=[]; while(i<lines.length && /^\s*\d+\.\s+/.test(lines[i])){ oi.push(esc(lines[i].replace(/^\s*\d+\.\s+/,""))); i++; } flushList("ol",oi); continue; }
      if(/^\s*[-*]\s+/.test(ln)){ var ui=[]; while(i<lines.length && /^\s*[-*]\s+/.test(lines[i])){ ui.push(esc(lines[i].replace(/^\s*[-*]\s+/,""))); i++; } flushList("ul",ui); continue; }
      if(/^\s*$/.test(ln)){ i++; continue; }
      var para=[]; while(i<lines.length && !/^\s*$/.test(lines[i]) && !/^(#{1,3}\s|```|\s*[-*]\s|\s*\d+\.\s)/.test(lines[i])){ para.push(esc(lines[i])); i++; }
      out.push("<p>"+inline(para.join(" "))+"</p>");
    }
    return out.join("");
  }

  function el(tag,cls){ var e=document.createElement(tag); if(cls) e.className=cls; return e; }
  function famClass(f){ return "fam-"+(f==="Claude"||f==="GPT"||f==="Gemini"?f:"Other"); }
  function fmtCost(v){ return (v==null||v===0)?"not recorded":("$"+Number(v).toFixed(4)); }

  var data;
  try{ data=JSON.parse(document.getElementById("session-data").textContent); }
  catch(e){ document.getElementById("main").textContent="Could not parse transcript data."; return; }

  // ---- header ----
  document.getElementById("proj").textContent="Kickoff Panel — "+(data.project||"(unknown project)");
  document.getElementById("sid").textContent=data.session_id||"";
  document.getElementById("foot").textContent="session "+(data.session_id||"—")+"  ·  created "+(data.created_at||"—");
  var meta=document.getElementById("meta");
  function metaRow(k,v){ if(v==null||v==="") return; var kk=el("div","k"); kk.textContent=k; var vv=el("div"); vv.textContent=v; meta.append(kk,vv); }
  metaRow("objective",data.objective);
  metaRow("strategy",data.strategy);
  metaRow("facilitator",data.facilitator_model);
  metaRow("cost",fmtCost(data.cost_total_usd));
  if(data.status) metaRow("status",data.status);
  var fams=document.getElementById("fams");
  var dist=data.family_distribution||{};
  Object.keys(dist).forEach(function(f){
    var b=el("span","badge "+famClass(f)); var d=el("span","dot"); b.appendChild(d);
    b.appendChild(document.createTextNode(f+" ×"+dist[f])); fams.appendChild(b);
  });

  // ---- prep cards (FR-UX-12) ----
  var prep=data.prep;
  if(prep){
    var cards=el("div","cards");
    [["Grounded context",prep.grounded_context],["Key assumptions",prep.key_assumptions],["Outside view",prep.outside_view]].forEach(function(pair){
      if(!pair[1]) return;
      var c=el("div","card"); var h=el("h3"); h.textContent=pair[0]; var m=el("div","md"); m.innerHTML=renderMarkdown(pair[1]);
      c.append(h,m); cards.appendChild(c);
    });
    if(cards.children.length) document.getElementById("prep").appendChild(cards);
  }

  // ---- halted state (FR-UX-14): prep + banner, no rounds ----
  if(data.is_halted){
    var hb=el("div","halt"); var hh=el("b"); hh.textContent="Panel halted after R0 — validate the premise first.";
    hb.appendChild(hh);
    var msg=(data.halt&&(data.halt.message||data.halt.reason))||"";
    if(msg){ var p=el("div"); p.style.marginTop="6px"; p.textContent=msg; hb.appendChild(p); }
    document.getElementById("halt").appendChild(hb);
  }

  // ---- shared entry renderer (both axes reuse it, FR-UX-5/7) ----
  function badge(cls,txt,withDot){ var b=el("span","badge "+cls); if(withDot){ b.appendChild(el("span","dot")); } b.appendChild(document.createTextNode(txt)); return b; }
  function buildEntry(entry,roundLabel){
    var det=el("details","entry"); det.open=false;
    var sum=el("summary");
    var fold=el("span","fold"); fold.textContent="▸"; fold.setAttribute("aria-hidden","true");
    var nm=el("span","ename"); nm.textContent=entry.display_name||entry.role_id||"(role)";
    var md=el("span","emodel"); md.textContent=entry.model||"";
    sum.append(fold,nm,md);
    sum.appendChild(badge(famClass(entry.family),entry.family||"Other",true));
    if(entry.is_adversary) sum.appendChild(badge("adv","adversary",false));
    if(entry.grounding) sum.appendChild(badge("ground-"+entry.grounding,entry.grounding,false));
    (entry.flags||[]).forEach(function(f){ sum.appendChild(badge("","⚑ "+f,false)); });
    if(roundLabel){ var rl=el("span","emodel"); rl.textContent="· "+roundLabel; sum.appendChild(rl); }
    det.appendChild(sum);

    var body=el("div","ebody");
    var ans=el("div","answer"); ans.innerHTML=renderMarkdown(entry.text||"(no answer recorded)");
    body.appendChild(ans);

    // secondary disclosure: prompt + usage, collapsed by default (FR-UX-7)
    var disc=el("details","disc"); var ds=el("summary"); ds.textContent="prompt & usage"; disc.appendChild(ds);
    var kv=el("div","kv");
    function kvrow(k,v){ if(v==null) return; var a=el("div","k"); a.textContent=k; var b=el("div"); b.textContent=v; kv.append(a,b); }
    kvrow("model",entry.model); kvrow("grounding",entry.grounding);
    kvrow("input tokens",entry.input_tokens); kvrow("output tokens",entry.output_tokens);
    kvrow("cost",fmtCost(entry.cost_usd));
    disc.appendChild(kv);
    if(entry.prompt){ var pb=el("div","promptbox"); pb.textContent=entry.prompt; disc.appendChild(pb); }
    body.appendChild(disc);
    det.appendChild(body);
    return det;
  }

  var main=document.getElementById("main");
  var rounds=data.rounds||[];
  var rosterSize=data.roster_size||0;

  function renderRoundMajor(){
    main.innerHTML="";
    if(!rounds.length){ var e=el("div","empty"); e.textContent="No rounds recorded yet."; main.appendChild(e); return; }
    rounds.forEach(function(rnd){
      var det=el("details","round"); det.open=true;
      var sum=el("summary");
      var fold=el("span","fold"); fold.textContent="▸"; fold.setAttribute("aria-hidden","true");
      var t=el("span","rtitle"); t.textContent=(rnd.round_id||"")+" · "+(rnd.title||"(untitled round)");
      var k=el("span","rkind"); k.textContent=rnd.kind||"";
      var denom=rosterSize||rnd.entry_count;
      var pr=el("span","prog"); pr.textContent=rnd.entry_count+"/"+denom+" roles";
      sum.append(fold,t,k,pr); det.appendChild(sum);
      var body=el("div","rbody");
      (rnd.entries||[]).forEach(function(en){ body.appendChild(buildEntry(en,null)); });
      det.appendChild(body); main.appendChild(det);
    });
  }

  function renderRoleMajor(){
    main.innerHTML="";
    // group the identical entry set by role_id (pure view transform, FR-UX-5)
    var order=[]; var byRole={};
    rounds.forEach(function(rnd){
      (rnd.entries||[]).forEach(function(en){
        var key=en.role_id||en.display_name||"(role)";
        if(!byRole[key]){ byRole[key]=[]; order.push(key); }
        byRole[key].push({round:rnd,entry:en});
      });
    });
    if(!order.length){ var e=el("div","empty"); e.textContent="No entries recorded yet."; main.appendChild(e); return; }
    order.forEach(function(key){
      var pairs=byRole[key]; var first=pairs[0].entry;
      var det=el("details","role"); det.open=true;
      var sum=el("summary");
      var fold=el("span","fold"); fold.textContent="▸"; fold.setAttribute("aria-hidden","true");
      var t=el("span","rtitle"); t.textContent=first.display_name||key;
      var md=el("span","rkind"); md.textContent=first.model||"";
      sum.append(fold,t,md);
      sum.appendChild(badge(famClass(first.family),first.family||"Other",true));
      if(first.is_adversary) sum.appendChild(badge("adv","adversary",false));
      var pr=el("span","prog"); pr.textContent=pairs.length+" rounds";
      sum.appendChild(pr); det.appendChild(sum);
      var body=el("div","rbody");
      pairs.forEach(function(p){ body.appendChild(buildEntry(p.entry,(p.round.round_id||"")+" "+(p.round.title||""))); });
      det.appendChild(body); main.appendChild(det);
    });
  }

  var axis="round";
  function setAxis(a){
    axis=a;
    var r=document.getElementById("ax-round"), ro=document.getElementById("ax-role");
    r.classList.toggle("on",a==="round"); r.setAttribute("aria-pressed",a==="round");
    ro.classList.toggle("on",a==="role"); ro.setAttribute("aria-pressed",a==="role");
    if(a==="round") renderRoundMajor(); else renderRoleMajor();
  }
  document.getElementById("ax-round").addEventListener("click",function(){ setAxis("round"); });
  document.getElementById("ax-role").addEventListener("click",function(){ setAxis("role"); });

  // expand/collapse all — operates on the top-level round/role sections (FR-UX-6)
  function setAll(open){ document.querySelectorAll("#main > details").forEach(function(d){ d.open=open; }); }
  document.getElementById("expand-all").addEventListener("click",function(){ setAll(true); });
  document.getElementById("collapse-all").addEventListener("click",function(){ setAll(false); });

  // ---- synthesis (FR-UX-15/16): prose-primary, unresolved tensions preserved ----
  var synth=data.synthesis;
  if(synth && (synth.text || (synth.open_tension_ids||[]).length)){
    var sec=el("section","synth");
    var h=el("h2"); h.textContent="Synthesis — needs your judgment"; sec.appendChild(h);
    sec.appendChild(badge("synth","synthetic · unratified",false));
    if((synth.open_tension_ids||[]).length){
      var tb=el("div","tensions");
      var tt=el("b"); tt.textContent="Unresolved tensions (preserved, not smoothed): "; tb.appendChild(tt);
      tb.appendChild(document.createTextNode((synth.open_tension_ids||[]).join(", ")));
      sec.appendChild(tb);
    }
    if(synth.text){ var body=el("div","answer"); body.innerHTML=renderMarkdown(synth.text); sec.appendChild(body); }
    document.getElementById("synth").appendChild(sec);
  }

  setAxis("round");
})();
</script>
</body>
</html>
"""
