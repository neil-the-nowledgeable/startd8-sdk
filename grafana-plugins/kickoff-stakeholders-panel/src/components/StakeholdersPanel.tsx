import React, { useCallback, useState } from 'react';
import { PanelProps } from '@grafana/data';
import { Alert, Button, ConfirmModal, Field, Input, TextArea, useStyles2 } from '@grafana/ui';
import { css } from '@emotion/css';
import { DryRunResult, PanelAnswerView, RunResult, StakeholdersPanelOptions } from '../types';
import { ApplyPanel } from './ApplyPanel';
import { FacilitatePanel } from './FacilitatePanel';
import { TriagePanel } from './TriagePanel';
import { errText, proxyPost } from '../api';

type Props = PanelProps<StakeholdersPanelOptions>;

type Phase = 'idle' | 'previewing' | 'confirm' | 'running' | 'done';

export const StakeholdersPanel: React.FC<Props> = (props) => {
  // The registered panel dispatches to the FR-R7 apply gate, the multi-round facilitation, or the
  // triage→write surface when configured; otherwise it shows the single-question paid Q&A run.
  if (props.options.mode === 'apply') {
    return <ApplyPanel {...props} />;
  }
  if (props.options.mode === 'facilitate') {
    return <FacilitatePanel {...props} />;
  }
  if (props.options.mode === 'triage') {
    return <TriagePanel {...props} />;
  }
  return <RunPanel {...props} />;
};

