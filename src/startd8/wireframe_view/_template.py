"""Self-contained HTML shell for the wireframe-visual preview (FR-WV-1/2/3/4).

ONE offline page — embedded CSS + JS, no CDN, no build. The composed view-model is injected once at
``__PLAN_DATA__`` inside a ``<script type="application/json">`` container (escape-first on embed —
:func:`view._embed_json` neutralizes ``<`` so a ``</script>`` in any label can't break out). The client
reads it (``textContent`` → ``JSON.parse``), then renders: a pinned inverted-pyramid summary band
(M-WV2), a collapsible section outline with metadata badges + authored narration (M-WV2), and
drill-in lo-fi mockups — form field-skeletons, page screen-frames, list table-skeletons (M-WV3).

``__EXPECTED_SCHEMA__`` is substituted from :data:`view.EXPECTED_SCHEMA_VERSION`; the client banners on a
``schema_version`` mismatch rather than rendering a wrong shape (FR-WV-7).
"""

WIREFRAME_VIEW_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Wireframe Preview</title>
<style>
  :root{
    --ink:#1c1c1c; --dim:#6b6b6b; --line:#c9c9c9; --bg:#f4f4f2; --card:#ffffff;
    --planned:#2e7d32; --defaults:#1565c0; --placeholder:#b8860b; --not_defined:#8a8a8a; --invalid:#c62828;
  }
  *{box-sizing:border-box}
  body{margin:0;font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
       color:var(--ink);background:var(--bg)}
  code,.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
  .wrap{max-width:920px;margin:0 auto;padding:0 18px 80px}
  a{color:var(--defaults)}

  /* ---- inverted-pyramid summary band (pinned) ---- */
  header.summary{position:sticky;top:0;z-index:10;background:var(--bg);
    border-bottom:2px solid var(--line);padding:16px 18px 12px;margin:0 -18px 18px}
  header.summary h1{margin:0 0 2px;font-size:19px}
  header.summary .root{color:var(--dim);font-size:12px;word-break:break-all;margin-bottom:8px}
  .meta{color:var(--dim);font-size:12.5px;margin:2px 0}
  .band{display:grid;grid-template-columns:max-content 1fr;gap:2px 10px;margin:10px 0 6px;font-size:13px}
  .band b{color:var(--dim);font-weight:600}
  .why{font-size:12.5px;color:#444;background:#fff;border:1px solid var(--line);border-radius:6px;
    padding:8px 10px;margin-top:8px}
  .why b{color:var(--dim)}
  .controls{margin-top:10px}
  .controls button{font:inherit;font-size:12px;border:1px solid var(--line);background:#fff;border-radius:5px;
    padding:3px 9px;cursor:pointer;margin-right:6px}

  /* ---- outline ---- */
  details.sec{background:var(--card);border:1px solid var(--line);border-radius:8px;margin:10px 0;overflow:hidden}
  details.sec>summary{list-style:none;cursor:pointer;padding:11px 14px;display:flex;align-items:center;gap:9px;
    font-weight:600}
  details.sec>summary::-webkit-details-marker{display:none}
  details.sec>summary::before{content:"\25B8";color:var(--dim);font-size:11px;transition:transform .12s}
  details.sec[open]>summary::before{transform:rotate(90deg)}
  .sec .what{font-weight:400;color:var(--dim);font-size:12.5px;flex:1;min-width:0;
    overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .sec-body{padding:4px 14px 14px}
  .narr{font-size:12.5px;color:#444;border-left:3px solid var(--line);padding:2px 0 2px 10px;margin:4px 0 12px}
  .narr div{margin:2px 0}.narr b{color:var(--dim)}

  /* ---- items ---- */
  .item{border-top:1px dashed var(--line);padding:9px 0}
  .item:first-child{border-top:none}
  .item .row{display:flex;align-items:center;gap:8px}
  .item .lbl{font-weight:600}
  .item .det{color:var(--dim);font-size:12px;margin:3px 0 0 2px}
  .drill{font-size:11.5px;border:1px solid var(--line);background:#fafafa;border-radius:5px;
    padding:2px 8px;cursor:pointer;margin-left:auto}

  /* ---- badges / pills ---- */
  .badge{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;
    padding:2px 7px;border-radius:10px;color:#fff;white-space:nowrap}
  .b-planned{background:var(--planned)}.b-defaults{background:var(--defaults)}
  .b-placeholder{background:var(--placeholder)}.b-not_defined{background:var(--not_defined)}
  .b-invalid{background:var(--invalid)}
  .pill{font-size:10.5px;color:var(--dim);border:1px solid var(--line);border-radius:10px;padding:1px 7px}
  .count{margin-left:auto;color:var(--dim);font-size:12px;font-weight:400}

  /* ---- lo-fi mockups (M-WV3) ---- */
  .mock{margin:10px 0 4px;border:1.5px solid #b5b5b5;border-radius:8px;background:#fff;overflow:hidden;
    box-shadow:0 1px 0 #ddd}
  .mock .chrome{background:#ececec;border-bottom:1.5px solid #b5b5b5;padding:5px 10px;font-size:11px;color:#555;
    display:flex;align-items:center;gap:6px}
  .mock .dot{width:9px;height:9px;border-radius:50%;background:#cfcfcf;display:inline-block}
  .mock .nav{display:flex;gap:8px;padding:7px 10px;border-bottom:1px dashed var(--line);flex-wrap:wrap}
  .mock .nav span{font-size:11.5px;color:#555;border:1px solid var(--line);border-radius:4px;padding:1px 7px;background:#fafafa}
  .mock .body{padding:12px 14px}
  .fld{display:grid;grid-template-columns:130px 1fr;gap:8px;align-items:center;margin:7px 0}
  .fld label{font-size:12.5px;color:#333}
  .fld .box{height:26px;border:1.5px solid #cfcfcf;border-radius:4px;background:#fbfbfb}
  .fld.area .box{height:52px}
  .omit{margin-top:11px;font-size:11.5px;color:var(--dim);border-top:1px dashed var(--line);padding-top:8px}
  .omit .tag{display:inline-block;border:1px solid var(--line);border-radius:4px;padding:0 6px;margin:2px 4px 0 0;
    background:#f6f6f6}
  .actions{margin-top:12px;display:flex;gap:8px}
  .actions .btn{border:1.5px solid #b5b5b5;border-radius:5px;padding:5px 14px;font-size:12px;background:#f0f0f0;color:#444}
  .actions .btn.primary{background:#e3ecf7;border-color:#9db8db;color:#1565c0}
  table.tbl{width:100%;border-collapse:collapse;font-size:12px}
  table.tbl th,table.tbl td{border:1px solid var(--line);padding:5px 8px;text-align:left;color:#666}
  table.tbl th{background:#f2f2f2}
  .skelrow div{height:9px;background:#eee;border-radius:3px}
  .banner{background:#fff3cd;border:1px solid #e0c97a;border-radius:6px;padding:9px 12px;margin:12px 0;font-size:12.5px}
  .empty{color:var(--dim);font-size:12px;font-style:italic}
</style>
</head>
<body>
<div class="wrap">
  <header class="summary" id="summary"></header>
  <div id="warn"></div>
  <main id="outline"></main>
</div>

<!-- Embedded view-model (application/json is never executed; view.render_html escapes "<" on embed). -->
<script type="application/json" id="plan-data">
__PLAN_DATA__
</script>

<script>
(function(){
  "use strict";
  var EXPECTED_SCHEMA = __EXPECTED_SCHEMA__;
  var data;
  try { data = JSON.parse(document.getElementById("plan-data").textContent); }
  catch(e){ document.getElementById("outline").innerHTML =
    '<div class="banner">Could not read the embedded plan data.</div>'; return; }

  function esc(s){ return String(s==null?"":s)
    .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
    .replace(/"/g,"&quot;").replace(/'/g,"&#39;"); }
  function badge(st){ return '<span class="badge b-'+esc(st)+'">'+esc(String(st).replace(/_/g," "))+'</span>'; }
  function el(html){ var t=document.createElement("template"); t.innerHTML=html.trim(); return t.content.firstChild; }
  function basename(p){ var s=String(p||"").replace(/\/+$/,""); return s.substring(s.lastIndexOf("/")+1)||s; }
  var ROLE = (data.audience && data.audience.role) || "architect";
  var EU = ROLE === "end_user";   // the plain, non-technical voice (FR-AUD)

  // ---- summary band (inverted pyramid, pinned) ----
  function renderSummary(){
    var s=data.summary||{}, h=document.getElementById("summary");
    var meta=(s.meta||[]).map(function(m){ return '<div class="meta">'+esc(m)+'</div>'; }).join("");
    // End-user band: plain labels + jargon-free values (FR-AUD gap-3); architect keeps the raw footer.
    var L = EU ? {a:"Health",b:"Size",c:"Content",d:"Ready to build?"}
               : {a:"Status",b:"Shape",c:"Content",d:"Cascade"};
    var vStatus  = EU ? esc(s.plain_status)  : esc(s.counts);
    var vShape   = EU ? esc(s.plain_shape)   : esc(s.shape);
    var vContent = EU ? esc(s.plain_content) : esc(s.content);
    var band=
      '<div class="band">'+
      '<b>'+L.a+'</b><span>'+vStatus+'</span>'+
      '<b>'+L.b+'</b><span>'+vShape+'</span>'+
      '<b>'+L.c+'</b><span>'+vContent+'</span>'+
      '<b>'+L.d+'</b><span>'+esc(s.readiness)+'</span>'+
      '</div>';
    var why = (s.why||s.do) ?
      '<div class="why"><div><b>'+(EU?"Start here ":"Why ")+'</b>'+esc(s.why)+'</div>'+
      '<div><b>'+(EU?"Then ":"Do ")+'</b>'+esc(s.do)+'</div></div>' : '';
    h.innerHTML =
      '<h1>Wireframe Preview — '+esc(basename(data.project_root))+'</h1>'+
      '<div class="root">'+esc(data.project_root)+'</div>'+ meta + band + why +
      '<div class="controls">'+
        '<button id="ex">Expand all</button><button id="co">Collapse all</button>'+
      '</div>';
    if(data.schema_version!==EXPECTED_SCHEMA){
      document.getElementById("warn").innerHTML =
        '<div class="banner">Data schema_version '+esc(data.schema_version)+
        ' ≠ viewer '+esc(EXPECTED_SCHEMA)+' — some fields may render incompletely.</div>';
    }
  }

  // ---- mockups (M-WV3) ----
  function chrome(title){
    return '<div class="chrome"><span class="dot"></span><span class="dot"></span><span class="dot"></span>'+
           '<span style="margin-left:6px">'+esc(title)+'</span></div>';
  }
  function formMock(m){
    var fields = (m.shown&&m.shown.length) ? m.shown.map(function(f){
      var area=/summary|description|notes|body|content|bio|context/i.test(f)?" area":"";
      return '<div class="fld'+area+'"><label>'+esc(f)+'</label><div class="box"></div></div>';
    }).join("") : '<div class="empty">no user-editable fields</div>';
    var om=m.omitted||{}, tags="";
    (om.server_managed||[]).forEach(function(f){ tags+='<span class="tag">'+esc(f)+' · server</span>'; });
    (om.owned||[]).forEach(function(f){ tags+='<span class="tag">'+esc(f)+' · AI/owner</span>'; });
    var omit = tags ? '<div class="omit">Not on the form (managed for the user): '+tags+'</div>' : '';
    return '<div class="mock">'+chrome((m.entity||"")+" — create / edit")+
      '<div class="body">'+fields+omit+
      '<div class="actions"><span class="btn primary">Save</span><span class="btn">Cancel</span></div>'+
      '</div></div>';
  }
  function pageMock(item, navLabels){
    var nav = navLabels.length ? '<div class="nav">'+navLabels.map(function(n){
      return '<span>'+esc(n)+'</span>'; }).join("")+'</div>' : '';
    return '<div class="mock">'+chrome(item.label)+ nav +
      '<div class="body"><div class="empty" style="min-height:70px">'+
      esc(item.detail||"page content")+'</div></div></div>';
  }
  function listMock(item){
    var head='<tr><th>#</th><th>columns defined in schema.prisma</th><th>&nbsp;</th></tr>';
    var rows="";
    for(var i=0;i<3;i++) rows+='<tr class="skelrow"><td>'+(i+1)+'</td><td><div></div></td><td><div></div></td></tr>';
    return '<div class="mock">'+chrome(item.label+" — list")+
      '<div class="body"><table class="tbl">'+head+rows+'</table></div></div>';
  }
  function mockFor(sectionKey, item){
    if(item.mockup && item.mockup.kind==="form") return formMock(item.mockup);
    if(sectionKey==="pages") return null;   // pages get a section-level frame set (below)
    return null;
  }

  // ---- outline (M-WV2) ----
  function renderItem(sectionKey, item, navLabels){
    var wrap=document.createElement("div"); wrap.className="item";
    var mock = mockFor(sectionKey, item);
    // End-user reads the visual mockup, not the raw "fields: … | omitted …" line — hide it when a
    // mockup carries the same info (FR-AUD gap-3); architect keeps the technical detail.
    var showDet = item.detail && !(EU && mock);
    var det = showDet ? '<div class="det mono">'+esc(item.detail)+'</div>' : '';
    wrap.innerHTML='<div class="row"><span class="lbl">'+esc(item.label)+'</span>'+badge(item.status)+'</div>'+det;
    var isPage = sectionKey==="pages";
    var isList = sectionKey==="entities" && /view|CRUD/i.test(item.detail||"");
    if(mock || isPage){
      var d=document.createElement("details");
      var sm=document.createElement("summary"); sm.className="drill"; sm.textContent="show mockup";
      sm.style.display="inline-block"; d.appendChild(sm);
      var host=document.createElement("div");
      host.innerHTML = mock || pageMock(item, navLabels);
      d.appendChild(host); wrap.querySelector(".row").appendChild(d);
    }
    return wrap;
  }
  function renderSection(sec){
    var d=document.createElement("details"); d.className="sec";
    var what = (sec.narration&&sec.narration.what) ? sec.narration.what : "";
    d.innerHTML='<summary>'+esc(sec.title)+' '+badge(sec.status)+
      '<span class="what">'+esc(what)+'</span>'+
      '<span class="count">'+(sec.items?sec.items.length:0)+'</span></summary>';
    var body=document.createElement("div"); body.className="sec-body";
    if(sec.narration){
      var n=sec.narration;
      var rows;
      if(EU){
        // FR-AUD-C2 — the DOES / WON'T / NEED framing. Skip `why` (its base value is architect voice;
        // the end_user records carry the stakes inside What/Need instead).
        rows=[["What you get",n.what]];
        if(n.wont) rows.push(["What it won't do",n.wont]);
        if(n.need) rows.push(["What you'll provide",n.need]);
        if(n.do)   rows.push(["Check",n.do]);
        if(n.next) rows.push(["Next",n.next]);
      } else {
        rows=[["What",n.what],["Why",n.why],["Do",n.do]];
        if(n.next) rows.push(["Next",n.next]);
      }
      body.appendChild(el('<div class="narr">'+rows.map(function(r){
        return '<div><b>'+r[0]+' </b>'+esc(r[1])+'</div>'; }).join("")+'</div>'));
    }
    var navLabels=(sec.key==="pages")?(sec.items||[]).map(function(i){return i.label;}).slice(0,6):[];
    if(sec.items && sec.items.length){
      sec.items.forEach(function(it){ body.appendChild(renderItem(sec.key, it, navLabels)); });
    } else {
      body.appendChild(el('<div class="empty">nothing defined for this section</div>'));
    }
    d.appendChild(body);
    return d;
  }
  function renderOutline(){
    var m=document.getElementById("outline");
    (data.sections||[]).forEach(function(sec){ m.appendChild(renderSection(sec)); });
  }

  renderSummary(); renderOutline();
  document.getElementById("ex").onclick=function(){ document.querySelectorAll("details.sec").forEach(function(d){d.open=true;}); };
  document.getElementById("co").onclick=function(){ document.querySelectorAll("details.sec").forEach(function(d){d.open=false;}); };
})();
</script>
</body>
</html>
"""
