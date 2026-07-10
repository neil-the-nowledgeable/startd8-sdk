import React, { useCallback, useState } from 'react';
import { PanelProps } from '@grafana/data';
import { Alert, Button, Collapse, ConfirmModal, Field, Input, useStyles2 } from '@grafana/ui';
import { css } from '@emotion/css';
import {
  DispositionResult,
  ExtractDryRun,
  ExtractResult,
  SerializeResult,
  StagedRow,
  StakeholdersPanelOptions,
  TriageCandidate,
  TriageReportResult,
} from '../types';
import { errText, proxyPost } from '../api';

type Props = PanelProps<StakeholdersPanelOptions>;

// The stepped state machine (plan R3 / FR-12/13): idle → triaged → (staged) → (dispositioned) →
// serialized. `sessionId` established at triage is the anchor threaded to every write call; a lost
// anchor or a server drift/in-progress 409 surfaces as a recoverable "re-triage" notice.
type Phase = 'idle' | 'triaging' | 'triaged' | 'previewing' | 'confirm' | 'extracting' | 'staged' | 'serializing' | 'serialized';

const LANE_LABEL: Record<string, string> = {
  FIELD_LEVEL: 'Field-level (→ VIPP write path)',
  NON_DECIDABLE: 'Non-decidable (→ human / backlog)',
  UNSTRUCTURED: 'Preserved — received but not accounted for',
};
const dkey = (r: StagedRow) => `${r.domain}::${r.value_path}`;

/**
 * Triage mode — drives the middle of the pipeline from the dashboard and hands off to Apply mode for
 * the final write. Thin driver over the tested routes (`/stakeholders/{triage,extract,disposition,
 * serialize}`); the token stays server-side via the datasource proxy. Output is SYNTHETIC & UNRATIFIED.
 */