const RunPanel: React.FC<Props> = ({ options, width, height }) => {
  const styles = useStyles2(getStyles);
  const [question, setQuestion] = useState('');
  const [cap, setCap] = useState<number | undefined>(options.defaultCap);
  const [phase, setPhase] = useState<Phase>('idle');
  const [dryRun, setDryRun] = useState<DryRunResult | null>(null);
  const [result, setResult] = useState<RunResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);

  const configured = Boolean(options.datasourceUid);

  const reset = useCallback(() => {
    setDryRun(null);
    setResult(null);
    setError(null);
    setCancelling(false);
  }, []);

  // Step 1 — dry-run (no spend): honest estimate + a run_key, then open the confirm modal.
  const handlePreview = useCallback(async () => {
    if (!question.trim() || !configured) {
      return;
    }
    reset();
    setPhase('previewing');
    try {
      const d = await proxyPost<DryRunResult>(options.datasourceUid, 'stakeholders/run', {
        question: question.trim(),
        cap: cap ?? null,
        dry_run: true,
      });
      setDryRun(d);
      setPhase('confirm');
    } catch (err) {
      setError(errText(err));
      setPhase('idle');
    }
  }, [question, cap, configured, options.datasourceUid, reset]);

  // Step 2 — confirm: ECHO the dry-run's run_key so the spent run is provably the previewed one (FR-11).
  const handleConfirm = useCallback(async () => {
    if (!dryRun) {
      return;
    }
    setPhase('running');
    try {
      const r = await proxyPost<RunResult>(options.datasourceUid, 'stakeholders/run', {
        question: question.trim(),
        cap: cap ?? null,
        run_key: dryRun.run_key, // <-- the fix: bind confirm to the exact previewed dry-run
      });
      setResult(r);
      setPhase('done');
    } catch (err) {
      setError(errText(err));
      setPhase('idle');
    } finally {
      setCancelling(false);
    }
  }, [dryRun, question, cap, options.datasourceUid]);

  // Cancel an in-flight run: signal the server (FR-12) — personas that already answered persist; the
  // awaiting confirm request then resolves with status "cancelled" + the partial answers.
  const handleCancel = useCallback(async () => {
    if (!dryRun || cancelling) {
      return;
    }
    setCancelling(true);
    try {
      await proxyPost(options.datasourceUid, `stakeholders/run/${encodeURIComponent(dryRun.run_key)}/cancel`, {});
    } catch (err) {
      // A failed cancel is non-fatal — the run may finish normally; surface it and let the run resolve.
      setError(errText(err));
      setCancelling(false);
    }
  }, [dryRun, cancelling, options.datasourceUid]);

  return (
    <div className={styles.container} style={{ width, height }}>
      {!configured && (
        <Alert severity="warning" title="Not configured">
          Set the panel option <b>Run datasource UID</b> to a datasource that proxies{' '}
          <code>/stakeholders/*</code> to the run endpoint (it adds the bearer token server-side).
        </Alert>
      )}

      <Field label="Question" description="Posed to every persona (bounded by the cap).">
        <TextArea
          value={question}
          onChange={(e) => setQuestion(e.currentTarget.value)}
          placeholder="e.g. What is the single biggest risk to this launch?"
          rows={2}
          disabled={phase === 'running' || phase === 'previewing'}
        />
      </Field>
      <Field label="Cap" description="Max personas to query (empty = all). Bounds spend.">
        <Input
          type="number"
          value={cap ?? ''}
          width={12}
          onChange={(e) => {
            const v = e.currentTarget.value;
            setCap(v === '' ? undefined : Number(v));
          }}
        />
      </Field>

      <div className={styles.actions}>
        <Button
          onClick={handlePreview}
          disabled={!configured || !question.trim() || phase === 'previewing' || phase === 'running'}
          variant="primary"
        >
          {phase === 'previewing' ? 'Estimating…' : phase === 'running' ? 'Running…' : 'Preview cost'}
        </Button>
        {phase === 'running' && (
          <Button variant="destructive" onClick={handleCancel} disabled={cancelling}>
            {cancelling ? 'Cancelling…' : 'Cancel run'}
          </Button>
        )}
        {phase !== 'running' && (dryRun || result || error) && (
          <Button variant="secondary" fill="text" onClick={() => { reset(); setPhase('idle'); }}>
            Clear
          </Button>
        )}
      </div>

      {error && <Alert severity="error" title="Run failed">{error}</Alert>}

      {/* Confirm modal — shows the honest estimate BEFORE any spend. */}
      {dryRun && (
        <ConfirmModal
          isOpen={phase === 'confirm'}
          title="Run the stakeholder panel? (paid)"
          body={
            <div className={styles.estimate}>
              <div>
                <b>{dryRun.n_personas}</b> personas · model <code>{dryRun.model}</code>
              </div>
              <div>
                Estimated cost <b>~${dryRun.estimated_cost.toFixed(4)}</b>{' '}
                (${dryRun.per_question_estimate.toFixed(4)}/persona)
              </div>
              <div className={styles.dim}>{dryRun.note}</div>
              <div className={styles.dim}>Answers will be synthetic and unratified.</div>
            </div>
          }
          confirmText={`Run (~$${dryRun.estimated_cost.toFixed(4)})`}
          onConfirm={handleConfirm}
          onDismiss={() => setPhase('idle')}
        />
      )}

      {result && <Results result={result} styles={styles} />}
    </div>
  );
};

const Results: React.FC<{ result: RunResult; styles: ReturnType<typeof getStyles> }> = ({ result, styles }) => (
  <div className={styles.results}>
    <div className={styles.resultHead}>
      session <code>{result.session_id}</code> · {result.status}
    </div>
    <Alert severity="warning" title="Synthetic &amp; unratified">
      Role-played stand-ins, not real stakeholders. Confirm with a human before relying on these.
    </Alert>
    {result.status === 'deduped' && (
      <div className={styles.dim}>This run_key already ran — showing the prior result (not re-charged).</div>
    )}
    {result.status === 'cancelled' && (
      <div className={styles.dim}>Run cancelled — showing only the personas that answered before cancellation.</div>
    )}
    {result.answers.map((a: PanelAnswerView, i: number) => (
      <div key={i} className={styles.answer}>
        <div className={styles.answerHead}>
          <b>{a.role_id}</b> <span className={styles.dim}>({a.grounding})</span>
        </div>
        <div>{a.text}</div>
      </div>
    ))}
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
  `,
});
