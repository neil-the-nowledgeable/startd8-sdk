"""Self-contained HTML shell for the wireframe-visual preview (FR-WV-1/2/3/4, FR-AUD).

ONE offline page — embedded CSS + JS, no CDN, no build. The composed view-model is injected once at
``__PLAN_DATA__`` inside a ``<script type="application/json">`` container (escape-first on embed —
:func:`view._embed_json` neutralizes ``<`` so a ``</script>`` in any label can't break out). The client
reads it (``textContent`` → ``JSON.parse``) and renders.

Design: a calm "warm editorial blueprint" — a document the non-technical author *reviews*, not a tool
that narrates itself. The end_user surface leads with a benefit-first, actionable intro (what to do and
why — R2-F2), shows a plain at-a-glance strip, then progressively-disclosed sections whose headers flag
"needs you" where the author's attention is required (R2-F5). No filesystem paths or build-pipeline
framing reach the end_user (R2-F1); a11y baseline: semantic landmarks, ``lang``, reduced-motion respect.

``__EXPECTED_SCHEMA__`` is substituted from :data:`view.EXPECTED_SCHEMA_VERSION` (FR-AUD-7 client guard).
"""

WIREFRAME_VIEW_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Your app — a first look</title>
<style>
  :root{
    --paper:#f4efe4; --card:#fffdf6; --card2:#fbf7ec;
    --ink:#241f17; --ink2:#5d5545; --faint:#8b8270;
    --line:#e3dcca; --line2:#d3c9b2;
    --accent:#1b545f; --accent2:#2b7382; --accent-wash:#e9f0ef;
    --ochre:#a2661b; --ochre-ink:#7a4c11; --ochre-wash:#fbf1dd;
    --planned:#3d7a57; --defaults:#3a6a94; --placeholder:#a9781a; --not_defined:#948b78; --invalid:#ab473a;
    --serif:"Iowan Old Style","Palatino Linotype",Palatino,"Book Antiqua",Georgia,"Times New Roman",serif;
    --sans:"Avenir Next",Avenir,"Segoe UI",-apple-system,BlinkMacSystemFont,system-ui,"Helvetica Neue",sans-serif;
    --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
  }
  *{box-sizing:border-box}
  html{-webkit-text-size-adjust:100%}
  body{
    margin:0;color:var(--ink);font-family:var(--sans);font-size:15px;line-height:1.58;
    background-color:var(--paper);
    background-image:radial-gradient(var(--line2) 0.7px, transparent 0.7px);
    background-size:22px 22px;background-position:-11px -11px;
  }
  .wrap{max-width:760px;margin:0 auto;padding:0 22px 96px}
  ::selection{background:var(--accent);color:#fff}

  /* ---------- masthead / intro ---------- */
  .mast{padding:56px 0 8px}
  .eyebrow{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);
    font-weight:700;margin-bottom:14px}
  .eyebrow .dot{opacity:.5;margin:0 8px}
  .headline{font-family:var(--serif);font-weight:600;font-size:33px;line-height:1.16;letter-spacing:-.01em;
    margin:0 0 14px;color:var(--ink)}
  .lead{font-size:16.5px;color:var(--ink2);margin:0 0 22px;max-width:60ch}
  ol.steps{list-style:none;counter-reset:s;margin:0;padding:0;display:grid;gap:10px}
  ol.steps li{counter-increment:s;position:relative;padding:11px 14px 11px 46px;background:var(--card);
    border:1px solid var(--line);border-radius:10px;font-size:14px;color:var(--ink)}
  ol.steps li::before{content:counter(s);position:absolute;left:11px;top:50%;transform:translateY(-50%);
    width:24px;height:24px;border-radius:50%;background:var(--accent);color:#fff;font-family:var(--serif);
    font-size:14px;display:flex;align-items:center;justify-content:center}

  /* architect intro fallback */
  .meta{color:var(--ink2);font-size:13px;margin:3px 0}
  .whybox{font-size:13.5px;color:var(--ink2);background:var(--card);border:1px solid var(--line);
    border-radius:10px;padding:12px 14px;margin-top:14px}
  .whybox b{color:var(--accent);font-weight:700}

  /* ---------- at-a-glance strip ---------- */
  .glance{display:grid;grid-template-columns:repeat(2,1fr);gap:1px;margin:26px 0 6px;
    background:var(--line);border:1px solid var(--line);border-radius:12px;overflow:hidden}
  .glance .cell{background:var(--card);padding:13px 16px}
  .glance .k{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--faint);font-weight:700;
    margin-bottom:3px}
  .glance .v{font-size:14px;color:var(--ink);font-weight:500}

  .rule{height:1px;background:var(--line2);margin:30px 0 22px;border:0}
  .controls{margin:0 0 16px;display:flex;gap:9px;align-items:center}
  .controls button{font:inherit;font-size:12.5px;color:var(--ink2);border:1px solid var(--line2);
    background:var(--card);border-radius:20px;padding:5px 13px;cursor:pointer}
  .controls button:hover{border-color:var(--accent);color:var(--accent)}
  .section-lead{font-family:var(--serif);font-size:13px;letter-spacing:.02em;color:var(--faint);
    text-transform:uppercase;margin:0 0 12px}

  /* ---------- sections (progressive disclosure) ---------- */
  details.sec{background:var(--card);border:1px solid var(--line);border-radius:13px;margin:11px 0;
    overflow:hidden;transition:border-color .15s, box-shadow .15s}
  details.sec[open]{border-color:var(--line2);box-shadow:0 6px 22px -14px rgba(40,32,16,.4)}
  details.sec>summary{list-style:none;cursor:pointer;padding:16px 18px;display:flex;align-items:baseline;
    gap:11px;outline:none}
  details.sec>summary::-webkit-details-marker{display:none}
  details.sec>summary:focus-visible{box-shadow:inset 0 0 0 2px var(--accent-wash)}
  .chev{align-self:center;color:var(--faint);font-size:10px;transition:transform .15s;flex:none}
  details.sec[open] .chev{transform:rotate(90deg)}
  .sec-title{font-family:var(--serif);font-size:18px;font-weight:600;color:var(--ink);flex:none}
  .sec-one{font-size:13px;color:var(--ink2);flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;
    white-space:nowrap}
  .needs{flex:none;font-size:11px;font-weight:700;color:var(--ochre-ink);background:var(--ochre-wash);
    border:1px solid #ecd9ad;border-radius:20px;padding:2px 10px}
  .allset{flex:none;font-size:11px;color:var(--planned);font-weight:600}
  .dot{flex:none;width:9px;height:9px;border-radius:50%;align-self:center}
  .d-planned{background:var(--planned)}.d-defaults{background:var(--defaults)}
  .d-placeholder{background:var(--placeholder)}.d-not_defined{background:var(--not_defined)}
  .d-invalid{background:var(--invalid)}

  .sec-body{padding:2px 18px 18px}
  .narr{margin:6px 0 14px}
  .narr .r{display:grid;grid-template-columns:118px 1fr;gap:12px;padding:7px 0;border-top:1px solid var(--line)}
  .narr .r:first-child{border-top:0}
  .narr .lab{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--faint);font-weight:700;
    padding-top:2px}
  .narr .r.need .lab{color:var(--ochre-ink)}
  .narr .r.need{background:linear-gradient(90deg,var(--ochre-wash),transparent);border-radius:8px;
    padding-left:8px;margin-left:-8px}
  .narr .txt{color:var(--ink);font-size:14px}
  .narr .r.wont .txt{color:var(--ink2)}

  .needlist{font-size:13px;color:var(--ochre-ink);background:var(--ochre-wash);border:1px solid #ecd9ad;
    border-radius:9px;padding:9px 12px;margin:0 0 12px}
  .needlist b{font-weight:700}

  /* ---------- items ---------- */
  .item{border-top:1px solid var(--line);padding:10px 0}
  .item:first-child{border-top:0}
  .item .row{display:flex;align-items:center;gap:9px}
  .item .lbl{font-weight:600;font-size:14px}
  .item .det{color:var(--ink2);font-size:12px;font-family:var(--mono);margin:4px 0 0 1px}
  .badge{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;padding:2px 8px;
    border-radius:20px;color:#fff;white-space:nowrap}
  .b-planned{background:var(--planned)}.b-defaults{background:var(--defaults)}
  .b-placeholder{background:var(--placeholder)}.b-not_defined{background:var(--not_defined)}
  .b-invalid{background:var(--invalid)}
  .drill{margin-left:auto;font:inherit;font-size:12px;color:var(--accent);border:1px solid var(--line2);
    background:var(--card2);border-radius:20px;padding:3px 12px;cursor:pointer}
  .drill:hover{border-color:var(--accent)}

  /* ---------- lo-fi mockups ---------- */
  .mock{margin:11px 0 3px;border:1.5px solid var(--line2);border-radius:11px;background:#fff;overflow:hidden}
  .mock .chrome{background:var(--card2);border-bottom:1.5px solid var(--line2);padding:7px 12px;font-size:12px;
    color:var(--ink2);display:flex;align-items:center;gap:6px;font-family:var(--serif)}
  .mock .cdot{width:9px;height:9px;border-radius:50%;background:var(--line2)}
  .mock .nav{display:flex;gap:8px;padding:9px 12px;border-bottom:1px solid var(--line);flex-wrap:wrap}
  .mock .nav span{font-size:12px;color:var(--ink2);border:1px solid var(--line);border-radius:6px;
    padding:2px 9px;background:var(--card2)}
  .mock .body{padding:14px 16px}
  .fld{display:grid;grid-template-columns:140px 1fr;gap:10px;align-items:center;margin:9px 0}
  .fld label{font-size:13px;color:var(--ink)}
  .fld .box{height:30px;border:1.5px solid var(--line2);border-radius:7px;background:var(--card2)}
  .fld.area .box{height:60px}
  .omit{margin-top:13px;font-size:12px;color:var(--ink2);border-top:1px solid var(--line);padding-top:10px}
  .omit .tag{display:inline-block;border:1px solid var(--line);border-radius:6px;padding:1px 8px;margin:3px 5px 0 0;
    background:var(--card2)}
  .acts{margin-top:14px;display:flex;gap:9px}
  .acts .btn{border:1.5px solid var(--line2);border-radius:8px;padding:6px 16px;font-size:13px;
    background:var(--card2);color:var(--ink2)}
  .acts .btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}
  .mock table.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
  .mock table.tbl th,.mock table.tbl td{border:1px solid var(--line);padding:6px 9px;text-align:left}
  .mock table.tbl th{background:var(--card2);color:var(--ink2);font-weight:600}
  .mock .skel{height:9px;background:var(--line);border-radius:3px;opacity:.7}

  /* ---------- closing / misc ---------- */
  .closing{margin:34px 0 0;background:var(--accent-wash);border:1px solid #cfe0de;border-radius:13px;
    padding:20px 22px;font-size:15px;color:var(--ink)}
  .closing b{font-family:var(--serif);font-weight:600;display:block;font-size:17px;margin-bottom:6px;color:var(--accent)}
  .banner{background:var(--ochre-wash);border:1px solid #ecd9ad;border-radius:10px;padding:11px 14px;
    margin:16px 0;font-size:13.5px;color:var(--ochre-ink)}
  .empty{color:var(--faint);font-size:13px;font-style:italic}

  /* ---------- QW-3 to-do roll-up · QW-1 toggle · QW-5 legend ---------- */
  .todos-box{background:var(--ochre-wash);border:1px solid #ecd9ad;border-radius:12px;padding:14px 16px;
    margin:18px 0 0;font-size:14px;color:var(--ink)}
  .todos-box b{color:var(--ochre-ink)} .todos-box ul{margin:6px 0 0;padding-left:20px} .todos-box li{margin:3px 0}
  .toolbar{display:flex;align-items:center;gap:12px;margin:22px 0 6px;flex-wrap:wrap}
  .toolbar .tg{font-size:11px;color:var(--faint);text-transform:uppercase;letter-spacing:.07em;font-weight:700}
  .toolbar select{font:inherit;font-size:13px;text-transform:none;letter-spacing:0;color:var(--ink);
    border:1px solid var(--line2);background:var(--card);border-radius:8px;padding:4px 9px;margin-left:6px}
  .toolbar button{font:inherit;font-size:12.5px;color:var(--ink2);border:1px solid var(--line2);
    background:var(--card);border-radius:20px;padding:5px 13px;cursor:pointer}
  .toolbar button:hover{border-color:var(--accent);color:var(--accent)}
  .legend{display:flex;gap:16px;flex-wrap:wrap;font-size:11.5px;color:var(--faint);margin:0 0 2px}
  .legend span{display:flex;align-items:center;gap:5px}
  .legend i{width:9px;height:9px;border-radius:50%;display:inline-block}

  /* ---------- EC-4: delivery-role lens banner ---------- */
  .lens-banner{margin:12px 0 0;background:var(--accent-wash);border:1px solid #cfe0de;border-radius:11px;
    padding:10px 15px;font-size:13.5px;color:var(--ink);line-height:1.5}
  .lens-banner b{color:var(--accent);font-family:var(--serif);font-weight:600}
  .lens-banner .lens-eyebrow{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--accent);
    font-weight:700;margin-right:8px}

  /* ---------- EC-2: per-section sign-off (approve / flag / annotate) ---------- */
  .sig-mark{flex:none;font-size:12px;font-weight:700}
  .sig-mark.ok{color:var(--planned)} .sig-mark.flag{color:var(--ochre-ink)}
  .signoff{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:14px 0 2px;padding-top:12px;
    border-top:1px dashed var(--line2)}
  .signoff .slab{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--faint);font-weight:700}
  .signoff button{font:inherit;font-size:12.5px;color:var(--ink2);border:1px solid var(--line2);background:var(--card);
    border-radius:20px;padding:4px 12px;cursor:pointer}
  .signoff button:hover{border-color:var(--accent);color:var(--accent)}
  .signoff button.on-ok{background:var(--planned);border-color:var(--planned);color:#fff}
  .signoff button.on-flag{background:var(--ochre);border-color:var(--ochre);color:#fff}
  .signoff .so-note{display:none;flex-basis:100%;width:100%;margin-top:4px;font:inherit;font-size:13px;color:var(--ink);
    border:1px solid var(--line2);border-radius:8px;padding:8px 10px;background:var(--card2);resize:vertical;min-height:42px}
  .signoff.flagged .so-note{display:block}
  .signbar{display:flex;align-items:center;gap:10px;margin:20px 0 0;background:var(--card);border:1px solid var(--line);
    border-radius:12px;padding:11px 15px;font-size:13.5px;color:var(--ink2)}
  .signbar b{color:var(--accent)}
  .signbar button{margin-left:auto;font:inherit;font-size:12.5px;color:#fff;background:var(--accent);
    border:1px solid var(--accent);border-radius:20px;padding:6px 15px;cursor:pointer}
  .signbar button:hover{background:var(--accent2)}

  /* ---------- motion ---------- */
  @keyframes rise{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
  .mast,.glance,.rule,.toolbar,.section-lead,details.sec,.closing{animation:rise .5s cubic-bezier(.2,.7,.2,1) both}
  .glance{animation-delay:.05s}.rule{animation-delay:.08s}.toolbar{animation-delay:.1s}
  #outline>details.sec:nth-child(1){animation-delay:.12s}
  #outline>details.sec:nth-child(2){animation-delay:.16s}
  #outline>details.sec:nth-child(3){animation-delay:.20s}
  #outline>details.sec:nth-child(4){animation-delay:.24s}
  #outline>details.sec:nth-child(5){animation-delay:.28s}
  #outline>details.sec:nth-child(n+6){animation-delay:.32s}
  @media (prefers-reduced-motion: reduce){*{animation:none !important}}
  @media (max-width:560px){.glance{grid-template-columns:1fr}.headline{font-size:27px}
    .narr .r{grid-template-columns:1fr;gap:2px}.fld{grid-template-columns:1fr;gap:3px}}
</style>
</head>
<body>
<div class="wrap">
  <header class="mast" id="mast"></header>
  <div id="warn" role="status"></div>
  <section class="glance" id="glance" aria-label="At a glance"></section>
  <div id="todos"></div>
  <div class="toolbar" id="toolbar"></div>
  <div class="legend" id="legend"></div>
  <div class="lens-banner" id="lens" hidden></div>
  <hr class="rule">
  <p class="section-lead" id="seclead">What your app includes</p>
  <main id="outline"></main>
  <div class="signbar" id="signbar"></div>
  <footer class="closing" id="closing" hidden></footer>
</div>

<!-- Embedded view-model (application/json is never executed; view.render_html escapes "<" on embed). -->
<script type="application/json" id="plan-data">
__PLAN_DATA__
</script>

<script>
(function(){
  "use strict";
  var EXPECTED_SCHEMA = __EXPECTED_SCHEMA__;
  var payload;
  try { payload = JSON.parse(document.getElementById("plan-data").textContent); }
  catch(e){ document.getElementById("outline").innerHTML =
    '<div class="banner">Could not read the preview data.</div>'; return; }
  var VARS = payload.variants || {}, cur = payload.default;   // QW-1: embedded audience variants
  var KITS = payload.kits || {};                              // EC-4: delivery-role kits (overlay metadata)
  var data, EU, s;   // (re)set by renderAll() for the currently-selected variant

  // EC-4: which base voice a role renders as (a kit → its declared base; a base voice → itself).
  function voiceOf(role){ return (KITS[role] && KITS[role].base) || role; }
  // EC-4: resolve a "role|fluency" key to an embedded view-model — a kit falls back to its base voice's
  // variant (kits carry no embedded variant of their own; they render base voice + a lens banner).
  function resolveVM(key){
    if(VARS[key]) return VARS[key];
    var p=key.split("|"), role=p[0], flu=p[1]||"intermediate", kit=KITS[role];
    if(kit) return VARS[kit.base+"|"+flu] || VARS[kit.base+"|intermediate"];
    return VARS[payload.default] || VARS[Object.keys(VARS)[0]];
  }

  function esc(s){ return String(s==null?"":s)
    .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
    .replace(/"/g,"&quot;").replace(/'/g,"&#39;"); }
  function el(html){ var t=document.createElement("template"); t.innerHTML=html.trim(); return t.content.firstChild; }
  function badge(st){ return '<span class="badge b-'+esc(st)+'">'+esc(String(st).replace(/_/g," "))+'</span>'; }

  // ---------- EC-2: per-section sign-off (approve / flag), persisted client-side ----------
  // The preview's verb is *approve*: the owner marks each section "looks right" or flags it with a note.
  // State lives in localStorage keyed by the app name (survives reload, offline); it is never in the
  // rendered file (determinism preserved) and can be exported as JSON to feed the kickoff loop.
  var APP="app", SKEY="", SIGN={};
  function loadSign(){ try{ return JSON.parse(localStorage.getItem(SKEY))||{}; }catch(e){ return SIGN||{}; } }
  function saveSign(){ try{ localStorage.setItem(SKEY,JSON.stringify(SIGN)); }catch(e){} }  // degrade: in-memory
  function paintMark(mk,key){ var st=(SIGN[key]||{}).status;
    mk.className="sig-mark"+(st?(" "+st):""); mk.textContent=(st==="ok")?"✓":(st==="flag")?"⚑":""; }
  function signRow(sec,mk){
    var w=document.createElement("div"); var st0=SIGN[sec.key]||{};
    w.className="signoff"+(st0.status==="flag"?" flagged":"");
    w.innerHTML='<span class="slab">Your call</span>'+
      '<button type="button" class="so-ok'+(st0.status==="ok"?" on-ok":"")+'">✓ Looks right</button>'+
      '<button type="button" class="so-flag'+(st0.status==="flag"?" on-flag":"")+'">⚑ Flag this</button>'+
      '<textarea class="so-note" placeholder="What should change here? (optional)"></textarea>';
    var ta=w.querySelector(".so-note"), ok=w.querySelector(".so-ok"), fl=w.querySelector(".so-flag");
    ta.value=st0.note||"";
    function set(status){
      var cur=SIGN[sec.key]||{};
      if(cur.status===status) delete SIGN[sec.key];                       // click the active choice → clear
      else SIGN[sec.key]={status:status, note:(status==="flag")?(cur.note||ta.value||""):""};
      saveSign();
      var now=SIGN[sec.key]||{};
      ok.classList.toggle("on-ok", now.status==="ok");
      fl.classList.toggle("on-flag", now.status==="flag");
      w.classList.toggle("flagged", now.status==="flag");
      paintMark(mk,sec.key); renderSignbar();
    }
    ok.onclick=function(){ set("ok"); };
    fl.onclick=function(){ set("flag"); };
    ta.oninput=function(){ var c=SIGN[sec.key]; if(c&&c.status==="flag"){ c.note=ta.value; saveSign(); } };
    return w;
  }
  function renderSignbar(){
    var secs=(data.sections||[]), n=secs.length, done=0, fl=0;
    secs.forEach(function(x){ var st=(SIGN[x.key]||{}).status; if(st==="ok"){done++;} else if(st==="flag"){done++;fl++;} });
    var bar=document.getElementById("signbar");
    bar.innerHTML='<span>Your sign-off: <b>'+done+'</b> of '+n+' reviewed'+
      (fl?' · <b style="color:var(--ochre-ink)">'+fl+' flagged</b>':'')+'</span>'+
      '<button type="button" id="so-export">Export sign-off</button>';
    document.getElementById("so-export").onclick=exportSign;
  }
  function exportSign(){
    var rows=(data.sections||[]).map(function(x){ var st=SIGN[x.key]||{};
      return {key:x.key, title:x.title, status:st.status||"unreviewed", note:st.note||""}; });
    // SO-1: stamp the plan identity so --signoff can bind this verdict to the exact plan it reviewed.
    var out={app:APP, audience:(data.audience||{}),
      inputs_fingerprint:(payload.inputs_fingerprint||null), schema_version:(data.schema_version||null),
      reviewed_at:new Date().toISOString(), sections:rows};
    var blob=new Blob([JSON.stringify(out,null,2)],{type:"application/json"});
    var url=URL.createObjectURL(blob), a=document.createElement("a");
    a.href=url; a.download=(APP||"app").replace(/[^a-z0-9_-]+/gi,"-").toLowerCase()+"-signoff.json";
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    setTimeout(function(){ URL.revokeObjectURL(url); },0);
  }

  // ---------- masthead ----------
  function renderMast(){
    var h=document.getElementById("mast");
    if(EU){
      var steps=(s.steps||[]).map(function(t){ return '<li>'+esc(t)+'</li>'; }).join("");
      h.innerHTML=
        '<div class="eyebrow">Your app <span class="dot">·</span> '+esc(data.app_name||"")+'</div>'+
        '<h1 class="headline">'+esc(s.headline||"A first look at your app")+'</h1>'+
        (s.lead?'<p class="lead">'+esc(s.lead)+'</p>':'')+
        (steps?'<ol class="steps">'+steps+'</ol>':'');
    } else {
      var meta=(s.meta||[]).map(function(m){ return '<div class="meta">'+esc(m)+'</div>'; }).join("");
      h.innerHTML=
        '<div class="eyebrow">Wireframe <span class="dot">·</span> '+esc(data.app_name||"")+'</div>'+
        '<h1 class="headline">Wireframe Preview</h1>'+ meta +
        ((s.why||s.do)?'<div class="whybox"><div><b>Why </b>'+esc(s.why)+'</div>'+
          '<div><b>Do </b>'+esc(s.do)+'</div></div>':'');
    }
    if(data.schema_version!==EXPECTED_SCHEMA){
      document.getElementById("warn").innerHTML='<div class="banner">This preview was made with a '+
        'different version — some parts may look incomplete.</div>';
    }
  }

  // ---------- at-a-glance ----------
  function renderGlance(){
    var g=document.getElementById("glance");
    var rows = EU
      ? [["Health",s.plain_status],["Size",s.plain_shape],["Content",s.plain_content],["Ready to build?",s.plain_ready]]
      : [["Status",s.counts],["Shape",s.shape],["Content",s.content],["Cascade",s.readiness]];
    g.innerHTML=rows.map(function(r){
      return '<div class="cell"><div class="k">'+esc(r[0])+'</div><div class="v">'+esc(r[1]||"")+'</div></div>';
    }).join("");
  }

  // ---------- mockups ----------
  function chrome(t){ return '<div class="chrome"><span class="cdot"></span><span class="cdot"></span>'+
    '<span class="cdot"></span><span style="margin-left:5px">'+esc(t)+'</span></div>'; }
  function formMock(m){
    var ml={}; (m.multiline||[]).forEach(function(x){ ml[x]=1; });  // AR-3: which fields are text areas (from data)
    var f=(m.shown&&m.shown.length)?m.shown.map(function(x){
      var area=ml[x]?" area":"";
      return '<div class="fld'+area+'"><label>'+esc(x)+'</label><div class="box"></div></div>';
    }).join(""):'<div class="empty">no boxes for people to fill in</div>';
    var om=m.omitted||{},tags="";
    (om.server_managed||[]).forEach(function(x){ tags+='<span class="tag">'+esc(x)+'</span>'; });
    (om.owned||[]).forEach(function(x){ tags+='<span class="tag">'+esc(x)+'</span>'; });
    var omit=tags?'<div class="omit">Filled in automatically (people don’t see these): '+tags+'</div>':'';
    return '<div class="mock">'+chrome((m.entity||"")+" — add or edit")+'<div class="body">'+f+omit+
      '<div class="acts"><span class="btn primary">Save</span><span class="btn">Cancel</span></div></div></div>';
  }
  function pageMock(item,nav){
    var n=nav.length?'<div class="nav">'+nav.map(function(x){return '<span>'+esc(x)+'</span>';}).join("")+'</div>':'';
    return '<div class="mock">'+chrome(item.label)+n+'<div class="body"><div class="empty" style="min-height:64px">'+
      esc(EU?"this screen's content":(item.detail||"page content"))+'</div></div></div>';
  }
  function listMock(m){  // LH-1: a list/table sketch with the entity's REAL columns
    var cols=(m.columns||[]).slice(0,6);
    if(!cols.length) return '<div class="mock">'+chrome((m.entity||"")+" — list")+
      '<div class="body"><div class="empty">a simple list</div></div></div>';
    var head='<tr><th style="width:34px">#</th>'+cols.map(function(c){return '<th>'+esc(c)+'</th>';}).join("")+'</tr>';
    var rows="";
    for(var i=0;i<3;i++){ rows+='<tr><td class="muted">'+(i+1)+'</td>'+
      cols.map(function(){return '<td><div class="skel"></div></td>';}).join("")+'</tr>'; }
    return '<div class="mock">'+chrome((m.entity||"")+" — list")+
      '<div class="body"><table class="tbl">'+head+rows+'</table></div></div>';
  }
  function mockFor(k,item){
    if(item.mockup&&item.mockup.kind==="form") return formMock(item.mockup);
    if(item.mockup&&item.mockup.kind==="list") return listMock(item.mockup);
    return null;
  }

  // ---------- items ----------
  function renderItem(k,item,nav){
    var w=document.createElement("div"); w.className="item";
    var mock=mockFor(k,item);
    var det=(item.detail&&!EU)?'<div class="det">'+esc(item.detail)+'</div>':'';
    w.innerHTML='<div class="row"><span class="lbl">'+esc(item.label)+'</span>'+badge(item.status)+'</div>'+det;
    if(mock||k==="pages"){
      var d=document.createElement("details");
      var sm=document.createElement("summary"); sm.className="drill"; sm.textContent="show a sketch";
      sm.style.display="inline-block"; d.appendChild(sm);
      var host=document.createElement("div"); host.innerHTML=mock||pageMock(item,nav);
      d.appendChild(host); w.querySelector(".row").appendChild(d);
    }
    return w;
  }

  // ---------- sections ----------
  function renderSection(sec){
    var d=document.createElement("details"); d.className="sec";
    var items=(sec.items||[]).filter(function(i){ return !(EU&&i.technical); });
    var one=(sec.narration&&sec.narration.what)?sec.narration.what:"";
    var needN=EU?(sec.need_items||[]).length:0;
    var signal = needN ? '<span class="needs">'+needN+' need'+(needN>1?'':'s')+' you</span>'
                       : (EU?'<span class="allset">✓ looks set</span>':'<span class="allset"></span>');
    d.innerHTML='<summary><span class="chev">▶</span>'+
      '<span class="dot d-'+esc(sec.status)+'"></span>'+
      '<span class="sec-title">'+esc(sec.title)+'</span>'+
      '<span class="sec-one">'+esc(one)+'</span>'+ signal +
      '<span class="sig-mark"></span></summary>';    // EC-2: approve/flag marker
    var body=document.createElement("div"); body.className="sec-body";
    var mk=d.querySelector(".sig-mark"); paintMark(mk,sec.key);

    if(sec.narration){
      var n=sec.narration,rows;
      if(EU){
        rows=[["What you get",n.what,""]];
        if(n.need) rows.push(["You'll provide",n.need,"need"]);
        if(n.wont) rows.push(["Won't include",n.wont,"wont"]);
        if(n.do)   rows.push(["To check",n.do,""]);
      } else {
        rows=[["What",n.what,""],["Why",n.why,""],["Do",n.do,""]];
        if(n.next) rows.push(["Next",n.next,""]);
      }
      body.appendChild(el('<div class="narr">'+rows.map(function(r){
        return '<div class="r '+r[2]+'"><div class="lab">'+esc(r[0])+'</div><div class="txt">'+esc(r[1])+'</div></div>';
      }).join("")+'</div>'));
    }
    if(EU && (sec.need_items||[]).length){
      body.appendChild(el('<div class="needlist"><b>Still needs you:</b> '+
        sec.need_items.map(esc).join(", ")+'</div>'));
    }
    var nav=(sec.key==="pages")?items.map(function(i){return i.label;}).slice(0,6):[];
    if(items.length){ items.forEach(function(it){ body.appendChild(renderItem(sec.key,it,nav)); }); }
    else { body.appendChild(el('<div class="empty">nothing to review here</div>')); }
    body.appendChild(signRow(sec,mk));   // EC-2: the approve/flag/annotate row
    d.appendChild(body);
    return d;
  }

  function renderClosing(){
    if(!EU || !s.closing) return;
    var c=document.getElementById("closing");
    c.hidden=false;
    c.innerHTML='<b>Anything missing?</b>'+esc(s.closing);
  }

  // ---------- QW-3: the "before launch" to-do roll-up (end_user only) ----------
  function renderTodos(){
    var box=document.getElementById("todos"); box.innerHTML="";
    var t=(EU && data.todos) ? data.todos : [];
    if(!t.length) return;
    var lis=t.map(function(x){ return '<li>'+esc(x.item)+' <span class="muted">— '+esc(x.section)+'</span></li>'; }).join("");
    box.innerHTML='<div class="todos-box"><b>Before you launch, '+t.length+' thing'+(t.length===1?'':'s')+
      ' need'+(t.length===1?'s':'')+' you:</b><ul>'+lis+'</ul></div>';
  }

  // ---------- EC-4: the delivery-role focus lens (shown only for a kit role) ----------
  function renderLens(){
    var box=document.getElementById("lens"), role=cur.split("|")[0], kit=KITS[role];
    if(!kit){ box.hidden=true; box.innerHTML=""; return; }
    box.hidden=false;
    box.innerHTML='<span class="lens-eyebrow">Your view · '+esc(kit.label)+'</span><b>Focus:</b> '+esc(kit.lens);
  }

  // ---------- render the whole document from the current variant (re-run on toggle, QW-1) ----------
  function renderAll(){
    data=resolveVM(cur);                                       // EC-4: kit → its base voice's variant
    EU=((data.audience&&data.audience.voice)==="end_user"); s=data.summary||{};
    renderLens();                                              // EC-4: the delivery-role focus lens
    APP=data.app_name||"app"; SKEY="startd8:wf-signoff:"+APP; SIGN=loadSign();   // EC-2: restore sign-off
    ["mast","warn","glance","todos","outline"].forEach(function(id){ document.getElementById(id).innerHTML=""; });
    var cl=document.getElementById("closing"); cl.innerHTML=""; cl.hidden=true;
    renderMast(); renderGlance(); renderTodos();
    document.getElementById("seclead").textContent = EU?"What your app includes":"Per-section shape";
    var m=document.getElementById("outline");
    (data.sections||[]).forEach(function(sec){ m.appendChild(renderSection(sec)); });
    renderClosing();
    // QW-5: status legend (plain meanings for the dots/badges)
    document.getElementById("legend").innerHTML =
      [["planned","ready to build"],["not_defined","not set up yet"],["placeholder","rough draft"],["invalid","needs fixing"]]
      .map(function(a){ return '<span><i class="dot d-'+a[0]+'"></i>'+a[1]+'</span>'; }).join("");
    renderSignbar();   // EC-2: sign-off progress + export
  }

  // ---------- QW-1 + EC-4: the role (base voice + delivery kits) / depth toggle + open/close ----------
  var parts=(cur||"end_user|intermediate").split("|");
  function kitGroup(base,label){                              // EC-4: the kits that overlay one base voice
    var opts=Object.keys(KITS).filter(function(r){ return KITS[r].base===base; })
      .map(function(r){ return '<option value="'+r+'">'+esc(KITS[r].label)+'</option>'; }).join("");
    return opts ? '<optgroup label="'+label+'">'+opts+'</optgroup>' : '';
  }
  document.getElementById("toolbar").innerHTML=
    '<label class="tg">View<select id="tg-role">'+
      '<optgroup label="Base voices">'+
        '<option value="end_user">Plain (for the owner)</option>'+
        '<option value="architect">Technical (for the builder)</option></optgroup>'+
      kitGroup("end_user","Delivery role · plain")+
      kitGroup("architect","Delivery role · technical")+
    '</select></label>'+
    '<label class="tg" id="tg-depth">Depth<select id="tg-flu">'+
      '<option value="beginner">Fuller</option><option value="intermediate">Standard</option>'+
      '<option value="advanced">Terser</option></select></label>'+
    '<span style="flex:1"></span>'+
    '<button id="ex">Open all</button><button id="co">Close all</button>';
  var selRole=document.getElementById("tg-role"), selFlu=document.getElementById("tg-flu");
  selRole.value=parts[0]; selFlu.value=parts[1]||"intermediate";
  // depth only bites for a plain voice; a technical voice (architect or a technical kit) hides it.
  function syncDepth(){ document.getElementById("tg-depth").style.display = voiceOf(selRole.value)==="architect"?"none":""; }
  function onToggle(){
    var role=selRole.value, flu=(voiceOf(role)==="architect")?"intermediate":selFlu.value;
    cur=role+"|"+flu; syncDepth(); renderAll();               // resolveVM() maps a kit to its base variant
  }
  selRole.onchange=onToggle; selFlu.onchange=onToggle; syncDepth();
  document.getElementById("ex").onclick=function(){ document.querySelectorAll("details.sec").forEach(function(d){d.open=true;}); };
  document.getElementById("co").onclick=function(){ document.querySelectorAll("details.sec").forEach(function(d){d.open=false;}); };

  renderAll();
})();
</script>
</body>
</html>
"""
