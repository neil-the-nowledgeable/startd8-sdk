import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

const post = vi.fn();
vi.mock('@grafana/runtime', () => ({ getBackendSrv: () => ({ post }) }));

// Lightweight @grafana/ui stand-ins (importing it for real pulls in @grafana/data's ESM react-use bug).
vi.mock('@grafana/ui', () => ({
  Alert: ({ title, children }: any) => (
    <div>
      {title}
      {children}
    </div>
  ),
  Button: ({ children, onClick, disabled }: any) => (
    <button onClick={onClick} disabled={disabled}>
      {children}
    </button>
  ),
  Checkbox: ({ label, value, onChange }: any) => (
    <label>
      <input type="checkbox" checked={!!value} onChange={onChange} aria-label={label} />
      {label}
    </label>
  ),
  Field: ({ label, description, children }: any) => (
    <div>
      {label}
      {description}
      {children}
    </div>
  ),
  TextArea: (props: any) => <textarea {...props} />,
  useStyles2: () => new Proxy({}, { get: () => '' }),
}));
vi.mock('@emotion/css', () => ({ css: () => '' }));

import { ApplyPanel } from './ApplyPanel';

const DS = 'ds-uid-1';

function renderPanel() {
  const props: any = { options: { datasourceUid: DS, mode: 'apply' }, width: 400, height: 400 };
  return render(<ApplyPanel {...props} />);
}

const PREVIEW = {
  would_apply: [{ proposal_id: 'f1', kind: 'friction', value_path: null }],
  envelope_seq: 1,
  content_hash: 'ch',
  challenge: 'BODY.SIGNATURE',
  expires_in_seconds: 300,
  posture: 'token-gated, not human-proof — any holder of the endpoint token can ratify',
};

describe('ApplyPanel', () => {
  beforeEach(() => post.mockReset());

  it('always shows the honest token-gated banner', () => {
    renderPanel();
    expect(screen.getByText(/Token-gated — not human-proof/i)).toBeTruthy();
  });

  it('previews, shows the would-apply set + challenge, then ratifies only the selected ids', async () => {
    renderPanel();
    post.mockResolvedValueOnce(PREVIEW); // preview
    fireEvent.click(screen.getByText('Preview apply'));

    await screen.findByText(/Would apply 1 proposal/i);
    expect(screen.getByText(/f1 · friction/)).toBeTruthy();
    expect(screen.getByDisplayValue('BODY.SIGNATURE')).toBeTruthy(); // challenge shown to copy

    // Paste the challenge into screen 2, then ratify.
    fireEvent.change(screen.getByPlaceholderText(/Paste the challenge/i), {
      target: { value: 'BODY.SIGNATURE' },
    });
    post.mockResolvedValueOnce({
      wrote: 1,
      actionable: 1,
      outcomes: [{ proposal_id: 'f1', decision: 'ACCEPT', code: 'ok' }],
      inbox_shredded: true,
      stale: false,
      refused_reason: '',
    });
    fireEvent.click(screen.getByText(/Ratify & apply/));

    await waitFor(() =>
      expect(post).toHaveBeenLastCalledWith(
        `/api/datasources/proxy/uid/${DS}/stakeholders/apply/ratify`,
        { proposal_ids: ['f1'], challenge: 'BODY.SIGNATURE' }
      )
    );
    await screen.findByText(/Applied 1\/1/);
  });

  it('surfaces a stale/expired ratify error and stays on the review screen', async () => {
    renderPanel();
    post.mockResolvedValueOnce(PREVIEW);
    fireEvent.click(screen.getByText('Preview apply'));
    await screen.findByText(/Would apply 1 proposal/i);

    fireEvent.change(screen.getByPlaceholderText(/Paste the challenge/i), {
      target: { value: 'BODY.SIGNATURE' },
    });
    post.mockRejectedValueOnce({ data: { error: 'challenge expired — re-preview' } });
    fireEvent.click(screen.getByText(/Ratify & apply/));

    await screen.findByText(/challenge expired/i);
    expect(screen.getByText(/Ratify & apply/)).toBeTruthy(); // still on the review screen to re-preview
  });
});
