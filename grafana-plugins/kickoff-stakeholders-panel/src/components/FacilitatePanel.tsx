import React, { useCallback, useEffect, useRef, useState } from 'react';
import { PanelProps } from '@grafana/data';
import { Alert, Button, Collapse, ConfirmModal, Field, Input, RadioButtonGroup, Spinner, useStyles2 } from '@grafana/ui';
import { css } from '@emotion/css';
import {
  ConsensusSignal,
  FacilitateDryRunResult,
  FacilitateStartResult,
  FacilitateStatusResult,
  RoundSummary,
  StakeholdersPanelOptions,
} from '../types';
import { errText, proxyGet, proxyPost } from '../api';

type Props = PanelProps<StakeholdersPanelOptions>;

type Phase = 'idle' | 'previewing' | 'confirm' | 'polling' | 'done';

// H-16 — the poll is bounded: a stuck/never-terminal run stops polling after this many ticks rather
// than hammering the endpoint forever. 120 × 5s ≈ 10 minutes, comfortably past a normal facilitation.
const POLL_INTERVAL_MS = 5000;
const MAX_POLLS = 120;

const POSTURE_OPTIONS = [
  { value: 'scrutiny', label: 'Scrutiny' },
  { value: 'prototype', label: 'Prototype' },
];
const TIER_OPTIONS = [
  { value: 'premium', label: 'Premium' },
  { value: 'cheap', label: 'Cheap' },
];

/**
 * Facilitate mode — a thin fire-and-poll driver over the tested Python routes. The facilitation runs
 * for minutes, so this is NOT one blocking request: Preview (dry-run, $0) → confirm echoing the exact
 * `run_key` → POST spawns a background worker and returns a `session_id` → bounded poll of
 * `GET /facilitate/{session_id}` until terminal. A Cancel button signals the in-flight run. The bearer
 * token stays server-side (datasource proxy); this component only knows the datasource UID.
 */
