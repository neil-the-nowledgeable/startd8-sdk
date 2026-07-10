import React, { useCallback, useState } from 'react';
import { PanelProps } from '@grafana/data';
import { Alert, Button, Checkbox, Field, TextArea, useStyles2 } from '@grafana/ui';
import { css } from '@emotion/css';
import { ApplyPreviewResult, ApplyResultView, ConsensusSignal, StakeholdersPanelOptions } from '../types';
import { errText, proxyPost } from '../api';

type Props = PanelProps<StakeholdersPanelOptions>;

type Phase = 'idle' | 'previewing' | 'reviewing' | 'ratifying' | 'done';

/**
 * FR-R7 apply gate — the two-screen preview → (copy challenge) → ratify flow. Writes the project
 * source of record, so it is deliberately two requests. **Token-gated, not human-proof** — the honest
 * banner says so. The challenge is copied from screen 1 and pasted into screen 2 (the deliberate act);
 * ratify applies only the selected proposal ids.
 */
export const ApplyPanel: React.FC<Props> = ({ options, width, height }) => {
  const styles = useStyles2(getStyles);
  const [phase, setPhase] = useState<Phase>('idle');
  const [preview, setPreview] = useState<ApplyPreviewResult | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [challengeInput, setChallengeInput] = useState('');
  const [result, setResult] = useState<ApplyResultView | null>(null);
  const [error, setError] = useState<string | null>(null);

  const configured = Boolean(options.datasourceUid);

  const reset = useCallback(() => {
    setPreview(null);
    setSelected(new Set());
    setChallengeInput('');
    setResult(null);
    setError(null);
  }, []);

  // Screen 1 — pure preview (no writes): reconstruct the would-apply set + mint a single-use challenge.
  const handlePreview = useCallback(async () => {
    if (!configured) {
      return;
    }
    reset();
    setPhase('previewing');
    try {
      const p = await proxyPost<ApplyPreviewResult>(options.datasourceUid, 'stakeholders/apply/preview', {});
      setPreview(p);
      setSelected(new Set(p.would_apply.map((w) => w.proposal_id))); // default: apply all previewed
      setPhase('reviewing');
    } catch (err) {
      setError(errText(err));
      setPhase('idle');
    }
  }, [configured, options.datasourceUid, reset]);

  const toggle = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  // Screen 2 — ratify: verify the pasted challenge server-side and apply ONLY the selected ids.
  const handleRatify = useCallback(async () => {
    if (!preview || selected.size === 0 || !challengeInput.trim()) {
      return;
    }
    setPhase('ratifying');
    setError(null);
    try {
      const r = await proxyPost<ApplyResultView>(options.datasourceUid, 'stakeholders/apply/ratify', {
        proposal_ids: Array.from(selected),
        challenge: challengeInput.trim(),
      });
      setResult(r);
      setPhase('done');
    } catch (err) {
      setError(errText(err)); // stale seq / expired / already-used → re-preview
      setPhase('reviewing');
    }
  }, [preview, selected, challengeInput, options.datasourceUid]);

  return (
    <div className={styles.container} style={{ width, height }}>
      <Alert severity="warning" title="Token-gated — not human-proof">
        This writes your project&apos;s <b>source of record</b>. Anyone holding the endpoint token can
        drive preview → ratify; the two-step flow is a deliberate act, not a human gate.
      </Alert>

      {!configured && (
        <Alert severity="warning" title="Not configured">
          Set <b>Run datasource UID</b> to a datasource that proxies <code>/stakeholders/*</code> (it adds
          the bearer token server-side).
        </Alert>
      )}

      <div className={styles.actions}>
        <Button
          onClick={handlePreview}
          disabled={!configured || phase === 'previewing' || phase === 'ratifying'}
          variant="secondary"
        >
          {phase === 'previewing' ? 'Previewing…' : preview ? 'Re-preview' : 'Preview apply'}
        </Button>
        {(preview || result || error) && (
          <Button variant="secondary" fill="text" onClick={() => { reset(); setPhase('idle'); }}>
            Clear
          </Button>
        )}
      </div>

      {error && <Alert severity="error" title="Apply blocked">{error}</Alert>}

      {/* Screen 1 result — the would-apply set + the challenge to copy. */}
      {preview && phase !== 'done' && (
        <div className={styles.section}>
          <ConsensusNote consensus={preview.consensus} styles={styles} />
          {preview.would_apply.length === 0 ? (
            <div className={styles.dim}>Nothing would apply (no accepted, un-applied proposals at this seq).</div>
          ) : (
            <>
              <div className={styles.head}>
                Would apply {preview.would_apply.length} proposal(s) at seq {preview.envelope_seq}:
              </div>
              {preview.would_apply.map((w) => (
                <Checkbox
                  key={w.proposal_id}
                  label={`${w.proposal_id} · ${w.kind}${w.value_path ? ` · ${w.value_path}` : ''}`}
                  value={selected.has(w.proposal_id)}
                  onChange={() => toggle(w.proposal_id)}
                />
              ))}

              {/* Screen 2 — paste the challenge, then ratify. */}
              <Field
                label="Challenge"
                description={`Copy this, then paste it below to ratify (expires in ${preview.expires_in_seconds}s, single-use).`}
              >
                <TextArea readOnly rows={2} value={preview.challenge} />
              </Field>
              <Field label="Paste challenge to confirm">
                <TextArea
                  rows={2}
                  value={challengeInput}
                  onChange={(e) => setChallengeInput(e.currentTarget.value)}
                  placeholder="Paste the challenge string from above"
                />
              </Field>
              <Button
                variant="destructive"
                onClick={handleRatify}
                disabled={selected.size === 0 || !challengeInput.trim() || phase === 'ratifying'}
              >
                {phase === 'ratifying' ? 'Applying…' : `Ratify & apply (${selected.size} selected)`}
              </Button>
            </>
          )}
        </div>
      )}

      {/* Result. */}
      {result && (
        <div className={styles.section}>
          <div className={styles.head}>
            Applied {result.wrote}/{result.actionable} · inbox {result.inbox_shredded ? 'shredded' : 'retained'}
          </div>
          {result.outcomes.map((o) => (
            <div key={o.proposal_id} className={styles.dim}>
              {o.proposal_id}: {o.code}
              {o.detail ? ` — ${o.detail}` : ''}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

const CONSENSUS_SEVERITY: Record<string, 'success' | 'warning' | 'error'> = {
  high: 'success',
  mixed: 'warning',
  low: 'error',
};

// #8 — the source facilitation's consensus, shown on the apply preview so a low-consensus (contentious)
// set is flagged before it's committed. Unlike FacilitatePanel's chip, this ALSO shows n/a (R2-F4): the
// operator should know consensus was attempted, not silently absent. The binding is unverified metadata.
const ConsensusNote: React.FC<{
  consensus?: ConsensusSignal;
  styles: ReturnType<typeof getStyles>;
}> = ({ consensus, styles }) => {
  if (!consensus) {
    return null;
  }
  if (consensus.label === 'n/a') {
    return (
      <div className={styles.dim}>
        Consensus: n/a — no source facilitation could be linked to this inbox (or ≤1 rateable persona).
      </div>
    );
  }
  const sev = CONSENSUS_SEVERITY[consensus.label] ?? 'warning';
  return (
    <Alert severity={sev} title={`Consensus: ${consensus.label.toUpperCase()} (n=${consensus.n})`}>
      <span className={styles.dim}>
        Synthetic, lexical ({consensus.basis}
        {typeof consensus.score === 'number' ? `, score ${consensus.score.toFixed(2)}` : ''}) — how
        similarly the personas framed their independent R1 takes. Low = read closely before committing,
        not a verdict; the source-session binding is unverified metadata (token-gated, not human-proof).
      </span>
    </Alert>
  );
};

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
  section: css`
    display: flex;
    flex-direction: column;
    gap: 6px;
  `,
  head: css`
    font-weight: 500;
  `,
  dim: css`
    color: var(--text-secondary, #8e8e8e);
    font-size: 12px;
  `,
});
