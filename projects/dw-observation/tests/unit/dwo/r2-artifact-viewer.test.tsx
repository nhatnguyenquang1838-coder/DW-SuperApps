import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ArtifactViewer from '@/components/dwo/ArtifactViewer';

beforeEach(() => { vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ json: async () => ({ ok: true, runId: 'DEV-RUN-024', path: 'execution/DEV-RUN-024-execution.json', bytes: 82, text: '{\n  "record_id": "DEV-RUN-024-ExecutionReceipt"\n}' }) })); });
describe('R2 artifact viewer', () => {
  it('renders the real evidence response in an accessible read-only dialog and closes accessibly', async () => {
    const onClose = vi.fn();
    render(<ArtifactViewer runId="DEV-RUN-024" path="execution/DEV-RUN-024-execution.json" onClose={onClose} />);
    expect(screen.getByRole('dialog', { name: /Artifact evidence/i })).toBeInTheDocument();
    expect(await screen.findByText(/DEV-RUN-024-ExecutionReceipt/)).toBeInTheDocument();
    expect(screen.getByText(/read-only observation/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Close artifact viewer' }));
    expect(onClose).toHaveBeenCalledOnce();
  });
  it('does not replace current evidence with stale data after request is aborted', async () => {
    const finishers: Array<(v: { json: () => Promise<object> }) => void> = [];
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => new Promise((resolve) => { finishers.push(resolve); })));
    const { rerender } = render(<ArtifactViewer runId="DEV-RUN-024" path="execution/DEV-RUN-024-execution.json" onClose={() => {}} />);
    rerender(<ArtifactViewer runId="DEV-RUN-025" path="execution/DEV-RUN-025-execution.json" onClose={() => {}} />);
    finishers[0]!({ json: async () => ({ ok: true, runId: 'DEV-RUN-024', path: 'old', text: 'STALE', bytes: 5 }) });
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Loading evidence'));
    expect(screen.queryByText('STALE')).not.toBeInTheDocument();
  });
});
