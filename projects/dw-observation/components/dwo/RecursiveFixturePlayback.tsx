'use client';

import { useEffect, useMemo, useState } from 'react';
import type { ProjectionEvent } from '@/lib/live';
import { ReplayTimeline } from '@/lib/replay';
import { projectFixtureReplayView } from '@/lib/dwo/fixtureReplayView';
import type { UnifiedRunWorkspaceModel } from '@/lib/runtime/unifiedRuntime';
import UnifiedRunWorkspace from './UnifiedRunWorkspace';

const GATES = ['G0', 'G1', 'G2', 'G3', 'G4', 'G5', 'G6'];

/** One cursor drives the existing workspace, gate matrix and source history. */
export default function RecursiveFixturePlayback({ model, events, milestones, initialCursor = 1 }: {
  model: UnifiedRunWorkspaceModel;
  events: ProjectionEvent[];
  milestones: { atomicDone: number; childDone: number; accepted: number };
  initialCursor?: number;
}) {
  const timeline = useMemo(() => new ReplayTimeline(events), [events]);
  const [cursor, setCursor] = useState(() => timeline.clamp(Number.isSafeInteger(initialCursor) ? initialCursor : 1));
  const [mode, setMode] = useState<'LIVE' | 'REPLAY'>('REPLAY');
  const [interactive, setInteractive] = useState(false);
  useEffect(() => setInteractive(true), []);
  const frame = timeline.frameAt(cursor);
  const prefix = frame.projection.events;
  // Full-tip evidence is available only after consuming the entire stream.
  // Any rewind returns to a prefix projection with evidence stripped.
  const viewModel = cursor === events.length
    ? { ...model, currentSequence: cursor - 1 }
    : projectFixtureReplayView(model, prefix);
  const goTo = (value: number) => { setMode('REPLAY'); setCursor(timeline.clamp(value)); };
  const gateStates = new Map<string, string>();
  const runStates = new Map<string, string>();
  for (const event of prefix) {
    if (typeof event.gate === 'string' && typeof event.gate_state === 'string') gateStates.set(`${event.run_id}:${event.gate}`, event.gate_state);
    if (typeof event.run_state === 'string') runStates.set(event.run_id, event.run_state);
  }
  return <section className="space-y-5" data-testid="recursive-fixture-playback">
    <header className="space-y-2">
      <h2 className="text-xl font-semibold">Recursive G0–G6 · ROOT → CHILD → ATOMIC</h2>
      <p className="text-sm" style={{ color: 'var(--dwo-color-text-muted)' }}>Synthetic read-only workflow. Declared topology stays visible; gate and run states follow only the selected event prefix. Child success never auto-completes its parent.</p>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Recursive scenario milestones">
        {([['Start at G0', 1], ['Atomics complete', milestones.atomicDone], ['Child complete', milestones.childDone], ['Root G6 accepted', milestones.accepted]] as const).map(([label, value]) =>
          <button key={label} disabled={!interactive} type="button" className="rounded border px-3 py-2 text-sm" onClick={() => goTo(value)}>{label}</button>)}
      </div>
      <p className="text-sm" aria-live="polite" data-testid="recursive-position">{cursor}/{events.length} · {viewModel.gate ?? 'NOT OBSERVED'} / {viewModel.gateState ?? 'NOT OBSERVED'} · {viewModel.status}</p>
      <p className="break-all text-xs" style={{ color: 'var(--dwo-color-text-muted)' }}>Prefix state digest: <code data-testid="recursive-state-digest">{frame.stateDigest}</code></p>
    </header>
    <div className="overflow-x-auto rounded border">
      <table className="w-full text-left text-xs" data-testid="recursive-gate-matrix">
        <caption className="p-3 text-left font-semibold">Gate history at selected cursor · NOT OBSERVED means no event at this cut</caption>
        <thead><tr><th className="p-2">Run / kind</th>{GATES.map(gate => <th key={gate} className="p-2">{gate}</th>)}<th className="p-2">Run state</th></tr></thead>
        <tbody>{model.nodes.map(node => <tr key={node.id} data-testid={`recursive-row-${node.id}`}>
          <th scope="row" className="p-2"><span className="block">{node.id}</span><span>{node.family}</span></th>
          {GATES.map(gate => <td className="p-2" key={gate} data-testid={`gate-${node.id}-${gate}`}>{gateStates.get(`${node.id}:${gate}`) ?? 'NOT OBSERVED'}</td>)}
          <td className="p-2" data-testid={`state-${node.id}`}>{runStates.get(node.id) ?? 'NOT OBSERVED'}</td>
        </tr>)}</tbody>
      </table>
    </div>
    <UnifiedRunWorkspace model={viewModel} replayCursor={cursor} replayTotal={events.length} replayMode={mode}
      onReplayCursorChange={goTo}
      onReplayModeChange={next => { setMode(next); if (next === 'LIVE') setCursor(events.length); }} />
    <details className="rounded border p-3" open>
      <summary>Source event history at this cursor ({prefix.length} events)</summary>
      <ol className="mt-3 space-y-2 text-xs" data-testid="recursive-event-history">
        {prefix.map(event => <li key={String(event.event_id)} className="break-words">
          <strong>{String(event.run_id)} · {String(event.gate)} / {String(event.gate_state)}</strong>
          <span> — {String(event.summary ?? event.event_type)}</span>
        </li>)}
      </ol>
    </details>
  </section>;
}
