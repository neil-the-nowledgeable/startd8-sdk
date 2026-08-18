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

  /* ---------- doc-context band (profiled requirements render only) ---------- */
  body.nav-profiled .dc-band{display:flex;flex-wrap:wrap;gap:6px;margin-top:14px;align-items:center}
  body.nav-profiled .dc-chip{display:inline-flex;align-items:baseline;gap:5px;font-family:var(--mono);
    font-size:11px;color:var(--ink2);background:var(--card);border:1px solid var(--line);
    border-radius:6px;padding:3px 8px;line-height:1.5;white-space:nowrap}
  body.nav-profiled .dc-chip .dc-k{font-size:9px;letter-spacing:.06em;text-transform:uppercase;
    color:var(--faint);font-weight:600}
  body.nav-profiled .dc-crit{font-weight:700}
  body.nav-profiled .dc-crit-high{color:#ab473a;border-color:#ab473a55}
  body.nav-profiled .dc-crit-medium{color:#a9781a;border-color:#a9781a55}
  body.nav-profiled .dc-crit-low{color:#3d7a57;border-color:#3d7a5755}
  body.nav-profiled .dc-backend{color:var(--accent);border-color:var(--accent)}
  body.nav-profiled .dc-counts{color:var(--faint)}
  body.nav-profiled .dc-risks{margin-top:8px;font-size:12px;color:var(--ink2)}
  body.nav-profiled .dc-risks summary{cursor:pointer;font-family:var(--mono);font-size:11px;
    color:var(--ink2);padding:3px 0;list-style-position:outside}
  body.nav-profiled .dc-risks summary::-webkit-details-marker{color:var(--faint)}
  body.nav-profiled .dc-risk{border-left:2px solid var(--line);padding:5px 0 5px 10px;margin:6px 0 6px 2px;
    font-size:12px;line-height:1.5}
  body.nav-profiled .dc-risk.dc-pri-high{border-left-color:#ab473a}
  body.nav-profiled .dc-risk.dc-pri-medium{border-left-color:#a9781a}
  body.nav-profiled .dc-risk.dc-pri-low{border-left-color:#3d7a57}
  body.nav-profiled .dc-rp{font-family:var(--mono);font-size:9px;text-transform:uppercase;
    letter-spacing:.06em;color:var(--faint);margin-right:6px}
  body.nav-profiled .dc-rt{font-weight:700;color:var(--ink)}
  body.nav-profiled .dc-mit{color:var(--ink2);font-size:11.5px;margin-top:2px}
  body.nav-profiled .dc-cite{font-family:var(--mono);font-size:10px;color:var(--accent)}
  body.nav-profiled .dc-nocite{font-family:var(--mono);font-size:10px;color:#ab473a}

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

  /* REQ-view-definition-mode: the old content-density modes are retired (their reason — "show structure
     not prose" — is now owned by the View Definition pick). Their one unique payload, the per-node
     structural metadata (item.meta), survives as the additive "Show node metadata" overlay. */
  .lbl-key{display:none}   /* the bare-key span stays in the DOM but hidden (no longer a mode) */
  .node-meta{display:none;font-family:var(--mono);font-size:11.5px;color:var(--ink2);margin:3px 0 0 1px}
  body.show-node-meta .node-meta{display:block}

  /* ---------- debugging layer: fixed top-right view-mode panel ---------- */
  #debug:empty{display:none}
  #debug{position:fixed;top:14px;right:14px;z-index:50;background:var(--card);border:1px solid var(--line2);
    border-radius:10px;padding:9px 12px;box-shadow:0 6px 22px -14px rgba(40,32,16,.5);max-width:230px}
  #debug .dbg-title{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--faint);
    font-weight:700;margin-bottom:6px}
  /* group headers — the panel's three logical kinds of control (VIEW modes · OVERLAYS · TEMPLATE
     ANATOMY), each a labelled divider so the panel reads as coherent sections, not a flat pile.
     Inert on the app path (whole panel is profile-gated). */
  #debug .dbg-group{font-size:9.5px;letter-spacing:.11em;text-transform:uppercase;color:var(--faint);
    font-weight:700;margin:9px 0 3px;padding-top:8px;border-top:1px solid var(--line)}
  #debug .dbg-group.dbg-group-first{margin-top:2px;padding-top:0;border-top:none}
  #debug .dbg-group .dbg-hint{font-weight:400;letter-spacing:.02em;text-transform:none;color:var(--faint);
    opacity:.75}
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
  /* Each region's label is a blueprint corner-annotation tucked INSIDE its own top-left (like a room
     label on a floor plan), not floating in the margin ABOVE the box — the old top:-11px collided on
     tightly-stacked + NESTED regions (a glance cell's label landed on the glance band's label). Every
     region reserves a top label-band via padding-top, so a nested region's content — and its own label —
     always start BELOW the parent's band. Scaffold-only: no body.scaffold on the app path → byte-identical. */
  body.scaffold{padding-top:6px}
  body.scaffold [data-scaffold]{outline:2px dashed var(--accent);outline-offset:2px;position:relative;
    margin-top:10px;padding-top:26px}
  /* the label chip: solid dark (white on --ink ≈ 13:1 contrast — legible over any content) with a
     layer-coloured left stripe, seated in the corner and ellipsised so a long label never overflows a
     narrow/nested region (the status-roll-up / shape cells were the worst case). */
  body.scaffold [data-scaffold]::before{content:attr(data-scaffold);position:absolute;top:4px;left:4px;
    z-index:10;background:var(--ink);color:#f7f3ea;font-family:var(--mono);font-size:11px;font-weight:600;
    letter-spacing:.02em;padding:2px 8px;border-radius:4px;max-width:calc(100% - 8px);
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis;pointer-events:none;
    border-left:4px solid var(--accent);box-shadow:0 1px 3px rgba(0,0,0,.28)}
  /* layer-aware colouring — the dark chip is constant (legibility); the left stripe + dashed outline
     carry the LAYER (control · descriptive · computed · node-driven), so scaffold mode still teaches
     the taxonomy without the failed white-on-ochre / white-on-green contrast. */
  body.scaffold [data-layer="control"]{outline-color:var(--accent2)}
  body.scaffold [data-layer="control"]::before{border-left-color:var(--accent2)}
  body.scaffold [data-layer="computed"]{outline-color:var(--ochre)}
  body.scaffold [data-layer="computed"]::before{border-left-color:var(--ochre)}
  body.scaffold [data-layer="node"]{outline-color:var(--planned)}
  body.scaffold [data-layer="node"]::before{border-left-color:var(--planned)}
  /* REQ-view-definition-mode: the isolate-anatomy CSS is retired — its "hide requirement content, keep
     the frame" intent is now the View Definition pick (frame-bare, below), with finer control via the
     per-layer disclosure toggles. */
  #debug .dbg-opt.dbg-sub{margin-left:16px}
  /* REQ-15 FR-1/FR-4: frame-bare — hide EVERY region's real content (keep the region outline + its
     ::before meta-description + the vd-template), so the frame shows only the scaffolding + control
     surface. Uses **display:none** (not visibility:hidden) so hidden content takes NO SPACE — the old
     visibility approach removed the text but kept its full height, leaving a large empty region (e.g. a
     paged-in node card's blank height). A per-layer toggle sets body.show-layer-<id>, restoring that one
     layer's content (progressive disclosure). The vd-template is excluded (:not) so it always shows. */
  body.frame-bare [data-scaffold] > *:not(.vd-template){display:none}
  body.frame-bare.show-layer-control [data-layer="control"] > *:not(.vd-template),
  body.frame-bare.show-layer-descriptive [data-layer="descriptive"] > *:not(.vd-template),
  body.frame-bare.show-layer-computed [data-layer="computed"] > *:not(.vd-template),
  body.frame-bare.show-layer-node [data-layer="node"] > *:not(.vd-template){display:revert}
  .vd-template{display:block;margin-top:2px;font-style:italic;color:var(--ink2)}
  .vd-template .vd-t{font-size:13px;line-height:1.7}
  .vd-template .vd-h{font-family:var(--serif);font-size:21px;color:var(--ink2);margin:3px 0}
  .vd-template .vd-sub{font-size:12px;opacity:.85;margin-top:3px}
  .vd-template .eyebrow{font-style:normal}
  .vd-template .ndt-cap{font-family:var(--mono);font-size:10.5px;color:var(--ink2);
    text-transform:uppercase;letter-spacing:.09em;margin:0 0 8px;font-style:normal}
  .vd-template .lbl-key{display:inline !important;font-family:var(--mono);color:var(--ink2);font-weight:600}
  .vd-template .node-meta{display:block !important}
  .vd-template .lbl,.vd-template .det,.vd-template .lives,.vd-template .node-meta,
  .vd-template .lbl-key{font-style:italic}
  .vd-template .badge.ndt-badge{background:var(--ink2)}
  #debug #layerToggles{display:none} body.scaffold #debug #layerToggles{display:block}
  /* scaffold-mode layer legend in the debug panel (hidden until scaffold on) */
  #debug .dbg-layers{display:none;margin-top:8px;padding-top:7px;border-top:1px solid var(--line);
    font-size:10px;font-family:var(--mono);line-height:1.7}
  body.scaffold #debug .dbg-layers{display:block}
  #debug .dbg-layers .ll{display:inline-block;color:#fff;border-radius:3px;padding:0 5px;margin:0 3px 3px 0}
  #debug .ll.control{background:var(--accent2)} #debug .ll.descriptive{background:var(--accent)}
  #debug .ll.computed{background:var(--ochre)} #debug .ll.node{background:var(--planned)}

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
  /* ── Requirement-card readability (PROFILED NAVIGATOR ONLY — body.nav-profiled; a generated-app
     preview has no profile → plain .item card above, byte-identical). Each requirement reads as an
     editorial reference-card: a status-coloured spine to scan by, a FR-id tag + title, "what it does"
     in readable serif prose, and evidence/metadata set apart as a quiet indented technical block. ── */
  body.nav-profiled #outline .item{border-top:none;margin:11px 0;padding:12px 16px 13px 16px;
    background:var(--card);border:1px solid var(--line);border-left:3px solid var(--st,var(--line2));
    border-radius:9px;transition:box-shadow .16s ease,border-left-color .16s}
  body.nav-profiled #outline .item:first-child{border-top:none}
  body.nav-profiled #outline .item:hover{box-shadow:0 3px 15px rgba(45,33,16,.08)}
  /* value-first hierarchy: a small id/status EYEBROW, then the DIDL NAME as the large heading */
  body.nav-profiled #outline .item .ci-top{display:flex;align-items:center;gap:9px;margin-bottom:6px}
  body.nav-profiled #outline .item .ci-full{margin-left:auto;font-family:var(--mono);font-size:10.5px;
    color:var(--accent);text-decoration:none;border-bottom:1px solid transparent;white-space:nowrap}
  body.nav-profiled #outline .item .ci-full:hover{border-bottom-color:var(--accent)}
  body.nav-profiled #outline .item .ci-top .lbl-key{display:inline-block;font-family:var(--mono);
    font-size:10.5px;font-weight:700;letter-spacing:.02em;color:var(--accent);background:rgba(27,84,95,.08);
    padding:2px 7px;border-radius:5px;flex:none}
  body.nav-profiled #outline .item .ci-top .badge{margin-left:auto}   /* status to the right edge */
  /* the DIDL deterministic NAME — FIRST + LARGEST: the requirement's meaning at a glance */
  body.nav-profiled #outline .item .ci-name-h{font-family:var(--serif);font-size:19px;font-weight:600;
    line-height:1.28;letter-spacing:-.01em;color:var(--ink);margin:0 0 4px}
  /* "what it does" — the statement, secondary serif prose under the name */
  body.nav-profiled #outline .item .ci-does{font-size:13px;line-height:1.5;color:var(--ink2);
    font-family:var(--serif);margin:4px 0 0}
  /* at-a-glance SIGNAL STRIP — plain-label pill chips (technical detail on hover) */
  body.nav-profiled #outline .item .sigstrip{display:flex;flex-wrap:wrap;gap:6px;margin:9px 0 3px}
  body.nav-profiled #outline .item .sig{font-family:var(--mono);font-size:10px;font-weight:700;
    text-transform:uppercase;letter-spacing:.05em;padding:2px 9px;border-radius:20px;white-space:nowrap;
    border:1px solid var(--line2);color:var(--ink2);background:var(--card);cursor:default}
  body.nav-profiled #outline .item .sig-arch{color:var(--accent2);border-color:var(--accent2)}
  body.nav-profiled #outline .item .sig-ground.sig-grounded{color:var(--planned);border-color:var(--planned)}
  body.nav-profiled #outline .item .sig-ground.sig-spec{color:var(--ochre-ink);border-color:var(--ochre)}
  body.nav-profiled #outline .item .sig-serves{color:var(--accent);border-color:var(--accent)}
  body.nav-profiled #outline .item .sig-scope{color:var(--faint);border-color:var(--line)}
  /* "what it does" — prose reads better in the serif body than cramped mono */
  body.nav-profiled #outline .item .det{font-family:var(--serif);font-size:13.5px;line-height:1.5;
    color:var(--ink);margin:8px 0 0}
  /* evidence + metadata — a quiet indented technical block set apart from the prose */
  body.nav-profiled #outline .item .lives,
  body.nav-profiled #outline .item .was,
  body.nav-profiled #outline .item .node-meta{margin:8px 0 0;padding-left:11px;
    border-left:2px solid var(--line);font-size:11.5px}
  body.nav-profiled #outline .item .lives{color:var(--ink2)}
  /* what/how/why captioned rows — HOW (verify) neutral, WHY (serves+objective) accented, quiet context */
  body.nav-profiled #outline .item .ci-row{font-size:12.5px;line-height:1.5;color:var(--ink2);
    margin:8px 0 0;padding-left:11px;border-left:2px solid var(--line)}
  body.nav-profiled #outline .item .ci-row.ci-why{border-left-color:var(--accent);color:var(--ink)}
  body.nav-profiled #outline .item .ci-row.ci-wont{color:var(--faint)}
  body.nav-profiled #outline .item .ci-cap{display:block;font-family:var(--mono);font-size:9.5px;
    font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--faint);margin-bottom:2px}
  body.nav-profiled #outline .item .ci-why .ci-cap{color:var(--accent)}
  body.nav-profiled #outline .item .ci-meta{margin-top:8px}
  body.nav-profiled #outline .item .ci-conf,
  body.nav-profiled #outline .item .ci-hd{font-family:var(--mono);font-size:10.5px;color:var(--faint)}
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
  /* FR-8: raw-data debug panel below the sign-off — a dark code block dumping the payload / node items
     being visualized. Hidden until a Debug toggle is on; profiled-navigator-only (app path never emits it). */
  .rawdata{margin:14px 0 0;background:var(--ink);border-radius:12px;padding:14px 16px}
  .rawdata[hidden]{display:none}
  .rawdata .raw-cap{font-family:var(--mono);font-size:11px;color:var(--accent);text-transform:uppercase;
    letter-spacing:.08em;margin:12px 0 6px}
  .rawdata .raw-cap:first-child{margin-top:0}
  .rawdata .raw-json{font-family:var(--mono);font-size:11.5px;line-height:1.5;color:#e8e2d4;
    white-space:pre-wrap;word-break:break-word;margin:0;max-height:440px;overflow:auto}
  /* FR-9: paging — hide the cards/sections not on the current page, and a prev/next bar below the outline. */
  .pg-hidden{display:none !important}
  .pg-empty{display:none !important}
  .pagebar{display:flex;align-items:center;gap:12px;margin:14px 0 0;padding:9px 14px;background:var(--card);
    border:1px solid var(--line);border-radius:20px;font-size:12.5px;color:var(--ink2)}
  .pagebar[hidden]{display:none}
  .pagebar .pg-count{flex:1;text-align:center;font-family:var(--mono);font-size:12px}
  .pagebar .pg-btn{font:inherit;font-size:12.5px;color:#fff;background:var(--accent);border:1px solid var(--accent);
    border-radius:16px;padding:5px 13px;cursor:pointer}
  .pagebar .pg-btn:hover:not([disabled]){background:var(--accent2)}
  .pagebar .pg-btn[disabled]{opacity:.4;cursor:default}
  /* FR-10/FR-11: per-cell inspector — a TABLE of the node's data (node data · value · how it's displayed);
     not-displayed value cells are editable (contenteditable) → a non-persistent edit that surfaces the
     field in the card (.ni-added) and updates only the in-memory node data. */
  .node-inspect{margin-top:9px;padding-top:8px;border-top:1px dashed var(--line2);font-family:var(--mono);font-size:11px}
  .node-inspect .ni-table{width:100%;border-collapse:collapse}
  .node-inspect thead th{text-align:left;color:var(--faint);text-transform:uppercase;letter-spacing:.07em;
    font-size:9.5px;font-weight:600;padding:0 8px 5px 0;border-bottom:1px solid var(--line2)}
  .node-inspect td{padding:3px 8px 3px 0;vertical-align:top;border-bottom:1px solid var(--line)}
  .node-inspect .ni-k{color:var(--accent);font-weight:600;white-space:nowrap;width:104px}
  .node-inspect .ni-v{color:var(--ink2);white-space:pre-wrap;word-break:break-word;width:100%}
  .node-inspect .ni-d{color:var(--faint);white-space:nowrap}
  .node-inspect .ni-edit{border:1px dashed var(--accent);border-radius:3px;padding:2px 6px;cursor:text;
    min-width:70px;color:var(--ink);background:rgba(120,90,40,.05)}
  .node-inspect .ni-edit:focus{outline:2px solid var(--accent);background:var(--card)}
  .node-inspect .ni-edit:empty::before{content:"click to add";color:var(--faint);font-style:italic}
  /* FR-12: the inline on/off switch */
  .node-inspect .ni-sw{position:relative;display:inline-block;width:26px;height:15px;vertical-align:middle;margin-right:8px}
  .node-inspect .ni-sw input{opacity:0;width:0;height:0;position:absolute;margin:0}
  .node-inspect .ni-sw .sw{position:absolute;inset:0;background:var(--line2);border-radius:15px;cursor:pointer;transition:background .15s}
  .node-inspect .ni-sw .sw::before{content:"";position:absolute;width:11px;height:11px;left:2px;top:2px;background:#fff;border-radius:50%;transition:transform .15s}
  .node-inspect .ni-sw input:checked+.sw{background:var(--accent)}
  .node-inspect .ni-sw input:checked+.sw::before{transform:translateX(11px)}
  .ni-added{color:var(--accent2);font-family:var(--mono);font-size:12px;margin:6px 0 0}
  @media (max-width:560px){.node-inspect td,.node-inspect .ni-k,.node-inspect .ni-v{display:block;width:auto}}

  /* ---------- requirement DETAIL panel (promoted inspector, reader variant; profiled-navigator only) ---------- */
  body.nav-profiled #outline .item.cd-able{cursor:pointer}
  body.nav-profiled #outline .item.cd-open{background:var(--card)}
  body.nav-profiled .ci-detail{margin-top:11px;padding-top:11px;border-top:1px solid var(--line);
    display:grid;gap:8px;font-size:12.5px;cursor:default}
  body.nav-profiled .cd-row{display:grid;grid-template-columns:104px 1fr;gap:12px;align-items:baseline}
  body.nav-profiled .cd-k{font-family:var(--mono);font-size:9.5px;text-transform:uppercase;letter-spacing:.06em;
    color:var(--faint);font-weight:600;padding-top:1px}
  body.nav-profiled .cd-v{color:var(--ink);line-height:1.55;word-break:break-word}
  body.nav-profiled .cd-touches .cd-v{display:grid;gap:2px}
  body.nav-profiled .cd-touch{display:flex;gap:9px;align-items:baseline;font-family:var(--mono);font-size:11.5px}
  body.nav-profiled .cd-tk{font-size:8.5px;text-transform:uppercase;letter-spacing:.05em;padding:1px 6px;
    border-radius:4px;min-width:46px;text-align:center;font-weight:700;flex:none}
  body.nav-profiled .cd-tk-code{background:#3a6a941e;color:#3a6a94}
  body.nav-profiled .cd-tk-test{background:#3d7a571e;color:#3d7a57}
  body.nav-profiled .cd-tk-config{background:#a9781a1e;color:#a9781a}
  body.nav-profiled .cd-tk-doc{background:#7a6a481e;color:#7a6a48}
  body.nav-profiled .cd-tk-build{background:#ab473a1e;color:#ab473a}
  body.nav-profiled .cd-tk-other{background:var(--line);color:var(--faint)}
  body.nav-profiled .cd-tp{color:var(--ink2)}
  body.nav-profiled .cd-full{display:inline-block;font-family:var(--mono);font-size:11px;
    color:var(--accent);text-decoration:none;border-bottom:1px solid transparent}
  body.nav-profiled .cd-full:hover{border-bottom-color:var(--accent)}
  body.nav-profiled .cd-full-top{margin-bottom:9px}
  body.nav-profiled .cd-full-bot{margin-top:5px}

  /* ---------- full-page requirement view (client-side route; profiled-navigator only) ---------- */
  #fullview{display:none}
  body.fullview-open .wrap,body.fullview-open #debug{display:none}
  body.fullview-open #fullview{display:block}
  .fv{max-width:820px;margin:0 auto;padding:38px 26px 80px}
  .fv-back{display:inline-block;margin-bottom:22px;font-family:var(--mono);font-size:12px;color:var(--accent);
    text-decoration:none;border-bottom:1px solid transparent}
  .fv-back:hover{border-bottom-color:var(--accent)}
  .fv-head{border-bottom:2px solid var(--line);padding-bottom:16px;margin-bottom:22px}
  .fv-eyebrow{display:flex;align-items:center;gap:9px;margin-bottom:9px}
  .fv-name{font-family:var(--serif);font-size:27px;line-height:1.25;color:var(--ink);margin:0;font-weight:600}
  .fv-body{display:grid;gap:14px}
  .fv-row{display:grid;grid-template-columns:150px 1fr;gap:20px;align-items:baseline;
    padding-bottom:13px;border-bottom:1px solid var(--line)}
  .fv-k{font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:.07em;
    color:var(--faint);font-weight:600;padding-top:2px}
  .fv-v{color:var(--ink);font-size:14.5px;line-height:1.6;word-break:break-word}
  .fv-touches{margin-top:10px}
  .fv-sk{font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:.07em;
    color:var(--faint);font-weight:600;margin-bottom:10px}
  .fv-touches .cd-touch{padding:3px 0}
  @media (max-width:600px){.fv-row{grid-template-columns:1fr;gap:4px}}

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
  <header class="mast" id="mast" data-layer="descriptive" data-scaffold="masthead — profile chrome (eyebrow · headline · why/do)"></header>
  <div id="warn" role="status"></div>
  <section class="glance" id="glance" aria-label="At a glance" data-layer="computed" data-scaffold="glance band — computed summary (status_counts · plan.shape)"></section>
  <div id="todos"></div>
  <div class="toolbar" id="toolbar" data-layer="control" data-scaffold="control layer — audience × fluency lenses"></div>
  <div class="legend" id="legend" data-layer="descriptive" data-scaffold="status legend — profile.statuses[].meaning"></div>
  <div class="lens-banner" id="lens" hidden></div>
  <hr class="rule">
  <p class="section-lead" id="seclead" data-layer="descriptive" data-scaffold="section lead — profile.section_lead">What your app includes</p>
  <main id="outline" data-layer="node" data-scaffold="outline — node sections + cards (the node-driven layer)"></main>
  <!-- FR-9: paging bar — prev/next through the requirement nodes N at a time (shown when a finite size is picked). -->
  <nav class="pagebar" id="pagebar" aria-label="Paging" hidden></nav>
  <div class="signbar" id="signbar"></div>
  <footer class="closing" id="closing" hidden></footer>
  <!-- FR-8: raw-data debug panel — populated + shown by the Debug group's Raw data / Node data toggles. -->
  <section class="rawdata" id="rawdata" aria-label="Raw data" hidden></section>
</div>
<!-- Full-page requirement detail (client-side route; populated by buildFullView on #<key> hash, profiled only). -->
<div id="fullview" data-layer="node" data-scaffold="full-page requirement view — buildFullView on the #<key> route"></div>

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
  var _pagingHook=null;   // FR-9: re-applied after each renderAll so paging survives a lens/depth re-render
  // ── FR-5 SEAM (unify-visibility-predicates) ──────────────────────────────────────────────────
  // Card visibility is a conjunction of independent predicates: status ∧ search ∧ audience ∧ page.
  // PRE_PAGING_REASONS is the ONE registration point for the pre-paging predicates that narrow what
  // paging sees; each class is set by exactly ONE owner (never clobbered), and paging's own pg-hidden
  // is applied LAST over the survivor set. To add a predicate (search's `srch-hidden`, Move 2's
  // `aud-hidden`): register its class HERE and have its owner call applyVisibility() — no other
  // handler changes. A card is shown iff it carries NO active hide-reason class (CSS: display:none).
  var PRE_PAGING_REASONS=["pf-hidden","srch-hidden","aud-hidden"];   // pf=status; srch,aud reserved
  // FR-1: the single visibility recompute point; reassigned in the paging block once applyPaging exists.
  var applyVisibility=function(){};

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
  // Doc-context band — the REQ's overall nature (criticality/domain/audience/trust/data-class/version +
  // FR/objective/non-goal counts + the risk profile with mitigation→FR coverage). MAXIMAL for now; pare
  // back after review. Rendered only when payload.profile.doc_context is populated (a per-doc req render).
  function docContextBand(){
    var P=payload.profile, c=(P&&P.doc_context)||null; if(!c||!Object.keys(c).length) return "";
    function chip(cls,label,val,title){ return val?'<span class="dc-chip '+cls+'" title="'+esc(title||label)+'"><span class="dc-k">'+esc(label)+'</span>'+esc(val)+'</span>':''; }
    var chips=chip("dc-crit dc-crit-"+esc(c.criticality||""),"criticality",c.criticality,"how critical this requirement is")
      + chip("dc-backend","domain",(c.backend||"").replace("python-",""),"backend / projection domain: "+(c.backend||""))
      + chip("dc-aud","for",c.audience,"audience — who this is for")
      + chip("dc-trust","trust",c.trust_boundary,"trust boundary")
      + chip("dc-data","data",c.data_classification,"data classification")
      + chip("dc-ver","version",c.version,"requirement version");
    var counts=[]; if(c.fr_count)counts.push(c.fr_count+" FRs"); if(c.objectives)counts.push(c.objectives+" objectives"); if(c.non_goals)counts.push(c.non_goals+" non-goals");
    if(counts.length) chips+='<span class="dc-chip dc-counts">'+esc(counts.join(" · "))+'</span>';
    var risks=c.risks||[], rhtml="";
    if(risks.length){
      var hi=0,unmit=0; risks.forEach(function(r){ if(r.priority==="high")hi++; if(!(r.cites&&r.cites.length))unmit++; });
      var sum=risks.length+" risks · "+hi+" high · "+(unmit?("⚠ "+unmit+" unmitigated"):"all mitigated");
      var rows=risks.map(function(r){
        var cite=(r.cites&&r.cites.length)?'<span class="dc-cite">'+esc(r.cites.join(" "))+'</span>':'<span class="dc-nocite">⚠ no FR cited</span>';
        return '<div class="dc-risk dc-pri-'+esc(r.priority)+'"><span class="dc-rp">'+esc(r.priority)+'</span><span class="dc-rt">'+esc(r.type)+'</span> '+esc(r.desc)+
          '<div class="dc-mit">→ '+esc(r.mitigation)+' '+cite+'</div></div>';
      }).join("");
      rhtml='<details class="dc-risks"'+(unmit?' open':'')+'><summary>'+esc(sum)+'</summary>'+rows+'</details>';
    }
    return (chips||rhtml)?'<div class="dc-band" data-layer="descriptive" data-scaffold="doc-context band — criticality/backend/audience/trust/risks (profile.doc_context)">'+chips+'</div>'+rhtml:'';
  }
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
        ((why||doo)?'<div class="whybox" data-region="whybox" data-layer="descriptive" data-scaffold="reading guidance — profile.why / profile.do">'+
          '<div><b>Why </b>'+esc(why)+'</div>'+
          '<div><b>Do </b>'+esc(doo)+'</div></div>':'')+
        docContextBand();
    }
    if(data.schema_version!==EXPECTED_SCHEMA){
      document.getElementById("warn").innerHTML='<div class="banner">This preview was made with a '+
        'different version — some parts may look incomplete.</div>';
    }
  }

  // ---------- PF-1: status-filter machinery (profiled navigator only) ----------
  var _activeFilter = null;   // current status key filter, null = show all

  function _applyFilter(key){
    // FR-3: the status predicate sets ONLY its own hide-reason class (`pf-hidden`), then defers the
    // composed recompute (section emptiness + re-page the survivor set) to applyVisibility(). It never
    // touches another predicate's class, so it cannot clobber paging/search/audience decisions (FR-2).
    var items = document.querySelectorAll("#outline .item[data-status]");
    items.forEach(function(it){
      var match = (key === null) || (it.getAttribute("data-status") === key);
      it.classList.toggle("pf-hidden", !match);
    });
    // Sync chip active state (status-predicate-owned UI).
    document.querySelectorAll(".status-chip").forEach(function(ch){
      ch.classList.toggle("active", ch.getAttribute("data-chip-key") === key);
    });
    applyVisibility();   // FR-1/FR-3: the single composed recompute (pf-empty from the union + re-page)
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
        var sc=(r[0]==="Shape")?' data-region="shape" data-layer="computed" data-scaffold="shape — plan.shape (dialect-aware)"':'';
        if(r[0] !== "Status") return '<div class="cell"'+sc+'><div class="k">'+esc(r[0])+'</div><div class="v">'+esc(r[1]||"")+'</div></div>';
        var chips = Object.keys(s.status_counts).map(function(key){
          var cnt=s.status_counts[key], p=profStatus(key), bg=p?p.color:"#888", lbl=p?p.label:key;
          return '<button class="status-chip" type="button" data-chip-key="'+esc(key)+'"'+
            ' style="background:'+esc(bg)+'" title="Filter to '+esc(lbl)+' items">'+
            esc(lbl)+' ('+esc(String(cnt))+')</button>';
        }).join("");
        return '<div class="cell" id="glance-status-cell" data-layer="computed" data-scaffold="status roll-up — status_counts (+ PF-1 grounding filter)"><div class="k">'+esc(r[0])+'</div>'+
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
  // Turn the node-detail blob (NAME →/VERIFY →/SERVES →/WON'T:/DEPENDS-ON:/confidence:) into captioned
  // WHAT/HOW/WHY rows for the profiled requirement card, read STRUCTURALLY from item.fields (the domain
  // projection's typed output) — no prose blob re-parse. Each present field becomes a labelled row; the
  // served objective (joined onto Serves) carries the 'why it matters'. confidence/ships_when are read
  // first-class off the item, not from fields (they have their own WireframeItem slots).
  function fieldsToSd(item){
    var f=item.fields||{};
    var arch=f.archetype?(f.archetype+(f.archetype_gloss?(" · "+f.archetype_gloss):"")):"";
    var scope=f.touches_count?(f.touches_count+(f.touches_count==="1"?" file":" files")):"";
    var rows="";
    function row(cap,cls,val){ if(val){ rows+='<div class="ci-row '+cls+'"><span class="ci-cap">'+cap+'</span>'+esc(val)+'</div>'; } }
    row("Verify · how you’ll know","ci-how",f.verify);
    row("Serves · why it matters","ci-why", f.serves?(f.serves+(f.serves_objective?(" · "+f.serves_objective):"")):"");
    row("Won’t","ci-wont",f.wont);
    row("Ships when","ci-dep",item.ships_when);
    row("Depends on","ci-dep",f.depends);
    var metaParts=[];
    if(item.confidence!=null){ var c=(typeof item.confidence==="number")?item.confidence.toFixed(2):String(item.confidence);
      metaParts.push('<span class="ci-conf">conf '+esc(c)+'</span>'); }
    if(f.handle){ metaParts.push('<span class="ci-hd">'+esc(f.handle)+'</span>'); }
    return { name:f.name||"", arch:arch, scope:scope, serves:f.serves||"", stmt:f.statement||"", rows:rows,
             meta:(metaParts.length?'<div class="ci-meta">'+metaParts.join(" · ")+'</div>':'') };
  }
  // At-a-glance SIGNAL STRIP — plain-labelled chips (technical detail on hover) for the broadest audience:
  // archetype (what kind) · grounding (how proven, status + evidence types) · serves (purpose) · scope (size).
  function signalStrip(item, sd){
    var chips="";
    if(sd.arch){ chips+='<span class="sig sig-arch" title="'+esc(sd.arch)+'">'+esc(sd.arch.split(" · ")[0])+'</span>'; }
    var evt={}; (item.lives||[]).forEach(function(e){ if(e.type) evt[e.type]=1; });
    var evs=Object.keys(evt).sort().join("+");
    var gl=item.status==="grounded"?"proven":(item.status==="spec"?"drafted":(item.status||""));
    if(gl){ chips+='<span class="sig sig-ground sig-'+esc(item.status||"")+'" title="'+esc((item.status||"")+(evs?" · "+evs:""))+'">'+esc(gl)+(evs?' · '+esc(evs):'')+'</span>'; }
    if(sd.serves){ chips+='<span class="sig sig-serves" title="objective it serves">'+esc(sd.serves)+'</span>'; }
    if(sd.scope){ chips+='<span class="sig sig-scope" title="files it touches">'+esc(sd.scope)+'</span>'; }
    return chips?'<div class="sigstrip">'+chips+'</div>':'';
  }
  // The requirement's full record as ordered {k,v} entries — read BY KEY from item.fields + first-class
  // slots (no prose re-parse). ONE extraction shared by the inline peek (buildDetail) and the full-page
  // view (buildFullView) so the two can't drift. Values are pre-escaped HTML (esc()).
  function recordEntries(item){
    var f=item.fields||{}, e=[];
    function add(label,val){ if(val) e.push({k:label, v:val}); }
    add("Name", f.name?esc(f.name):"");
    add("Statement", f.statement?esc(f.statement):"");
    add("Verify", f.verify?esc(f.verify):"");
    add("Serves", f.serves?esc(f.serves+(f.serves_objective?(" · "+f.serves_objective):"")):"");
    add("Type", f.archetype?esc(f.archetype+(f.archetype_gloss?(" · "+f.archetype_gloss):"")):"");
    add("Depends on", f.depends?esc(f.depends):"");
    add("Won’t", f.wont?esc(f.wont):"");
    add("Ships when", item.ships_when?esc(item.ships_when):"");
    if(item.lives&&item.lives.length){ add("Evidence", item.lives.map(function(x){ return esc((x.type||"ref")+": "+(x.ref||"")); }).join("<br>")); }
    if(item.confidence!=null){ var c=(typeof item.confidence==="number")?item.confidence.toFixed(2):String(item.confidence); add("Confidence", esc(c)); }
    add("Handle", f.handle?esc(f.handle):"");
    return e;
  }
  // The full typed Touches list as HTML rows (path + source-bound kind badge). Shared by both views.
  function touchesRows(item){
    if(!(item.touches&&item.touches.length)) return "";
    return item.touches.map(function(t){
      return '<div class="cd-touch"><span class="cd-tk cd-tk-'+esc(t.kind||"other")+'">'+esc(t.kind||"other")+
        '</span><span class="cd-tp">'+esc(t.path||"")+'</span></div>';
    }).join("");
  }
  // Inline PEEK panel (the promoted inspector — reader variant): a compact record + an 'open full view'
  // link into the client-side full-page route. The debug/edit grid (buildInspect) stays behind the toggle.
  function buildDetail(card){
    var item=card._nodeData||{}, d=document.createElement("div"); d.className="ci-detail";
    d.setAttribute("data-layer","node");   // registered region (view_definition regions.bindings: detail)
    d.setAttribute("data-scaffold","requirement detail peek — click-to-expand record + typed Touches (item.fields/touches)");
    var full='<a class="cd-full" href="#'+encodeURIComponent(item.key||"")+'">open full view →</a>';
    var html=recordEntries(item).map(function(e){
      return '<div class="cd-row"><span class="cd-k">'+esc(e.k)+'</span><span class="cd-v">'+e.v+'</span></div>'; }).join("");
    var tr=touchesRows(item);
    if(tr) html+='<div class="cd-row cd-touches"><span class="cd-k">Touches · '+item.touches.length+'</span><span class="cd-v">'+tr+'</span></div>';
    // The full-view link rides BOTH the top and the bottom of the panel so a reader never has to hunt for
    // it — reach the full page immediately on expand, or after reading the record.
    d.innerHTML='<div class="cd-full-top">'+full+'</div>'+html+'<div class="cd-full-bot">'+full+'</div>';
    return d;
  }
  // Full-page requirement view (client-side route): a dedicated page for ONE requirement, reached by the
  // peek's link or a #<key> deep-link. Same shared extraction, fuller layout. Back link clears the hash.
  function buildFullView(item){
    var f=item.fields||{}, d=document.createElement("div"); d.className="fv";
    var rows=recordEntries(item).map(function(e){
      return '<div class="fv-row"><div class="fv-k">'+esc(e.k)+'</div><div class="fv-v">'+e.v+'</div></div>'; }).join("");
    var tr=touchesRows(item);
    d.innerHTML=
      '<a class="fv-back" href="#">← all requirements</a>'+
      '<div class="fv-head"><div class="fv-eyebrow"><span class="lbl-key">'+esc(item.key||"")+'</span>'+badge(item.status)+'</div>'+
        '<h1 class="fv-name">'+esc(f.name||item.label||"")+'</h1></div>'+
      '<div class="fv-body">'+(rows||'<div class="fv-row"><div class="fv-v">(no further detail)</div></div>')+
      (tr?'<div class="fv-touches"><div class="fv-sk">Touches · '+item.touches.length+' — the full blast-radius</div>'+tr+'</div>':'')+
      '</div>';
    return d;
  }
  // Client-side routing for the full-page view (profiled only): #<key> opens that requirement's page;
  // empty/unknown hash restores the browse. Called on hashchange AND after each renderAll (deep-link on load).
  function findItemByKey(k){
    var found=null;
    (data.sections||[]).forEach(function(sec){ (sec.items||[]).forEach(function(it){ if(it.key===k) found=it; }); });
    return found;
  }
  function resolveHash(){
    if(!payload.profile) return;   // full-page view is a profiled-navigator feature only
    var h=decodeURIComponent((location.hash||"").replace(/^#/,""));
    var item=h?findItemByKey(h):null;
    if(item){
      var host=document.getElementById("fullview"); host.innerHTML=""; host.appendChild(buildFullView(item));
      document.body.classList.add("fullview-open"); window.scrollTo(0,0);
    } else {
      document.body.classList.remove("fullview-open");
    }
  }
  function renderItem(k,item,nav){
    var w=document.createElement("div"); w.className="item"; w._nodeData=item;   // FR-10: exact per-cell data
    // PF-1: expose the item's status as a data attribute when a domain profile is active so the
    // filter machinery (data-status selectors) can show/hide items without touching the app path.
    if(payload.profile && item.status){
      w.setAttribute("data-status", item.status);
      // readability: stamp the status colour as a CSS var so the card's status spine renders it
      // (profiled-navigator only — the app path sets nothing → byte-identical).
      var _ps=profStatus(item.status); if(_ps&&_ps.color) w.style.setProperty("--st", _ps.color);
    }
    var mock=mockFor(k,item);
    // Profiled requirement card: parse the node-detail blob into labelled WHAT/HOW/WHY slots so a reader
    // sees what it does, how it's verified, and WHY it matters (the served objective). App path (no
    // profile) keeps the plain .det blob → byte-identical.
    var livesHtml="";
    if(item.lives&&item.lives.length&&!EU){
      livesHtml='<div class="lives"><span class="lk">Lives · evidence</span>'+
        item.lives.map(function(e){
          var t=(e.type||"ref"), r=(e.ref||"");
          return esc(t)+": "+esc(r);
        }).join(" · ")+'</div>';
    }
    var wasHtml="";
    if(item.was&&item.was.length&&!EU){
      wasHtml='<div class="was"><span class="lk">Was</span>'+esc(item.was.join(" · "))+'</div>';
    }
    var metaHtml=(item.meta&&!EU)?'<div class="node-meta">'+esc(item.meta)+'</div>':'';  // revealed by "Show node metadata"
    if(payload.profile && !EU){
      // VALUE-FIRST requirement card: the DIDL deterministic NAME leads (largest); a small id/status
      // eyebrow; then what it does, why it matters (Serves+objective), how you'll know (Verify), evidence.
      var sd=fieldsToSd(item);
      var kk=item.key||"";
      var does=kk ? item.label.replace(new RegExp("^"+kk.replace(/[.*+?^${}()|[\\]\\\\]/g,"\\\\$&")+"\\s*—\\s*"),"") : item.label;
      w.innerHTML=
        '<div class="ci-top"><span class="lbl-key">'+esc(kk)+'</span>'+badge(item.status)+
          '<a class="ci-full" href="#'+encodeURIComponent(item.key||"")+'">full view →</a></div>'+
        (sd.name?'<div class="ci-name-h">'+esc(sd.name)+'</div>':'')+
        ((does&&does!==item.label)?'<div class="det ci-does">'+esc(does)+'</div>':'')+
        signalStrip(item,sd)+
        (sd.stmt?'<div class="det">'+esc(sd.stmt)+'</div>':'')+
        sd.rows+livesHtml+wasHtml+sd.meta+metaHtml;
      // FR-1: click the card to expand its read-only detail panel in place (profiled requirement cards
      // only → app path adds no handler). Clicks on inner interactive elements (sketch, links, the debug
      // inspector, the panel itself) are ignored so the toggle never hijacks them.
      w.classList.add("cd-able");
      w.addEventListener("click", function(ev){
        // Ignore only interactive bits INSIDE this card (the sketch details, links, the debug inspector,
        // the panel itself) — NOT the section <details> that WRAPS every card (an ancestor match here was
        // swallowing every click). w.contains() is false for ancestors, true for the card's own descendants.
        var hit=ev.target.closest("details,a,input,label,button,summary,.node-inspect,.ci-detail");
        if(hit && w.contains(hit)) return;
        var ex=w.querySelector(".ci-detail");
        if(ex){ ex.parentNode.removeChild(ex); w.classList.remove("cd-open"); }
        else { w.appendChild(buildDetail(w)); w.classList.add("cd-open"); }
      });
    } else {
      var det=(item.detail&&!EU)?'<div class="det">'+esc(item.detail)+'</div>':'';
      w.innerHTML='<div class="row"><span class="lbl">'+esc(item.label)+'</span>'+
        (item.key?'<span class="lbl-key">'+esc(item.key)+'</span>':'')+  // bare node key (kept in DOM, hidden)
        badge(item.status)+'</div>'+det+livesHtml+wasHtml+metaHtml;
    }
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
    // readability: mark the body so the enhanced requirement-card styling applies to the PROFILED
    // navigator only — a generated-app preview (no profile) keeps the plain .item card, byte-identical.
    document.body.classList.toggle("nav-profiled", !!payload.profile);
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
    applyDefinitionOverride();   // REQ-14: apply the resolved control/region deltas over the defaults
    if(_pagingHook) _pagingHook();   // FR-9: re-page the freshly-rendered cards
    resolveHash();   // re-resolve the full-page route against the freshly-rendered variant (deep-link on load)
  }

  // REQ-14 (FR-3/FR-5/FR-7): apply a resolved ViewDefinition's control + regions as an ADDITIVE runtime
  // override over the template's hardcoded panel + static region attributes. When the profile carries no
  // delta (or the base values), this re-sets the same strings — a no-op — so the default render is
  // byte-identical; a domain delta relabels a control group/toggle or a region's data-layer/data-scaffold
  // anatomy, and because the scaffold overlay reads those attributes it now reveals the DEFINITION, not
  // hand-authored template strings (the closed mirror). Absent profile ⇒ returns immediately.
  function applyDefinitionOverride(){
    var P=payload.profile; if(!P) return;
    var ctl=P.control;
    if(ctl&&ctl.groups){ Object.keys(ctl.groups).forEach(function(gid){
      var g=ctl.groups[gid], gel=document.querySelector('#debug [data-group="'+gid+'"]');
      if(gel){ if(g.label!=null&&gel.childNodes[0]) gel.childNodes[0].nodeValue=g.label+" ";
               if(g.hint!=null){ var h=gel.querySelector(".dbg-hint"); if(h) h.textContent=g.hint; } }
      var tg=g.toggles||{}; Object.keys(tg).forEach(function(tid){
        var inp=document.getElementById(tid); if(inp&&tg[tid].label!=null){ var sp=inp.nextElementSibling; if(sp) sp.textContent=tg[tid].label; }
      });
    }); }
    var rg=P.regions;
    if(rg&&rg.bindings){ Object.keys(rg.bindings).forEach(function(rid){
      var r=rg.bindings[rid], el=document.getElementById(rid)||document.querySelector('[data-region="'+rid+'"]');
      if(el){ if(r.layer!=null) el.setAttribute("data-layer",r.layer); if(r.scaffold!=null) el.setAttribute("data-scaffold",r.scaffold); }
    }); }
    // REQ-15 FR-3: render the layer LEGEND from the definition's ordered layer schema (was hardcoded +
    // 3-way inconsistent). The base schema reproduces the current legend text → byte-identical.
    var ly=(rg&&rg.layers)||null, leg=document.querySelector("#debug .dbg-layers");
    if(ly&&leg){
      var ids=Object.keys(ly).sort(function(a,b){return (ly[a].order||0)-(ly[b].order||0);});
      leg.innerHTML="layers: "+ids.map(function(id){return '<span class="ll '+id+'">'+(ly[id].label||id)+'</span>';}).join("");
      // REQ-15 FR-4: build a per-layer show/hide toggle from the schema so the operator reveals one layer
      // at a time / none / all. Toggling sets body.show-layer-<id>; the frame source starts all-hidden.
      var host=document.getElementById("layerToggles");
      if(host){
        host.innerHTML=ids.map(function(id){return '<label class="dbg-opt dbg-sub"><input type="checkbox" data-layer-toggle="'+id+'"><span>show '+(ly[id].label||id)+'</span></label>';}).join("");
        host.querySelectorAll("[data-layer-toggle]").forEach(function(cb){
          cb.addEventListener("change",function(){ document.body.classList.toggle("show-layer-"+cb.getAttribute("data-layer-toggle"), cb.checked); });
        });
      }
    }
    // REQ-15 FR-1 / REQ-view-definition-mode FR-1+FR-4: the requirement-free frame (scaffold + frame-bare)
    // is now driven by the panel's VIEW pick (syncView), which initialises from `payload.frame` and owns
    // the classes thereafter — so a re-render (lens toggle) can't re-force the frame after the operator
    // switches back to Requirement. Per-layer toggles still reveal a layer.
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
  // REQ-view-definition-mode: two clean axes. (1) VIEW — pick one: Requirement (default) vs the
  // requirement-free View Definition frame OF THIS renderer (scaffold + frame-bare, its own resolved
  // definition's regions/meta). (2) OVERLAYS — additive: Show node metadata (the item.meta reveal) ·
  // Outline regions (the template-anatomy outline overlay) · Hide app-scaffold chrome · the per-layer
  // disclosure toggles. Gated to a profile so the app path is byte-identical.
  if(payload.profile){
    // Live provenance readout — "all content is cruft until proven otherwise": chrome that traces to
    // a source is proven; an orphan (no source) is cruft. Green when clean, ochre when cruft remains.
    // FR-7: the bare frame has NO requirement content, so its empty chrome slots are not "cruft" —
    // they are definition slots. In frame mode read as a definition summary instead of false cruft.
    var ch=payload.chrome, prov="";
    if(payload.frame){
      var nreg=document.querySelectorAll("[data-scaffold]").length;
      var nlay=(payload.profile.regions&&payload.profile.regions.layers)?Object.keys(payload.profile.regions.layers).length:0;
      prov='<div class="dbg-prov dbg-clean">View Definition · '+nreg+' regions · '+nlay+' layers defined</div>';
    } else if(ch){
      var cruft=(ch.orphans||[]).length, cls=cruft?"dbg-cruft":"dbg-clean";
      prov='<div class="dbg-prov '+cls+'">provenance '+ch.score+' · '+ch.present+'/'+ch.total+' proven'+
        (cruft?' · <b>'+cruft+' cruft</b>: '+esc((ch.orphans||[]).join(", ")):' · no cruft ✓')+'</div>';
    }
    // Default HTML = the base taxonomy; applyDefinitionOverride() relabels groups/toggles from the
    // resolved definition's `control` over these ids (a domain delta can rename a group/toggle).
    document.getElementById("debug").innerHTML=
      '<div class="dbg-title">View mode</div>'+
      // ── VIEW: pick one — what am I looking at? the Requirement, or the View Definition ─────────
      '<div class="dbg-group dbg-group-first" data-group="view">View <span class="dbg-hint">· pick one</span></div>'+
      '<label class="dbg-opt"><input type="radio" name="viewpick" id="viewRequirement" checked><span>Requirement</span></label>'+
      '<label class="dbg-opt"><input type="radio" name="viewpick" id="viewDefinition"><span>View Definition</span></label>'+
      // ── OVERLAYS: additive filters, independent of the VIEW pick ───────────────────────────────
      // Show node metadata = the per-node item.meta reveal (the retired density modes' only unique
      // payload). Outline regions = the template-anatomy outline overlay (was "Scaffold mode"). Hide
      // app-scaffold chrome = the non-destructive cruft-purge. Per-layer toggles append below.
      '<div class="dbg-group" data-group="overlays">Overlays <span class="dbg-hint">· additive</span></div>'+
      '<label class="dbg-opt"><input type="checkbox" id="nodeMeta"><span>Show node metadata</span></label>'+
      '<label class="dbg-opt"><input type="checkbox" id="outlineRegions"><span>Outline regions</span></label>'+
      '<label class="dbg-opt"><input type="checkbox" id="hideScaffold"><span>Hide app-scaffold chrome</span></label>'+
      // REQ-15 FR-4: host for the per-layer disclosure toggles (built from the definition's layer schema
      // by applyDefinitionOverride). Empty in the served HTML; populated at runtime, byte-safe.
      '<div id="layerToggles"></div>'+
      '<div class="dbg-layers">layers: <span class="ll control">control</span>'+
        '<span class="ll descriptive">descriptive</span><span class="ll computed">computed</span>'+
        '<span class="ll node">node-driven</span></div>'+
      // ── DEBUG: raw view of the data + nodes being visualized (FR-8) — renders into #rawdata below sign-off
      '<div class="dbg-group" data-group="debug">Debug <span class="dbg-hint">· raw</span></div>'+
      '<label class="dbg-opt"><input type="checkbox" id="rawData"><span>Raw data</span></label>'+
      '<label class="dbg-opt"><input type="checkbox" id="nodeData"><span>Node data</span></label>'+
      '<label class="dbg-opt"><input type="checkbox" id="inspectCells"><span>Inspect cells</span></label>'+
      // ── PAGING: show N requirement nodes at a time + page through the rest (FR-9, pick-one) ──────
      '<div class="dbg-group" data-group="paging">Paging <span class="dbg-hint">· show N at a time</span></div>'+
      '<label class="dbg-opt"><input type="radio" name="pagepick" id="pageAll" checked><span>All</span></label>'+
      '<label class="dbg-opt"><input type="radio" name="pagepick" id="page10"><span>10</span></label>'+
      '<label class="dbg-opt"><input type="radio" name="pagepick" id="page5"><span>5</span></label>'+
      '<label class="dbg-opt"><input type="radio" name="pagepick" id="page1"><span>1 at a time</span></label>'+
      // ── PROVENANCE: the live readout stays at the bottom ──────────────────────────────────────
      prov;
    var viewReq=document.getElementById("viewRequirement"), viewDef=document.getElementById("viewDefinition");
    var nodeMeta=document.getElementById("nodeMeta"), outline=document.getElementById("outlineRegions");
    var hide=document.getElementById("hideScaffold");
    // ONE frame mechanism (FR-4): the View Definition pick and `--source frame` both drive
    // scaffold + frame-bare. `scaffold` (region outlines + ::before meta + legend) is on when EITHER
    // the View Definition pick OR the Outline-regions overlay is active; `frame-bare` (hide all region
    // CONTENT, leaving only the meta-descriptions) is on only for the View Definition pick.
    // FR-6: display-logic templates — when the View Definition is shown, EVERY region renders a
    // slot-annotated skeleton of WHAT it displays and FROM WHAT it derives (built from the real render
    // classes), so no region is blank. Injected client-side in frame mode only; removed on leaving it.
    // FR-13: the region display templates now come FROM the View Definition (payload.profile.region_templates,
    // projected by to_render_profile) — no longer hardcoded here. The interaction below stays template-side.
    var FRAME_TEMPLATES=(payload.profile&&payload.profile.region_templates)||{};
    function syncFrameTemplates(on){
      Object.keys(FRAME_TEMPLATES).forEach(function(id){
        var el=document.getElementById(id); if(!el) return;
        var existing=el.querySelector(".vd-template");
        if(on && !existing){
          // a <span> (inline element) can live inside #seclead's <p>; a <div> everywhere else.
          var wrap=document.createElement(el.tagName==="P"?"span":"div");
          wrap.className="vd-template"; wrap.innerHTML=FRAME_TEMPLATES[id]; el.appendChild(wrap);
        } else if(!on && existing){ existing.parentNode.removeChild(existing); }
      });
    }
    function syncView(){
      var vd=viewDef.checked;
      document.body.classList.toggle("scaffold", vd || outline.checked);
      document.body.classList.toggle("frame-bare", vd);
      syncFrameTemplates(vd);   // FR-6: show/hide every region's display-logic template with the View Definition
    }
    viewReq.onchange=syncView; viewDef.onchange=syncView; outline.onchange=syncView;
    nodeMeta.onchange=function(){ document.body.classList.toggle("show-node-meta", nodeMeta.checked); };
    hide.onchange=function(){ document.body.classList.toggle("hide-scaffold", hide.checked); };
    // FR-8: raw-data debug panel below the sign-off — Raw data = the current variant being visualized;
    // Node data = just the node items (flattened from the variant's sections). Rebuilt on each toggle.
    var rawData=document.getElementById("rawData"), nodeData=document.getElementById("nodeData"),
        inspectCells=document.getElementById("inspectCells");
    function nodeItems(){
      var out=[]; (data.sections||[]).forEach(function(sec){ (sec.items||[]).forEach(function(it){ out.push(it); }); });
      return out;
    }
    function renderRawData(){
      var el=document.getElementById("rawdata"); if(!el) return;
      var blocks="";
      if(rawData.checked){ blocks+='<div class="raw-cap">raw data being visualized — payload.variants["'+esc(cur)+'"]</div>'+
        '<pre class="raw-json">'+esc(JSON.stringify(data,null,2))+'</pre>'; }
      if(nodeData.checked){ var n=nodeItems(); blocks+='<div class="raw-cap">node data — '+n.length+' node(s) being visualized</div>'+
        '<pre class="raw-json">'+esc(JSON.stringify(n,null,2))+'</pre>'; }
      el.innerHTML=blocks; el.hidden=!(rawData.checked||nodeData.checked);
    }
    rawData.onchange=renderRawData; nodeData.onchange=renderRawData;
    // FR-10: per-cell inspector — under each card, show the node's data (every field + value) next to HOW
    // each field is displayed (field→element mapping, or "not displayed"). Uses each card's stashed
    // _nodeData (exact, not order-guessed). Re-applied after each renderAll (combined into the hook below).
    // FR-13: the field→element mapping now comes FROM the View Definition (payload.profile.field_display,
    // projected by to_render_profile) — no longer hardcoded. Each entry = {how it renders, card selector}.
    var INSPECT_MAP=(payload.profile&&payload.profile.field_display)||{};
    // FR-11: editing a not-displayed field is NON-PERSISTENT — it updates the card's in-memory node data
    // and surfaces the field as a line in the card, affecting only the shown HTML (never written to disk).
    function updateAddedLine(card, field, raw){
      // coerce ANY value to a string first — a node field can be a list/number/bool (approve_prompts,
      // confidence, technical, paths), and calling .trim() on those threw (the toggle silently failed).
      var val=(raw==null)?"":(typeof raw==="object"?JSON.stringify(raw):String(raw));
      var line=card.querySelector('[data-ni-add="'+field+'"]');
      if(val&&val.trim()){
        if(!line){ line=document.createElement("div"); line.className="ni-added";
          line.setAttribute("data-ni-add",field); card.insertBefore(line, card.querySelector(".node-inspect")); }
        line.textContent=field+": "+val;
      } else if(line){ line.parentNode.removeChild(line); }
    }
    function buildInspect(card){
      var item=card._nodeData||{}, d=document.createElement("div"); d.className="node-inspect";
      var rows=Object.keys(item).map(function(k){
        var v=item[k], val=(v==null)?"":(typeof v==="object"?JSON.stringify(v):String(v)), m=INSPECT_MAP[k];
        if(m){   // displayed field: read-only value + a switch (default ON) that toggles the element
          return '<tr><td class="ni-k">'+esc(k)+'</td><td class="ni-v">'+(esc(val)||"∅")+'</td>'+
            '<td class="ni-d"><label class="ni-sw"><input type="checkbox" checked data-ni-toggle="'+esc(m.sel)+'">'+
            '<span class="sw"></span></label>'+esc(m.how)+'</td></tr>';
        }        // not-displayed field: editable value + a switch (default OFF) that SURFACES the value in the card
        return '<tr><td class="ni-k">'+esc(k)+'</td>'+
          '<td class="ni-v ni-edit" contenteditable="true" data-ni-field="'+esc(k)+'">'+esc(val)+'</td>'+
          '<td class="ni-d"><label class="ni-sw"><input type="checkbox" data-ni-show="'+esc(k)+'">'+
          '<span class="sw"></span></label>show in card</td></tr>';
      }).join("");
      d.innerHTML='<table class="ni-table"><thead><tr><th>node data</th><th>value</th>'+
        '<th>how it’s displayed</th></tr></thead><tbody>'+rows+'</tbody></table>';
      // FR-11: editable not-displayed value → update in-memory data; editing auto-surfaces it (checks its switch)
      Array.prototype.forEach.call(d.querySelectorAll(".ni-edit"), function(cell){
        cell.addEventListener("input", function(){
          var f=cell.getAttribute("data-ni-field");
          card._nodeData[f]=cell.textContent;            // non-persistent, in-memory only
          var sw=d.querySelector('[data-ni-show="'+f+'"]'); if(sw) sw.checked=true;
          updateAddedLine(card, f, cell.textContent);     // reflect the edit in the card view
        });
      });
      // FR-12 (displayed): the switch toggles that element's display in THIS card (default on)
      Array.prototype.forEach.call(d.querySelectorAll("[data-ni-toggle]"), function(inp){
        inp.addEventListener("change", function(){
          var sel=inp.getAttribute("data-ni-toggle");
          Array.prototype.forEach.call(card.querySelectorAll(sel), function(el){
            if(el.closest(".node-inspect")) return;      // never toggle the inspector's own nodes
            el.style.display = inp.checked ? "" : "none";
          });
        });
      });
      // FR-12 (not-displayed): the switch SURFACES the field's value as a card line — reveal what isn't shown
      Array.prototype.forEach.call(d.querySelectorAll("[data-ni-show]"), function(inp){
        inp.addEventListener("change", function(){
          var f=inp.getAttribute("data-ni-show");   // pass the RAW value; updateAddedLine coerces (bool/num/list)
          updateAddedLine(card, f, inp.checked ? card._nodeData[f] : "");
        });
      });
      return d;
    }
    function syncInspect(on){
      var cards=Array.prototype.filter.call(document.querySelectorAll("#outline .item"),
        function(el){ return !el.closest(".vd-template"); });
      cards.forEach(function(card){
        var existing=card.querySelector(".node-inspect");
        if(on && !existing && card._nodeData){ card.appendChild(buildInspect(card)); }
        else if(!on && existing){ existing.parentNode.removeChild(existing);
          Array.prototype.forEach.call(card.querySelectorAll("[data-ni-add]"),
            function(l){ l.parentNode.removeChild(l); }); }   // drop the edit-surfaced lines too
      });
    }
    inspectCells.onchange=function(){ syncInspect(inspectCells.checked); };
    // FR-9: paging over the requirement nodes — pick-one page size shows N cards at a time; the #pagebar
    // pages through the rest, down to one at a time. Runs after each renderAll (via _pagingHook) so it
    // survives a lens/depth re-render. Operates on the real node cards (not the frame display template).
    var pageAll=document.getElementById("pageAll"), page10=document.getElementById("page10"),
        page5=document.getElementById("page5"), page1=document.getElementById("page1"), _page=0;
    function pageSize(){ return page1.checked?1 : page5.checked?5 : page10.checked?10 : Infinity; }
    function pagedCards(){
      // FR-4 (the bug fix): page only the SURVIVOR set — real cards (not the display template) carrying
      // NO pre-paging hide-reason (status/search/audience). Before this, pagedCards ignored `pf-hidden`,
      // so status filtering and paging didn't intersect ("showing X–Y of N" counted hidden cards). Now
      // paging composes with the pre-paging predicates by construction (the FR-5 seam is the single source).
      return Array.prototype.filter.call(document.querySelectorAll("#outline .item"),
        function(el){ return !el.closest(".vd-template") &&
          !PRE_PAGING_REASONS.some(function(r){ return el.classList.contains(r); }); });
    }
    function applyPaging(){
      var bar=document.getElementById("pagebar"), cards=pagedCards(), sz=pageSize();
      var secs=document.querySelectorAll("#outline details.sec");
      if(sz===Infinity){
        cards.forEach(function(c){ c.classList.remove("pg-hidden"); });
        secs.forEach(function(sc){ sc.classList.remove("pg-empty"); });
        bar.hidden=true; bar.innerHTML=""; return;
      }
      var total=cards.length, pages=Math.max(1, Math.ceil(total/sz));
      if(_page>=pages) _page=pages-1; if(_page<0) _page=0;
      var start=_page*sz, end=Math.min(start+sz, total);
      cards.forEach(function(c,i){ c.classList.toggle("pg-hidden", i<start||i>=end); });
      secs.forEach(function(sc){
        var vis=Array.prototype.some.call(sc.querySelectorAll(".item"), function(c){
          return !c.classList.contains("pg-hidden") && !c.closest(".vd-template"); });
        sc.classList.toggle("pg-empty", !vis);
      });
      bar.innerHTML='<button class="pg-btn" id="pg-prev"'+(_page===0?' disabled':'')+'>‹ prev</button>'+
        '<span class="pg-count">showing '+(total?start+1:0)+'–'+end+' of '+total+'  ·  page '+(_page+1)+' / '+pages+'</span>'+
        '<button class="pg-btn" id="pg-next"'+(_page>=pages-1?' disabled':'')+'>next ›</button>';
      bar.hidden=false;
      var pv=document.getElementById("pg-prev"), nx=document.getElementById("pg-next");
      if(pv) pv.onclick=function(){ _page--; applyPaging(); };
      if(nx) nx.onclick=function(){ _page++; applyPaging(); };
    }
    pageAll.onchange=page10.onchange=page5.onchange=page1.onchange=function(){ _page=0; applyPaging(); };
    // FR-1: the single visibility recompute point (now that applyPaging is in scope). Sole authority for
    // card shown/hidden = the union of hide-reason classes (CSS display:none per class). It recomputes the
    // composed PRE-PAGING section emptiness (dim a section with no pre-paging survivor — preserving the
    // status filter's collapse), then re-pages the survivor set so paging composes with status/search/aud.
    applyVisibility=function(){
      var secs=document.querySelectorAll("#outline details.sec");
      secs.forEach(function(sec){
        var cards=sec.querySelectorAll(".item[data-status]"), any=false;
        cards.forEach(function(c){
          if(c.closest(".vd-template")) return;
          if(!PRE_PAGING_REASONS.some(function(r){ return c.classList.contains(r); })) any=true;
        });
        sec.classList.toggle("pf-empty", cards.length>0 && !any);   // dim when no pre-paging survivor
      });
      applyPaging();   // re-page over the fresh survivor set (pg-hidden applied LAST)
    };
    // FR-6: renderAll re-applies the COMPOSED visibility (status ∧ page) + the per-cell inspector after
    // rebuilding the cards — so the composition survives a lens/depth variant re-render, as paging did.
    _pagingHook=function(){ applyVisibility(); syncInspect(inspectCells.checked); };
    // `--source frame`: reflect the requirement-free frame in the picker so toggling back works.
    if(payload.frame){ viewDef.checked=true; viewReq.checked=false; }
    syncView();
  }

  window.addEventListener("hashchange", resolveHash);   // full-page route: react to #<key> / back
  renderAll();
})();
</script>
</body>
</html>
"""
