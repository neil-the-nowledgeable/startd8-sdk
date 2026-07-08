import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// getBackendSrv().post is the single network seam — mock it so we can control the run's timing.
const post = vi.fn();
vi.mock('@grafana/runtime', () => ({
  getBackendSrv: () => ({ post }),
}));

// Lightweight stand-ins for @grafana/ui — importing it for real pulls in @grafana/data, whose ESM
// build has a react-use resolution bug in this vitest env. These render the props the test asserts on.
vi.mock('@grafana/ui', () => ({
  Button: ({ children, onClick, disabled }: any) => (
    <button onClick={onClick} disabled={disabled}>
      {children}
    </button>
  ),
  Alert: ({ title, children }: any) => (
    <div>
      {title}
      {children}
    </div>
  ),
  Field: ({ children }: any) => <div>{children}</div>,
  Input: (props: any) => <input {...props} />,
  TextArea: (props: any) => <textarea {...props} />,
  ConfirmModal: ({ isOpen, title, body, confirmText, onConfirm }: any) =>
    isOpen ? (
      <div>
        <div>{title}</div>
        {body}
        <button onClick={onConfirm}>{confirmText}</button>
      </div>
    ) : null,
  useStyles2: () => new Proxy({}, { get: () => '' }),
}));

vi.mock('@emotion/css', () => ({ css: () => '' }));

import { StakeholdersPanel } from './StakeholdersPanel';

const DS = 'ds-uid-1';

function renderPanel() {
  const props: any = {
    options: { datasourceUid: DS },
    width: 400,
    height: 400,
  };
  return render(<StakeholdersPanel {...props} />);
}

/** Drive preview → confirm so the panel enters the in-flight `running` phase (run promise pending). */
async function enterRunningPhase(runPromise: Promise<any>) {
  post.mockResolvedValueOnce({
    run_key: 'rk-abc',
    roster_version: 'rv1',
    n_personas: 2,
    per_question_estimate: 0.01,
    estimated_cost: 0.02,
    model: 'mock',
    note: 'estimate',
  }); // dry-run
  post.mockReturnValueOnce(runPromise); // the confirmed run — stays pending until we resolve it

  fireEvent.change(screen.getByPlaceholderText(/biggest risk/i), { target: { value: 'what breaks?' } });
  fireEvent.click(screen.getByText('Preview cost'));
  await screen.findByText(/Run the stakeholder panel/i); // confirm modal
  fireEvent.click(screen.getByText(/^Run \(~\$/));
  await screen.findByText('Cancel run'); // now in the running phase
}

describe('StakeholdersPanel cancel button', () => {
  beforeEach(() => {
    post.mockReset();
  });

  it('shows Cancel only while a run is in flight and POSTs the cancel route for the previewed run_key', async () => {
    let resolveRun: (v: any) => void = () => {};
    const runPromise = new Promise((res) => {
      resolveRun = res;
    });
    renderPanel();
    await enterRunningPhase(runPromise);

    // Click Cancel → it must hit the run_key-scoped cancel route (not re-run).
    post.mockResolvedValueOnce({ run_key: 'rk-abc', cancelled: true }); // cancel response
    fireEvent.click(screen.getByText('Cancel run'));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        `/api/datasources/proxy/uid/${DS}/stakeholders/run/rk-abc/cancel`,
        {}
      )
    );

    // The server then resolves the in-flight run as cancelled with partial answers.
    resolveRun({ session_id: 's1', status: 'cancelled', run_key: 'rk-abc', answers: [] });
    await screen.findByText(/Run cancelled/i);
    expect(screen.queryByText('Cancel run')).toBeNull(); // gone once the run resolves
  });

  it('does not render Cancel before a run starts', () => {
    renderPanel();
    expect(screen.queryByText('Cancel run')).toBeNull();
  });
});
