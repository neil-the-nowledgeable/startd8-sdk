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
<title>__DOC_TITLE__</title>
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

  /* Structure-only view (profiled navigator): strip the descriptive layer, leaving just the
     section groups + node labels — the underlying node structure with no other text. */
  body.structure-only .meta, body.structure-only .whybox, body.structure-only .lead,
  body.structure-only .glance, body.structure-only #legend, body.structure-only #signbar,
  body.structure-only #warn, body.structure-only .det, body.structure-only .lives,
  body.structure-only .was, body.structure-only .narr, body.structure-only .needlist,
  body.structure-only .sec-one, body.structure-only .needs, body.structure-only .allset,
  body.structure-only .badge, body.structure-only .signoff, body.structure-only .todos-box,
  body.structure-only .item .row details, body.structure-only .sig-mark{display:none !important}
  body.structure-only .item{padding:4px 0}
  body.structure-only .sec-body{padding-top:6px}
  /* structure-only shows the bare node key, not the full descriptive label */
  .lbl-key{display:none}
  body.structure-only .lbl{display:none}
  body.structure-only .lbl-key{display:inline;font-weight:600;font-size:14px}
  /* the available structural metadata per node — hidden normally, revealed in structure-only + combined */
  .node-meta{display:none;font-family:var(--mono);font-size:11.5px;color:var(--ink2);margin:3px 0 0 1px}
  body.structure-only .node-meta, body.combined .node-meta{display:block}

  /* ---------- debugging layer: fixed top-right view-mode panel ---------- */
  #debug:empty{display:none}
  #debug{position:fixed;top:14px;right:14px;z-index:50;background:var(--card);border:1px solid var(--line2);
    border-radius:10px;padding:9px 12px;box-shadow:0 6px 22px -14px rgba(40,32,16,.5);max-width:230px}
  #debug .dbg-title{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--faint);
    font-weight:700;margin-bottom:6px}
  #debug .dbg-opt{display:flex;align-items:flex-start;gap:6px;font-size:12.5px;color:var(--ink);
    cursor:pointer;padding:2px 0}
  #debug .dbg-opt input{margin-top:2px;flex:none}
  #debug .dbg-prov{margin-top:8px;padding-top:7px;border-top:1px solid var(--line);font-size:11px;
    font-family:var(--mono);line-height:1.4}
  #debug .dbg-prov.dbg-clean{color:var(--planned)}
  #debug .dbg-prov.dbg-cruft{color:var(--ochre-ink)}
  #debug .dbg-prov b{font-weight:700}
  @media (max-width:920px){#debug{position:static;max-width:none;margin:14px 0 0;box-shadow:none}}

  /* multi-stage cruft purge — hide the app-scaffold chrome the audit flagged (non-destructive;
     opt-in via the debug panel). Sign-off subsystem, dead mockup drills, EU need-signals, todos,
     and the delivery-role kit optgroups in the VIEW dropdown. */
  body.hide-scaffold .signoff,
  body.hide-scaffold #signbar,
  body.hide-scaffold .item .row details,
  body.hide-scaffold .todos-box,
  body.hide-scaffold .needs,
  body.hide-scaffold .allset,
  body.hide-scaffold #tg-role optgroup[label^="Delivery role"]{display:none !important}

  /* Scaffold mode — the template's anatomy: outline every region carrying a data-scaffold role and
     float its label + data source, so an adopter (legal · benchmark · dev-os) can read the template
     itself from a debugging standpoint. Overlay only; no layout shift beyond the outline. */
  body.scaffold [data-scaffold]{outline:1.5px dashed var(--accent2);outline-offset:2px;position:relative}
  body.scaffold [data-scaffold]::before{content:attr(data-scaffold);position:absolute;top:-8px;left:8px;
    z-index:5;background:var(--accent);color:#fff;font-family:var(--mono);font-size:9.5px;font-weight:600;
    letter-spacing:.02em;padding:1px 6px;border-radius:4px;white-space:nowrap;pointer-events:none;opacity:.92}

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
  .item .lives{color:var(--ink2);font-size:12px;font-family:var(--mono);margin:4px 0 0 1px}
  .item .lives .lk{font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--faint);margin-right:6px}
  .item .was{color:var(--faint);font-size:12px;font-family:var(--mono);margin:2px 0 0 1px}
  .item .was .lk{font-weight:700;letter-spacing:.04em;text-transform:uppercase;margin-right:6px}
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
  .signoff .so-prompts{flex-basis:100%;width:100%;margin:0 0 6px;padding:8px 10px;background:var(--card2);
    border:1px dashed var(--line2);border-radius:8px}
  .signoff .so-prompts ul{margin:4px 0 0 1.1em;padding:0;font-size:13px;color:var(--ink2)}
  .signoff .so-prompts li{margin:2px 0}
  .signbar{display:flex;align-items:center;gap:10px;margin:20px 0 0;background:var(--card);border:1px solid var(--line);
    border-radius:12px;padding:11px 15px;font-size:13.5px;color:var(--ink2)}
  .signbar b{color:var(--accent)}
  .signbar button{margin-left:auto;font:inherit;font-size:12.5px;color:#fff;background:var(--accent);
    border:1px solid var(--accent);border-radius:20px;padding:6px 15px;cursor:pointer}
  .signbar button:hover{background:var(--accent2)}

  /* ---------- PF-1: status-filter chips (profiled navigator only; rendered only when payload.profile) ---------- */
  .status-chips{display:flex;flex-wrap:wrap;gap:5px;margin-top:5px}
  .status-chip{font-size:11px;font-weight:700;letter-spacing:.03em;padding:3px 9px;border-radius:20px;
    color:#fff;cursor:pointer;border:2px solid transparent;white-space:nowrap;line-height:1.4}
  .status-chip:hover{opacity:.85}
  .status-chip.active{box-shadow:0 0 0 2px var(--ink),0 0 0 4px transparent;outline:2px solid var(--ink);outline-offset:1px}
  /* items hidden by the active filter (JS sets display:none via applyFilter) */
  .item.pf-hidden{display:none}
  /* sections with no visible items are collapsed + dimmed when a filter is active */
  details.sec.pf-empty{opacity:.45;pointer-events:none}

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
<div id="debug" role="group" aria-label="View mode"></div>
<div class="wrap">
  <header class="mast" id="mast" data-scaffold="masthead — profile chrome (eyebrow · headline · why/do)"></header>
  <div id="warn" role="status"></div>
  <section class="glance" id="glance" aria-label="At a glance" data-scaffold="glance band — computed summary (status_counts · plan.shape)"></section>
  <div id="todos"></div>
  <div class="toolbar" id="toolbar" data-scaffold="control layer — audience × fluency lenses"></div>
  <div class="legend" id="legend" data-scaffold="status legend — profile.statuses[].meaning"></div>
  <div class="lens-banner" id="lens" hidden></div>
  <hr class="rule">
  <p class="section-lead" id="seclead" data-scaffold="section lead — profile.section_lead">What your app includes</p>
  <main id="outline" data-scaffold="outline — node sections + cards (the node-driven layer)"></main>
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
  // Domain profile (opt-in): a status's own label+color, else the app-build default.
  function profStatus(st){ var P=(payload.profile&&payload.profile.statuses)||null;
    if(P){ for(var i=0;i<P.length;i++){ if(P[i].key===st) return P[i]; } } return null; }
  function badge(st){ var p=profStatus(st);
    if(p) return '<span class="badge" style="background:'+esc(p.color)+'">'+esc(p.label)+'</span>';
    return '<span class="badge b-'+esc(st)+'">'+esc(String(st).replace(/_/g," "))+'</span>'; }

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
    var prompts=(sec.approve_prompts||[]);
    var promptHtml=prompts.length
      ?('<div class="so-prompts"><span class="slab">Approve?</span><ul>'+
        prompts.map(function(q){ return '<li>'+esc(q)+'</li>'; }).join("")+
        '</ul></div>')
      :'';
    w.innerHTML=promptHtml+
      '<span class="slab">Your call</span>'+
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
      var row={key:x.key, title:x.title, status:st.status||"unreviewed", note:st.note||""};
      if(x.approve_prompts&&x.approve_prompts.length) row.approve_prompts=x.approve_prompts.slice();
      return row; });
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
        '<div class="eyebrow">'+esc((payload.profile&&payload.profile.eyebrow)||"Your app")+' <span class="dot">·</span> '+esc(data.app_name||"")+'</div>'+
        '<h1 class="headline">'+esc(s.headline||(payload.profile&&payload.profile.headline)||"A first look at your app")+'</h1>'+
        (s.lead?'<p class="lead">'+esc(s.lead)+'</p>':'')+
        (steps?'<ol class="steps">'+steps+'</ol>':'');
    } else {
      // A profiled (non-app) consumer supplies its own apex chrome so the masthead speaks its
      // domain; without a profile the built-in app strings + summary meta/why/do are unchanged
      // (byte-identity: esc() of the literals is the literals).
      var P=payload.profile||null;
      var eyebrow=(P&&P.eyebrow)||"Wireframe";
      var headline=(P&&P.headline)||"Wireframe Preview";
      var metaLines=P?(P.summary_meta||[]):(s.meta||[]);
      var why=P?(P.why||""):(s.why||"");
      var doo=P?(P.do||""):(s.do||"");
      var meta=metaLines.map(function(m){ return '<div class="meta">'+esc(m)+'</div>'; }).join("");
      h.innerHTML=
        '<div class="eyebrow">'+esc(eyebrow)+' <span class="dot">·</span> '+esc(data.app_name||"")+'</div>'+
        '<h1 class="headline">'+esc(headline)+'</h1>'+ meta +
        ((why||doo)?'<div class="whybox" data-scaffold="reading guidance — profile.why / profile.do">'+
          '<div><b>Why </b>'+esc(why)+'</div>'+
          '<div><b>Do </b>'+esc(doo)+'</div></div>':'');
    }
    if(data.schema_version!==EXPECTED_SCHEMA){
      document.getElementById("warn").innerHTML='<div class="banner">This preview was made with a '+
        'different version — some parts may look incomplete.</div>';
    }
  }

  // ---------- PF-1: status-filter machinery (profiled navigator only) ----------
  var _activeFilter = null;   // current status key filter, null = show all

  function _applyFilter(key){
    // Walk every .item in the outline, show/hide by data-status; hide empty sections.
    var items = document.querySelectorAll("#outline .item[data-status]");
    items.forEach(function(it){
      var match = (key === null) || (it.getAttribute("data-status") === key);
      it.classList.toggle("pf-hidden", !match);
    });
    // Collapse / dim sections that have no visible items under the active filter.
    var secs = document.querySelectorAll("#outline details.sec");
    secs.forEach(function(sec){
      if(key === null){ sec.classList.remove("pf-empty"); return; }
      var visible = sec.querySelectorAll(".item[data-status]:not(.pf-hidden)").length;
      sec.classList.toggle("pf-empty", visible === 0);
    });
    // Sync chip active state.
    document.querySelectorAll(".status-chip").forEach(function(ch){
      ch.classList.toggle("active", ch.getAttribute("data-chip-key") === key);
    });
  }

  function _onChipClick(key){
    _activeFilter = (_activeFilter === key) ? null : key;   // toggle: click active chip → clear
    _applyFilter(_activeFilter);
  }

  // ---------- at-a-glance ----------
  function renderGlance(){
    var g=document.getElementById("glance");
    var rows = EU
      ? [["Health",s.plain_status],["Size",s.plain_shape],["Content",s.plain_content],["Ready to build?",s.plain_ready]]
      : [["Status",s.counts],["Shape",s.shape],["Content",s.content],["Cascade",s.readiness]];
    // A profiled (non-app) consumer often has no Content/Cascade figures; drop the empty cells
    // rather than render bare "CONTENT"/"CASCADE" labels. App path (no profile) keeps all four.
    if(payload.profile){ rows=rows.filter(function(r){ return r[1]!=null && String(r[1]).trim()!==""; }); }
    // PF-1 (inspect-loop derivative value): in a profiled navigator view, replace the STATUS cell's
    // plain text with interactive chips — the status roll-up becomes a live grounding filter.
    if(!EU && payload.profile && s.status_counts && Object.keys(s.status_counts).length){
      g.innerHTML=rows.map(function(r){
        var sc=(r[0]==="Shape")?' data-scaffold="shape — plan.shape (dialect-aware)"':(r[0]==="Content"||r[0]==="Cascade")?'':'';
        if(r[0] !== "Status") return '<div class="cell"'+sc+'><div class="k">'+esc(r[0])+'</div><div class="v">'+esc(r[1]||"")+'</div></div>';
        var chips = Object.keys(s.status_counts).map(function(key){
          var cnt=s.status_counts[key], p=profStatus(key), bg=p?p.color:"#888", lbl=p?p.label:key;
          return '<button class="status-chip" type="button" data-chip-key="'+esc(key)+'"'+
            ' style="background:'+esc(bg)+'" title="Filter to '+esc(lbl)+' items">'+
            esc(lbl)+' ('+esc(String(cnt))+')</button>';
        }).join("");
        return '<div class="cell" id="glance-status-cell" data-scaffold="status roll-up — status_counts (+ PF-1 grounding filter)"><div class="k">'+esc(r[0])+'</div>'+
          '<div class="status-chips" id="status-chips">'+chips+'</div></div>';
      }).join("");
      g.querySelectorAll(".status-chip").forEach(function(btn){
        btn.addEventListener("click", function(){ _onChipClick(btn.getAttribute("data-chip-key")); });
      });
    } else {
      g.innerHTML=rows.map(function(r){
        return '<div class="cell"><div class="k">'+esc(r[0])+'</div><div class="v">'+esc(r[1]||"")+'</div></div>';
      }).join("");
    }
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
    // PF-1: expose the item's status as a data attribute when a domain profile is active so the
    // filter machinery (data-status selectors) can show/hide items without touching the app path.
    if(payload.profile && item.status) w.setAttribute("data-status", item.status);
    var mock=mockFor(k,item);
    var det=(item.detail&&!EU)?'<div class="det">'+esc(item.detail)+'</div>':'';
    var livesHtml="";
    if(item.lives&&item.lives.length&&!EU){
      livesHtml='<div class="lives"><span class="lk">Lives</span>'+
        item.lives.map(function(e){
          var t=(e.type||"ref"), r=(e.ref||"");
          return esc(t)+": "+esc(r);
        }).join(" · ")+'</div>';
    }
    var wasHtml="";
    if(item.was&&item.was.length&&!EU){
      wasHtml='<div class="was"><span class="lk">Was</span>'+esc(item.was.join(" · "))+'</div>';
    }
    var metaHtml=(item.meta&&!EU)?'<div class="node-meta">'+esc(item.meta)+'</div>':'';  // structure-only reveal
    w.innerHTML='<div class="row"><span class="lbl">'+esc(item.label)+'</span>'+
      (item.key?'<span class="lbl-key">'+esc(item.key)+'</span>':'')+  // structure-only: bare node key
      badge(item.status)+'</div>'+det+livesHtml+wasHtml+metaHtml;
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
    _activeFilter = null;   // PF-1: reset status filter on each full re-render (voice/depth toggle)
    data=resolveVM(cur);                                       // EC-4: kit → its base voice's variant
    EU=((data.audience&&data.audience.voice)==="end_user"); s=data.summary||{};
    renderLens();                                              // EC-4: the delivery-role focus lens
    APP=data.app_name||"app"; SKEY="startd8:wf-signoff:"+APP; SIGN=loadSign();   // EC-2: restore sign-off
    ["mast","warn","glance","todos","outline"].forEach(function(id){ document.getElementById(id).innerHTML=""; });
    var cl=document.getElementById("closing"); cl.innerHTML=""; cl.hidden=true;
    renderMast(); renderGlance(); renderTodos();
    document.getElementById("seclead").textContent = (payload.profile&&payload.profile.section_lead) ? payload.profile.section_lead : (EU?"What your app includes":"Per-section shape");
    var m=document.getElementById("outline");
    (data.sections||[]).forEach(function(sec){ m.appendChild(renderSection(sec)); });
    renderClosing();
    // QW-5: status legend (plain meanings for the dots/badges)
    document.getElementById("legend").innerHTML = (function(){
      var P=(payload.profile&&payload.profile.statuses)||null;
      if(P) return P.map(function(s){ return '<span><i class="dot" style="background:'+esc(s.color)+'"></i>'+esc(s.meaning)+'</span>'; }).join("");
      return [["planned","ready to build"],["not_defined","not set up yet"],["placeholder","rough draft"],["invalid","needs fixing"]]
        .map(function(a){ return '<span><i class="dot d-'+a[0]+'"></i>'+a[1]+'</span>'; }).join("");
    })();
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

  // ---------- debugging layer: top-right view-mode panel (profiled navigator only) ----------
  // Three modes over the node view: content (default) · structure only (keys + metadata, no prose) ·
  // combined (content AND the structural metadata together). Gated to a profile so the app path is
  // byte-identical (FR-8). Structure-only and Combined are mutually exclusive.
  if(payload.profile){
    // Live provenance readout — "all content is cruft until proven otherwise": chrome that traces to
    // a source is proven; an orphan (no source) is cruft. Green when clean, ochre when cruft remains.
    var ch=payload.chrome, prov="";
    if(ch){
      var cruft=(ch.orphans||[]).length, cls=cruft?"dbg-cruft":"dbg-clean";
      prov='<div class="dbg-prov '+cls+'">provenance '+ch.score+' · '+ch.present+'/'+ch.total+' proven'+
        (cruft?' · <b>'+cruft+' cruft</b>: '+esc((ch.orphans||[]).join(", ")):' · no cruft ✓')+'</div>';
    }
    document.getElementById("debug").innerHTML=
      '<div class="dbg-title">View mode</div>'+
      '<label class="dbg-opt"><input type="checkbox" id="structOnly"><span>Structure only</span></label>'+
      '<label class="dbg-opt"><input type="checkbox" id="combined"><span>Combined (structure + content)</span></label>'+
      // Multi-stage cruft purge: an orthogonal filter (not a view mode) that HIDES the app-scaffold
      // chrome the fresh-eyes audit flagged (sign-off subsystem · mockups · delivery-role kits) —
      // non-destructive so a downstream consumer opts in and elements can resurface later in a
      // different light. Default off (nothing hidden until selected).
      '<label class="dbg-opt"><input type="checkbox" id="hideScaffold"><span>Hide app-scaffold chrome</span></label>'+
      // Scaffold mode: the meta-debugging view of the TEMPLATE itself. As this renderer becomes the
      // de-facto multi-domain node visualizer (requirements first; legal · benchmark · dev-os next),
      // an adopter needs to see the template's anatomy — each region labelled with its scaffold role +
      // data source (data-scaffold). Orthogonal overlay, not a view mode.
      '<label class="dbg-opt"><input type="checkbox" id="scaffold"><span>Scaffold mode (template anatomy)</span></label>'+
      prov;
    var struct=document.getElementById("structOnly"), comb=document.getElementById("combined");
    var hide=document.getElementById("hideScaffold"), scaf=document.getElementById("scaffold");
    function syncModes(){
      document.body.classList.toggle("structure-only", struct.checked);
      document.body.classList.toggle("combined", comb.checked);
    }
    struct.onchange=function(){ if(struct.checked) comb.checked=false; syncModes(); };
    comb.onchange=function(){ if(comb.checked) struct.checked=false; syncModes(); };
    hide.onchange=function(){ document.body.classList.toggle("hide-scaffold", hide.checked); };
    scaf.onchange=function(){ document.body.classList.toggle("scaffold", scaf.checked); };
  }

  renderAll();
})();
</script>
</body>
</html>
"""
