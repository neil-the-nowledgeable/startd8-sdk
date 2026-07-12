# Remote Onboarding Guide (FR-E15)

**The headline flow:** a project owner invites a *remote* stakeholder to run a guided kickoff session
in their browser — no CLI, no install, no shared credentials — while the owner keeps full control:
every write the stakeholder proposes is mirrored, audited, reviewed, and applied *by the owner*.

This guide packages pieces that already ship (the cloud authorization grant, the FR-E12 magic-link
door, `--mirror-cockpit`, the audit log, the agentic cockpit, and VIPP apply). One command
(`startd8 cloud-grant invite`) assembles the operator's side; this doc explains the concepts and the
end-to-end runbook.

---

## Who does what

| Role | Has | Does |
|------|-----|------|
| **Operator** (project owner) | the platform's identity (SSH/IAM/CLI), the grant store | issues the invite, runs the server, reviews + applies |
| **Stakeholder** (remote) | a one-time link | clicks it, has a guided conversation, proposes inputs |

The stakeholder never gets the API key, never touches the CLI, and **cannot write** anything directly —
the agentic loop only *recommends*; the operator confirms every write (the same human gate as a local
session).

---

## The one-command invite

```bash
startd8 cloud-grant invite \
  --for-serve /path/to/project \        # project_id = its directory name (issue↔serve can't drift)
  --serve-url https://app.example \     # where the stakeholder's browser reaches the server
  --cloud-origin https://app.example \  # the FR-14 Origin factor
  --deployment prod-1 \                 # (or STARTD8_DEPLOYMENT_ID)
  --issued-by you@team \
  --ttl 1h --uses 1                     # bounded: one use, expires in an hour (defaults)
```

It **issues a bounded, audited grant + a one-time magic link**, generates the consumer API key, and
prints the **operator playbook** — the exact serve command, the link to send, and how to review +
apply. Nothing new happens under the hood; it stitches the shipped pieces together so you run one
command instead of the grant CLI *plus* the serve flags.

## The 4-step runbook (what `invite` prints)

1. **Start the server** (you, on the deployment host) — the printed
   `startd8 kickoff start … --cloud --api-key … --grant-store … --deployment-id … --cloud-origin …`
   command. `--cloud` keeps the surface read/preview-only *except* the grant-authorized chat path;
   `--mirror-cockpit` (default on non-hosted) mirrors the redacted session to `.startd8` for the cockpit.
2. **Send the one-time link** to the stakeholder:
   `https://app.example/kickoff/enter?t=<token>`. They click it; the server verifies + **burns** the
   token, **consumes one grant use**, mints a browser session, and drops them straight into the guided
   agentic chat — **no CLI, no API key on their side** (FR-E12). Per-turn actions re-validate the grant
   (no re-consume); a revoked/expired grant ends the session on its next turn.
3. **Review what they proposed** — their session mirrors to the cockpit. Read the proposals
   (`startd8 kickoff proposals <project>`) or the Grafana cockpit
   (`kickoff portal --dynamic --provision <grafana>`), and the readout
   (`startd8 kickoff readout <project> --format md --out onboarding.md`) is a shareable summary of
   *what was captured, what's blocked, and the proposed next actions*.
4. **Apply the ones you accept** — the human-gated write path:
   `startd8 vipp negotiate` → `startd8 vipp apply`. The stakeholder's proposals never touch the
   source of record until *you* confirm them.

---

## Why it's safe (the trust chain, briefly)

- **Bounded + expiring + revocable.** The grant is use-limited (default 1) and TTL-bounded (default
  1h); `startd8 cloud-grant revoke <id>` kills it — and any session minted from it — immediately.
- **The link is the credential.** Possession of the one-time link authorizes exactly one session; it
  is burned on first click, so a leaked link in browser history is inert afterward. **Serve over
  HTTPS** and treat the link + API key as secrets.
- **Audited.** Every issue / consume / redeem / revoke is appended to a fail-closed audit log; the
  FR-E4 metrics + FR-E22 alerts surface denial spikes (probing) in Grafana.
- **Fail-closed.** A missing/invalid api-key, an unconfigured Origin, or an absent grant denies with
  no use spent; the served app holds the store **consume-only** (structurally, on the SQLite backend).
- **Writes stay with the owner.** The stakeholder proposes; VIPP apply (human-confirmed) is the only
  path to the source of record.

## Scope

Minimal, **single remote stakeholder at a time** — no multi-user identity/IdP (deferred to a hosted
future). For local single-user use, you don't need any of this: run `startd8 kickoff concierge-chat`
directly. This flow exists for the *remote* case where the person onboarding isn't at your machine.

## Reference

- Grant primitive + trust chain — `CLOUD_MIRROR_GRANT_REQUIREMENTS.md`
- The magic-link human door — `CLOUD_HUMAN_DOOR_REQUIREMENTS.md` (FR-E12)
- Enhancements catalog — `GRANT_AND_COCKPIT_ENHANCEMENTS.md`