export const FacilitatePanel: React.FC<Props> = ({ options, width, height }) => {
  const styles = useStyles2(getStyles);
  const [posture, setPosture] = useState<string>(options.posture ?? 'scrutiny');
  const [tier, setTier] = useState<string>(options.tier ?? 'premium');
  const [cap, setCap] = useState<number | undefined>(options.defaultCap);
  const [phase, setPhase] = useState<Phase>('idle');
  const [dryRun, setDryRun] = useState<FacilitateDryRunResult | null>(null);
  const [start, setStart] = useState<FacilitateStartResult | null>(null);
  const [status, setStatus] = useState<FacilitateStatusResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const pollsRef = useRef(0);

  const configured = Boolean(options.datasourceUid);
  const capBody = cap ?? null;

  const reset = useCallback(() => {
    setDryRun(null);
    setStart(null);
    setStatus(null);
    setError(null);
    setCancelling(false);
    pollsRef.current = 0;
  }, []);

  // Step 1 — dry-run (no spend): honest round-weighted estimate + a run_key bound to posture/tier/cap.
  const handlePreview = useCallback(async () => {
    if (!configured) {
      return;
    }
    reset();
    setPhase('previewing');
    try {
      const d = await proxyPost<FacilitateDryRunResult>(options.datasourceUid, 'stakeholders/facilitate', {
        dry_run: true,
        posture,
        tier,
        cap: capBody,
      });
      setDryRun(d);
      setPhase('confirm');
    } catch (err) {
      setError(errText(err));
      setPhase('idle');
    }
  }, [configured, options.datasourceUid, posture, tier, capBody, reset]);

  // Step 2 — confirm: ECHO the dry-run's run_key so the spawned run is provably the previewed one
  // (H-10). The response is the fire-and-poll handle (session_id); the worker runs in the background.
  const handleConfirm = useCallback(async () => {
    if (!dryRun) {
      return;
    }
    setPhase('polling');
    pollsRef.current = 0;
    try {
      const s = await proxyPost<FacilitateStartResult>(options.datasourceUid, 'stakeholders/facilitate', {
        posture,
        tier,
        cap: capBody,
        run_key: dryRun.run_key, // <-- binds the spawn to the exact previewed dry-run
      });
      setStart(s);
      // A dedup-to-terminal spawn may already be done — the poll effect will settle it either way.
      setStatus({ session_id: s.session_id, status: s.status, is_terminal: false });
    } catch (err) {
      setError(errText(err));
      setPhase('idle');
    }
  }, [dryRun, options.datasourceUid, posture, tier, capBody]);

  // Step 3 — bounded poll (H-16). One in-flight GET at a time via setTimeout recursion; stops on a
  // terminal status, on the poll cap, or when the component unmounts / the run is cleared.
  useEffect(() => {
    if (phase !== 'polling' || !start?.session_id) {
      return;
    }
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const tick = async () => {
      if (cancelled) {
        return;
      }
      pollsRef.current += 1;
      try {
        const st = await proxyGet<FacilitateStatusResult>(
          options.datasourceUid,
          `stakeholders/facilitate/${encodeURIComponent(start.session_id)}`
        );
        if (cancelled) {
          return;
        }
        setStatus(st);
        if (st.is_terminal) {
          setPhase('done');
          return;
        }
      } catch (err) {
        if (cancelled) {
          return;
        }
        // A transient poll failure is non-fatal — keep polling until terminal or the cap; surface it.
        setError(errText(err));
      }
      if (pollsRef.current >= MAX_POLLS) {
        setError('Stopped polling after the time limit — the run may still be going. Use “Check again”.');
        setPhase('done');
        return;
      }
      timer = setTimeout(tick, POLL_INTERVAL_MS);
    };

    // First poll is immediate (next macrotask) so a dedup-to-terminal spawn settles at once and a
    // live run shows a first status without a 5s blank; subsequent polls space out by the interval.
    timer = setTimeout(tick, 0);
    return () => {
      cancelled = true;
      if (timer) {
        clearTimeout(timer);
      }
    };
  }, [phase, start, options.datasourceUid]);

  // Cancel an in-flight facilitation by the session_id the poller holds (H-9/H-17). Already-completed
  // rounds persist; the run resolves to a terminal `cancelled` on the next poll.
  const handleCancel = useCallback(async () => {
    if (!start?.session_id || cancelling) {
      return;
    }
    setCancelling(true);
    try {
      await proxyPost(
        options.datasourceUid,
        `stakeholders/facilitate/${encodeURIComponent(start.session_id)}/cancel`,
        {}
      );
    } catch (err) {
      // A failed cancel is non-fatal — the run may finish on its own; surface it and keep polling.
      setError(errText(err));
    } finally {
      setCancelling(false);
    }
  }, [start, cancelling, options.datasourceUid]);

  // Manual re-poll after the bounded loop gave up (or to refresh a still-running status).
  const handleCheckAgain = useCallback(async () => {
    if (!start?.session_id) {
      return;
    }
    try {
      const st = await proxyGet<FacilitateStatusResult>(
        options.datasourceUid,
        `stakeholders/facilitate/${encodeURIComponent(start.session_id)}`
      );
      setStatus(st);
      if (!st.is_terminal) {
        pollsRef.current = 0;
        setError(null);
        setPhase('polling');
      }
    } catch (err) {
      setError(errText(err));
    }
  }, [start, options.datasourceUid]);

  const busy = phase === 'previewing' || phase === 'polling';

  return (
    <div className={styles.container} style={{ width, height }}>
      {!configured && (
        <Alert severity="warning" title="Not configured">
          Set the panel option <b>Run datasource UID</b> to a datasource that proxies{' '}
          <code>/stakeholders/*</code> to the run endpoint (it adds the bearer token server-side).
        </Alert>
      )}

      <Field label="Posture" description="Scrutiny = strategic red-team. Prototype = constructive early-stage UX.">
        <RadioButtonGroup options={POSTURE_OPTIONS} value={posture} onChange={(v) => setPosture(v!)} disabled={busy} />
      </Field>
      <Field label="Model tier" description="Premium = opus/gpt-5.5/gemini-pro. Cheap = haiku/mini/flash.">
        <RadioButtonGroup options={TIER_OPTIONS} value={tier} onChange={(v) => setTier(v!)} disabled={busy} />
      </Field>
      <Field label="Cap" description="Max personas in the panel (empty = all). Bounds spend.">
        <Input
          type="number"
          value={cap ?? ''}
          width={12}
          disabled={busy}
          onChange={(e) => {
            const v = e.currentTarget.value;
            setCap(v === '' ? undefined : Number(v));
          }}
        />
      </Field>

      <div className={styles.actions}>
        <Button onClick={handlePreview} disabled={!configured || busy} variant="primary">
          {phase === 'previewing' ? 'Estimating…' : phase === 'polling' ? 'Running…' : 'Preview cost'}
        </Button>
        {phase === 'polling' && (
          <Button variant="destructive" onClick={handleCancel} disabled={cancelling}>
            {cancelling ? 'Cancelling…' : 'Cancel'}
          </Button>
        )}
        {phase === 'done' && (
          <>
            <Button variant="secondary" onClick={handleCheckAgain}>
              Check again
            </Button>
            <Button variant="secondary" fill="text" onClick={() => { reset(); setPhase('idle'); }}>
              Clear
            </Button>
          </>
        )}
      </div>

      {error && <Alert severity="error" title="Facilitation notice">{error}</Alert>}

      {/* Confirm modal — the honest round-weighted estimate BEFORE any spend. */}
      {dryRun && (
        <ConfirmModal
          isOpen={phase === 'confirm'}
          title="Run the facilitation? (paid, multi-round)"
          body={
            <div className={styles.estimate}>
              <div>
                <b>{dryRun.n_participants}</b> participants · <b>{dryRun.posture}</b> · <b>{dryRun.tier}</b> tier
              </div>
              <div>
                ~<b>{dryRun.projected_calls}</b> model calls · estimated <b>~${dryRun.estimated_cost.toFixed(4)}</b>
              </div>
              <div className={styles.dim}>Models: {Object.values(dryRun.models).join(', ')}</div>
              <div className={styles.dim}>{dryRun.note}</div>
              <div className={styles.dim}>This runs for minutes in the background — you can poll or cancel it.</div>
              <div className={styles.dim}>Output is synthetic and unratified.</div>
            </div>
          }
          confirmText={`Run (~$${dryRun.estimated_cost.toFixed(4)})`}
          onConfirm={handleConfirm}
          onDismiss={() => setPhase('idle')}
        />
      )}

      {status && (phase === 'polling' || phase === 'done') && (
        <StatusView status={status} styles={styles} polling={phase === 'polling'} />
      )}
    </div>
  );
};

const TERMINAL_LABEL: Record<string, string> = {
  completed: 'Completed',
  cancelled: 'Cancelled',
  error: 'Errored',
  unknown: 'Not visible yet',
};

const CONSENSUS_SEVERITY: Record<string, 'success' | 'warning' | 'error'> = {
  high: 'success',
  mixed: 'warning',
  low: 'error',
};

// #6 — the synthetic lexical-consensus signal over the independent R1 answers. Shown only when it's
// rateable (≥2 non-challenger personas); the caveat text keeps it honest (divergence in wording, not
// proven semantic agreement).
const ConsensusChip: React.FC<{
  consensus?: ConsensusSignal;
  styles: ReturnType<typeof getStyles>;
}> = ({ consensus, styles }) => {
  if (!consensus || consensus.label === 'n/a') {
    return null;
  }
  const sev = CONSENSUS_SEVERITY[consensus.label] ?? 'warning';
  return (
    <Alert severity={sev} title={`Consensus: ${consensus.label.toUpperCase()} (n=${consensus.n})`}>
      <span className={styles.dim}>
        Synthetic, lexical signal ({consensus.basis}
        {typeof consensus.score === 'number' ? `, score ${consensus.score.toFixed(2)}` : ''}) — how
        similarly the personas framed their independent R1 takes. Low = worth a closer read, not a
        verdict; it is not proven semantic agreement.
      </span>
    </Alert>
  );
};

// #7 — the live per-round accordion. Grows as rounds land; the latest round is expanded by default so
// the operator watches the freshest contributions fill in. Excerpts are bounded previews (synthetic).
const RoundsView: React.FC<{
  rounds?: RoundSummary[];
  styles: ReturnType<typeof getStyles>;
}> = ({ rounds, styles }) => {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  if (!rounds || rounds.length === 0) {
    return null;
  }
  const lastId = rounds[rounds.length - 1].round_id;
  return (
    <div className={styles.rounds}>
      {rounds.map((r) => {
        const isOpen = open[r.round_id] ?? r.round_id === lastId; // latest expanded by default
        return (
          <Collapse
            key={r.round_id}
            label={`${r.round_id}${r.title ? ` — ${r.title}` : ''} · ${r.entries.length} contribution(s)`}
            isOpen={isOpen}
            onToggle={() => setOpen((o) => ({ ...o, [r.round_id]: !isOpen }))}
            collapsible
          >
            {r.entries.length === 0 ? (
              <div className={styles.dim}>…waiting for contributions…</div>
            ) : (
              r.entries.map((e, i) => (
                <div key={i} className={styles.answer}>
                  <div className={styles.answerHead}>
                    <b>{e.display_name || e.role_id}</b>
                    {e.is_challenger && <span className={styles.dim}> · challenger</span>}
                    {e.grounding && <span className={styles.dim}> · {e.grounding}</span>}
                  </div>
                  <div className={styles.pre}>{e.excerpt}</div>
                </div>
              ))
            )}
          </Collapse>
        );
      })}
    </div>
  );
};

const StatusView: React.FC<{
  status: FacilitateStatusResult;
  styles: ReturnType<typeof getStyles>;
  polling: boolean;
}> = ({ status, styles, polling }) => (
  <div className={styles.results}>
    <div className={styles.resultHead}>
      session <code>{status.session_id}</code> ·{' '}
      {polling ? (
        <span>
          <Spinner inline size={12} /> {status.status} · round {status.rounds_completed ?? 0}
        </span>
      ) : (
        <span>{TERMINAL_LABEL[status.status] ?? status.status}</span>
      )}
      {typeof status.cost_so_far_usd === 'number' && status.cost_so_far_usd > 0 && (
        <span className={styles.dim}> · ~${status.cost_so_far_usd.toFixed(4)}</span>
      )}
    </div>

    <ConsensusChip consensus={status.consensus} styles={styles} />

    <Alert severity="warning" title="Synthetic &amp; unratified">
      Role-played stand-ins, not real stakeholders. Confirm with a human before relying on this synthesis.
    </Alert>

    <RoundsView rounds={status.rounds} styles={styles} />

    {status.stalled && !status.is_terminal && (
      <Alert severity="warning" title="Possibly stalled">
        No progress in a while — the facilitation worker may have died (e.g. a server restart). Try{' '}
        <b>Check again</b>; if it stays stalled, re-run it.
      </Alert>
    )}

    {status.status === 'error' && (
      <Alert severity="error" title="Facilitation errored">{status.error || 'The run ended in an error state.'}</Alert>
    )}
    {status.status === 'cancelled' && (
      <div className={styles.dim}>Cancelled — showing whatever rounds completed before cancellation.</div>
    )}
    {status.halt && (
      <Alert severity="info" title="Facilitation halted (assumptions gate)">
        <div className={styles.pre}>{status.halt}</div>
      </Alert>
    )}
    {status.synthesis && (
      <div className={styles.answer}>
        <div className={styles.pre}>{status.synthesis}</div>
      </div>
    )}
  </div>
);

const getStyles = () => ({
  container: css`
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 8px;
    overflow: auto;
  `,
  actions: css`
    display: flex;
    gap: 8px;
    align-items: center;
  `,
  estimate: css`
    display: flex;
    flex-direction: column;
    gap: 4px;
  `,
  dim: css`
    color: var(--text-secondary, #8e8e8e);
    font-size: 12px;
  `,
  results: css`
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-top: 8px;
  `,
  resultHead: css`
    font-size: 12px;
    color: var(--text-secondary, #8e8e8e);
  `,
  answer: css`
    padding: 8px;
    background: var(--background-secondary, rgba(255, 255, 255, 0.03));
    border-radius: 4px;
  `,
  answerHead: css`
    margin-bottom: 4px;
    font-size: 12px;
  `,
  pre: css`
    white-space: pre-wrap;
    font-family: inherit;
    margin: 0;
  `,
  rounds: css`
    display: flex;
    flex-direction: column;
    gap: 4px;
  `,
});