export const TriagePanel: React.FC<Props> = ({ options, width, height }) => {
  const styles = useStyles2(getStyles);
  const [sessionInput, setSessionInput] = useState('');
  const [phase, setPhase] = useState<Phase>('idle');
  const [report, setReport] = useState<TriageReportResult | null>(null);
  const [sessionId, setSessionId] = useState('');
  const [backlogOpen, setBacklogOpen] = useState(false);
  const [dryRun, setDryRun] = useState<ExtractDryRun | null>(null);
  const [extract, setExtract] = useState<ExtractResult | null>(null);
  const [dispositions, setDispositions] = useState<Record<string, 'accepted' | 'rejected'>>({});
  const [serialized, setSerialized] = useState<SerializeResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const configured = Boolean(options.datasourceUid);

  const resetDownstream = useCallback(() => {
    setDryRun(null);
    setExtract(null);
    setDispositions({});
    setSerialized(null);
    setError(null);
    setNotice(null);
  }, []);

  // Step 1 — triage (read-only, $0): route the synthesis into typed, lane-sorted candidates.
  const handleTriage = useCallback(async () => {
    if (!configured) {
      return;
    }
    resetDownstream();
    setReport(null);
    setPhase('triaging');
    try {
      const r = await proxyPost<TriageReportResult>(options.datasourceUid, 'stakeholders/triage', {
        session_id: sessionInput.trim() || null,
      });
      setReport(r);
      setSessionId(r.session_id); // the anchor for every subsequent write call (FR-13)
      setPhase('triaged');
    } catch (err) {
      setError(errText(err));
      setPhase('idle');
    }
  }, [configured, options.datasourceUid, sessionInput, resetDownstream]);

  // Step 2a — extract dry-run ($0): honest estimate + checksum, then open the paid-confirm modal.
  const handlePreview = useCallback(async () => {
    setError(null);
    setNotice(null);
    setPhase('previewing');
    try {
      const d = await proxyPost<ExtractDryRun>(options.datasourceUid, 'stakeholders/extract', {
        session_id: sessionId,
        dry_run: true,
      });
      // FR-12 staleness guard: if the synthesis changed since triage (a re-facilitation), the displayed
      // candidates are stale — refuse to extract against them and prompt a re-triage rather than staging
      // recs the operator didn't actually see.
      if (report && report.synthesis_checksum && d.synthesis_checksum !== report.synthesis_checksum) {
        setNotice('Synthesis changed since you triaged — re-triage to refresh the candidates before extracting.');
        setPhase('triaged');
        return;
      }
      setDryRun(d);
      setPhase('confirm');
    } catch (err) {
      setError(errText(err));
      setPhase('triaged');
    }
  }, [options.datasourceUid, sessionId, report]);

  // Step 2b — extract confirm (PAID). FR-8a: transition phase synchronously BEFORE the await so the
  // modal closes on the first click and a double-click can't issue a second (paid) request.
  const handleConfirm = useCallback(async () => {
    if (!dryRun) {
      return;
    }
    setPhase('extracting');
    try {
      const r = await proxyPost<ExtractResult>(options.datasourceUid, 'stakeholders/extract', {
        session_id: sessionId,
        confirm_checksum: dryRun.synthesis_checksum,
      });
      setExtract(r);
      setDispositions({});
      setPhase('staged');
      if (r.status === 'deduped') {
        setNotice('Already extracted for this synthesis — $0, no re-charge.');
      }
    } catch (err) {
      // 409 = checksum drift (synthesis changed) or a concurrent extract in progress → re-triage.
      setError(errText(err));
      setNotice('If the synthesis changed, re-triage to refresh; if extraction is in progress, retry shortly.');
      setPhase('triaged');
    }
  }, [dryRun, options.datasourceUid, sessionId]);

  // Step 3 — disposition ($0): accept/reject a staged rec, keyed on (domain, value_path) (needs M1b domain).
  const handleDisposition = useCallback(
    async (row: StagedRow, decision: 'accepted' | 'rejected') => {
      setError(null);
      try {
        const r = await proxyPost<DispositionResult>(options.datasourceUid, 'stakeholders/disposition', {
          session_id: sessionId,
          domain: row.domain,
          value_path: row.value_path,
          disposition: decision,
        });
        if (r.updated) {
          setDispositions((prev) => ({ ...prev, [dkey(row)]: decision }));
        }
      } catch (err) {
        setError(errText(err)); // 404 "stage it first" surfaces here, not a silent no-op
      }
    },
    [options.datasourceUid, sessionId]
  );

  // Step 4 — serialize ($0): push ACCEPTED staged recs to the VIPP inbox, then hand off to Apply mode.
  const handleSerialize = useCallback(async () => {
    setError(null);
    setNotice(null);
    setPhase('serializing');
    try {
      const r = await proxyPost<SerializeResult>(options.datasourceUid, 'stakeholders/serialize', {
        session_id: sessionId,
      });
      setSerialized(r);
      setPhase('serialized');
    } catch (err) {
      // 409 undrained-inbox (M1d) — Apply mode must drain it first; keep the accepted set intact.
      setError(errText(err));
      setNotice('If the inbox is occupied, switch to Apply mode and ratify it before re-serializing.');
      setPhase('staged');
    }
  }, [options.datasourceUid, sessionId]);

  const acceptedCount = Object.values(dispositions).filter((d) => d === 'accepted').length;
  const fieldLevel = (report?.candidates ?? []).filter((c) => c.lane === 'FIELD_LEVEL');

  return (
    <div className={styles.container} style={{ width, height }}>
      {!configured && (
        <Alert severity="warning" title="Not configured">
          Set the panel option <b>Run datasource UID</b> to a datasource that proxies{' '}
          <code>/stakeholders/*</code> to the run endpoint (it adds the bearer token server-side).
        </Alert>
      )}

      <Field label="Session" description="Facilitation session to triage (empty = latest).">
        <Input
          value={sessionInput}
          width={40}
          placeholder="kp-… (empty = latest)"
          disabled={phase === 'triaging'}
          onChange={(e) => setSessionInput(e.currentTarget.value)}
        />
      </Field>
      <div className={styles.actions}>
        <Button onClick={handleTriage} disabled={!configured || phase === 'triaging'} variant="primary">
          {phase === 'triaging' ? 'Triaging…' : 'Triage'}
        </Button>
        {report && (
          <Button variant="secondary" fill="text" onClick={() => { setReport(null); resetDownstream(); setPhase('idle'); }}>
            Clear
          </Button>
        )}
      </div>

      <Alert severity="warning" title="Synthetic &amp; unratified">
        Routes a role-played synthesis; it decides nothing. Field-level items become VIPP proposals only
        after you extract → accept → serialize → <b>ratify in Apply mode</b>.
      </Alert>

      {error && <Alert severity="error" title="Triage notice">{error}</Alert>}
      {notice && <Alert severity="info" title="Heads up">{notice}</Alert>}

      {report && <ReportView report={report} styles={styles} backlogOpen={backlogOpen} setBacklogOpen={setBacklogOpen} />}

      {/* Step 2 — the paid extract, only when there are field-level candidates to stage. */}
      {report && report.synthesis_present && fieldLevel.length > 0 && phase !== 'serialized' && (
        <div className={styles.step}>
          <div className={styles.stepHead}>Stage field-level recommendations ({fieldLevel.length}) — paid</div>
          <Button
            onClick={handlePreview}
            disabled={phase === 'previewing' || phase === 'extracting'}
            variant="primary"
            size="sm"
          >
            {phase === 'previewing' ? 'Estimating…' : phase === 'extracting' ? 'Extracting…' : 'Preview extract cost'}
          </Button>
        </div>
      )}

      {/* Step 3 — disposition the staged recs. */}
      {extract && extract.staged.length > 0 && (
        <div className={styles.step}>
          <div className={styles.stepHead}>
            Staged ({extract.staged.length}){extract.status === 'deduped' ? ' · $0 replay' : (
              typeof extract.actual_cost === 'number' ? ` · ~$${extract.actual_cost.toFixed(4)}` : ''
            )}
          </div>
          {extract.staged.map((row) => (
            <div key={dkey(row)} className={styles.stagedRow}>
              <div className={styles.stagedText}>
                <code>{row.value_path}</code> = <b>{row.value}</b>
                <span className={styles.dim}> ({row.domain || 'no-domain'})</span>
              </div>
              <div className={styles.rowActions}>
                <Button
                  size="sm"
                  variant={dispositions[dkey(row)] === 'accepted' ? 'primary' : 'secondary'}
                  onClick={() => handleDisposition(row, 'accepted')}
                >
                  Accept
                </Button>
                <Button
                  size="sm"
                  variant={dispositions[dkey(row)] === 'rejected' ? 'destructive' : 'secondary'}
                  fill="outline"
                  onClick={() => handleDisposition(row, 'rejected')}
                >
                  Reject
                </Button>
              </div>
            </div>
          ))}
          {/* Step 4 — serialize accepted → VIPP inbox. */}
          <div className={styles.actions}>
            <Button
              variant="primary"
              size="sm"
              disabled={acceptedCount === 0 || phase === 'serializing'}
              onClick={handleSerialize}
            >
              {phase === 'serializing' ? 'Serializing…' : `Serialize ${acceptedCount} accepted → inbox`}
            </Button>
          </div>
        </div>
      )}

      {serialized && <SerializedView result={serialized} sessionId={sessionId} styles={styles} />}

      {/* Paid-confirm modal — honest estimate BEFORE any spend. */}
      {dryRun && (
        <ConfirmModal
          isOpen={phase === 'confirm'}
          title="Extract field-level recommendations? (paid)"
          body={
            <div className={styles.estimate}>
              <div>model <code>{dryRun.model}</code> · {dryRun.n_allowed} allowed fields</div>
              <div>Estimated cost <b>~${dryRun.estimated_cost.toFixed(4)}</b></div>
              <div className={styles.dim}>{dryRun.note}</div>
              <div className={styles.dim}>Staged output is synthetic &amp; unratified.</div>
            </div>
          }
          confirmText={`Extract (~$${dryRun.estimated_cost.toFixed(4)})`}
          onConfirm={handleConfirm}
          onDismiss={() => setPhase('triaged')}
        />
      )}
    </div>
  );
};

const ReportView: React.FC<{
  report: TriageReportResult;
  styles: ReturnType<typeof getStyles>;
  backlogOpen: boolean;
  setBacklogOpen: (v: boolean) => void;
}> = ({ report, styles, backlogOpen, setBacklogOpen }) => {
  if (!report.synthesis_present) {
    return (
      <Alert severity="info" title="No synthesis for this session">
        This session has no facilitated synthesis to triage (e.g. an ask-all run). Run a Facilitate
        session first.
      </Alert>
    );
  }
  const c = report.counts;
  const lanes: Array<TriageCandidate['lane']> = ['FIELD_LEVEL', 'NON_DECIDABLE', 'UNSTRUCTURED'];
  return (
    <div className={styles.results}>
      <div className={styles.resultHead}>
        session <code>{report.session_id}</code> · {c.total ?? 0} items · FIELD {c.FIELD_LEVEL ?? 0} ·
        ND {c.NON_DECIDABLE ?? 0} · UNSTRUCTURED {c.UNSTRUCTURED ?? 0}
      </div>
      {report.health.length > 0 && (
        <Alert severity="info" title="Health">
          <ul className={styles.tight}>{report.health.map((h, i) => <li key={i}>{h}</li>)}</ul>
        </Alert>
      )}
      {lanes.map((lane) => {
        const group = report.candidates.filter((x) => x.lane === lane);
        if (group.length === 0) {
          return null;
        }
        return (
          <div key={lane} className={lane === 'UNSTRUCTURED' ? styles.preservedGroup : styles.laneGroup}>
            <div className={styles.laneHead}>{LANE_LABEL[lane]} ({group.length})</div>
            {group.map((cand, i) => (
              <div key={i} className={styles.candidate}>
                <div><b>{cand.title || cand.raw_text.slice(0, 80)}</b></div>
                <div className={styles.dim}>
                  {cand.input_kind}
                  {cand.value_path ? ` · ${cand.value_path}` : ''}
                  {cand.role ? ` · ${cand.role}` : ''}
                  {cand.reason ? ` · ${cand.reason}` : ''}
                </div>
              </div>
            ))}
          </div>
        );
      })}
      <Collapse label="Backlog preview (copy-out)" isOpen={backlogOpen} onToggle={() => setBacklogOpen(!backlogOpen)} collapsible>
        <pre className={styles.pre}>{report.backlog_markdown || '(no backlog items)'}</pre>
      </Collapse>
    </div>
  );
};

const SerializedView: React.FC<{ result: SerializeResult; sessionId: string; styles: ReturnType<typeof getStyles> }> = ({
  result,
  sessionId,
  styles,
}) => (
  <div className={styles.step}>
    <div className={styles.stepHead}>Serialized → VIPP inbox</div>
    <div>{result.staged.length} written to the inbox.</div>
    {result.rejected.length > 0 && (
      <Alert severity="warning" title="Not serialized — not allow-listed">
        <ul className={styles.tight}>
          {result.rejected.map(([vp, reason], i) => <li key={i}><code>{vp}</code> — {reason}</li>)}
        </ul>
      </Alert>
    )}
    {result.inbox && <div className={styles.dim}>inbox: <code>{result.inbox}</code></div>}
    <Alert severity="info" title="Next: ratify in Apply mode">
      Switch this panel to <b>Apply</b> mode (session <code>{sessionId}</code>) to preview → paste the
      challenge → ratify the inbox into the project source of record.
    </Alert>
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
  step: css`
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 8px;
    border: 1px solid var(--border-weak, rgba(255, 255, 255, 0.1));
    border-radius: 4px;
  `,
  stepHead: css`
    font-weight: 600;
    font-size: 13px;
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
  `,
  resultHead: css`
    font-size: 12px;
    color: var(--text-secondary, #8e8e8e);
  `,
  laneGroup: css`
    display: flex;
    flex-direction: column;
    gap: 4px;
  `,
  preservedGroup: css`
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 6px;
    border-left: 3px solid var(--warning, #f2cc0c);
    background: var(--background-secondary, rgba(255, 255, 255, 0.03));
  `,
  laneHead: css`
    font-weight: 600;
    font-size: 12px;
    margin-top: 4px;
  `,
  candidate: css`
    padding: 4px 8px;
    background: var(--background-secondary, rgba(255, 255, 255, 0.03));
    border-radius: 4px;
  `,
  stagedRow: css`
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    padding: 4px 0;
  `,
  stagedText: css`
    flex: 1;
    font-size: 13px;
  `,
  rowActions: css`
    display: flex;
    gap: 4px;
  `,
  tight: css`
    margin: 0;
    padding-left: 16px;
  `,
  pre: css`
    white-space: pre-wrap;
    font-family: inherit;
    margin: 0;
    font-size: 12px;
  `,
});
