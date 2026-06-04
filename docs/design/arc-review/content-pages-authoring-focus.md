# CRP Focus — Content-Pages UI Authoring (default-on / multi-user gate)

The page-authoring capability (`--pages-authoring`) is **built and gated OFF by default**, sound for
its stated bound: **NFR-UI-1 — local-first, single-user, no auth**. This review is the gate before any
decision to (a) enable it by default in every generated app, or (b) expose authoring beyond local
single-user. Weight findings toward what *changes when that bound is removed*.

## Where we need input most

1. **Raw-HTML self-XSS in prose → stored XSS at multi-user.** python-markdown passes raw HTML through;
   the generated app renders prose at generate time and serves it. Harmless self-XSS locally. What is the
   right control before multi-user/default-on — sanitize at generate time (bleach/allowlist), escape, a
   CSP, or a documented "trusted-authors-only" boundary? Where should it live (SDK generate-time vs app)?

2. **Concurrent-POST race on `pages.yaml`/`.md`.** Read-modify-write with no lock; lost updates under
   concurrency. Acceptable single-user. What's the minimal correct mechanism if authoring is shared
   (file lock, optimistic version check on the manifest, single-writer queue)?

3. **Broader manifest shapes.** The owned safe-append supports only block-style, consistently-indented
   `pages:`; flow-style / odd-indent fail loud without corruption (write gated on a clean reparse). Is
   "fail-loud + document the supported shape" acceptable, or should the append normalize/round-trip
   arbitrary valid YAML (e.g. a comment-preserving round-tripper)? Trade-off vs. the no-SDK-import,
   minimal-runtime-deps constraint.

4. **The generated-owned validator drifting from the SDK `parse_pages`.** `app/pages_io.py` re-emits the
   strict-parse rules as owned code (the app must not import the SDK). How do we keep the two in sync over
   time — a shared contract test, codegen from one source, or a versioned rule-set? What breaks if they
   diverge (UI accepts a manifest the next `generate backend` rejects)?

5. **Disk-write endpoint as an attack surface.** Even gated/local, the app exposes POST routes that write
   into the project source tree. Beyond slugify + `parent == app/pages/` containment, what else matters at
   exposure (auth hook, path/size limits, rate limiting, refusing symlinked targets, write-scope allowlist)?

6. **Atomicity / rollback completeness.** Create validates-then-writes-prose-then-commits-manifest with
   prose rollback on manifest failure. Are there partial-failure windows left (e.g. manifest write
   succeeds, process dies before response; orphan `.md` overwrite/rollback-delete of a pre-existing file)?
