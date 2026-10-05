/**
 * CR-827-A/B/C/D verification — evidence inspector, recovery lineage,
 * deterministic replay (fixture + durable), FNR-02 comparison evidence.
 *
 * AC-827-01 replay reconstructs expected frames for official fixtures (deterministic)
 * AC-827-02 replay reconstructs expected frames from durable history under the accepted ordering/rebuild contract
 * AC-827-03 recovery generations remain immutable and navigable
 * AC-827-04 evidence provenance visible without inventing missing facts
 * AC-827-05 fixture replay and durable replay produce deterministic comparison evidence under FNR-02
 */
import { describe, expect, it } from 'vitest';
import {
  EVIDENCE_CAPABILITIES,
  type EvidenceRecord,
  inspectEvidence,
} from '@/lib/dwo/evidenceInspector';
import {
  RECOVERY_CAPABILITIES,
  type RecoveryGeneration,
  appendGeneration,
  navigateLineage,
  type RecoveryKind,
} from '@/lib/dwo/recoveryLineage';
import {
  REPLAY_CAPABILITIES,
  compareReplayEvidence,
  replayFromDurable,
  replayFromFixture,
  type ReplayView,
} from '@/lib/dwo/replay';
import {
  deriveV2EvidenceReplayReady,
  type EvidenceReplayInput,
} from '@/lib/dwo/evidenceCertification';
import { DurableLog } from '@/lib/dwo/durableOrder';
import { FNR02_CONTRACT_ID } from '@/lib/dwo/comparisonContract';

function certInput(overrides: Partial<EvidenceReplayInput> = {}): EvidenceReplayInput {
  return {
    fixtureReplayDeterministic: true,
    durableReplayDeterministic: true,
    recoveryImmutable: true,
    provenanceVisible: true,
    fnr02ComparisonEvidence: true,
    ...overrides,
  };
}

function fixtureEvent(runId: string, ordinal: number, runState: string): {
  eventId: string;
  runId: string;
  ordinal: number;
  runState: string;
} {
  return { eventId: `EVT-${runId}-${ordinal}`, runId, ordinal, runState };
}

describe('AC-827-01 · replay reconstructs expected frames for official fixtures (deterministic)', () => {
  it('replays a fixture event prefix into a deterministic frame', () => {
    const events = [fixtureEvent('DEV-RUN-001', 1, 'OPEN'), fixtureEvent('DEV-RUN-001', 2, 'ACCEPTED')];
    const a = replayFromFixture('DEV-RUN-001', events);
    const b = replayFromFixture('DEV-RUN-001', events);
    expect(a.runId).toBe('DEV-RUN-001');
    expect(a.runState).toBe('ACCEPTED');
    expect(a.digest).toBe(b.digest); // deterministic
    expect(a.source).toBe('FIXTURE');
  });

  it('replay is deterministic regardless of event input order', () => {
    const e1 = fixtureEvent('DEV-RUN-001', 1, 'OPEN');
    const e2 = fixtureEvent('DEV-RUN-001', 2, 'ACCEPTED');
    const a = replayFromFixture('DEV-RUN-001', [e1, e2]);
    const b = replayFromFixture('DEV-RUN-001', [e2, e1]);
    expect(a.digest).toBe(b.digest);
    expect(a.runState).toBe('ACCEPTED');
  });
});

describe('AC-827-02 · replay reconstructs expected frames from durable history under the accepted ordering/rebuild contract', () => {
  it('replays a durable log into a frame using the durable watermark', () => {
    const log = new DurableLog();
    log.append({ eventId: 'E1', runId: 'DEV-RUN-001', ordinal: 1, payload: { runState: 'OPEN' } });
    log.append({ eventId: 'E2', runId: 'DEV-RUN-001', ordinal: 2, payload: { runState: 'ACCEPTED' } });
    const frame = replayFromDurable(log, 'DEV-RUN-001');
    expect(frame.runId).toBe('DEV-RUN-001');
    expect(frame.runState).toBe('ACCEPTED');
    expect(frame.source).toBe('DURABLE');
    expect(frame.watermark).toBe(2);
  });

  it('replay from durable history is deterministic (rebuild parity)', () => {
    const log = new DurableLog();
    log.append({ eventId: 'E1', runId: 'DEV-RUN-001', ordinal: 1, payload: { runState: 'OPEN' } });
    log.append({ eventId: 'E2', runId: 'DEV-RUN-001', ordinal: 2, payload: { runState: 'ACCEPTED' } });
    const a = replayFromDurable(log, 'DEV-RUN-001');
    const b = replayFromDurable(log, 'DEV-RUN-001');
    expect(a.digest).toBe(b.digest);
  });
});

describe('AC-827-03 · recovery generations remain immutable and navigable', () => {
  it('appends a recovery generation and keeps it immutable', () => {
    const lineage: RecoveryGeneration[] = [];
    const g1 = appendGeneration(lineage, { runId: 'DEV-RUN-001', kind: 'RETRY', parentGeneration: null });
    const g2 = appendGeneration(lineage, { runId: 'DEV-RUN-001', kind: 'RERUN', parentGeneration: g1.id });
    expect(lineage.length).toBe(2);
    expect(g1.id).not.toBe(g2.id);
    // Immutability: the appended generation object is frozen.
    expect(Object.isFrozen(g1)).toBe(true);
    expect(Object.isFrozen(g2)).toBe(true);
  });

  it('navigates the lineage from a generation back to its root', () => {
    const lineage: RecoveryGeneration[] = [];
    const g1 = appendGeneration(lineage, { runId: 'DEV-RUN-001', kind: 'RETRY', parentGeneration: null });
    const g2 = appendGeneration(lineage, { runId: 'DEV-RUN-001', kind: 'RERUN', parentGeneration: g1.id });
    const g3 = appendGeneration(lineage, { runId: 'DEV-RUN-001', kind: 'SUPERSESSION', parentGeneration: g2.id });
    const path = navigateLineage(lineage, g3.id);
    expect(path.map((g) => g.kind)).toEqual(['RETRY', 'RERUN', 'SUPERSESSION']);
  });

  it('supports all recovery kinds', () => {
    const kinds: RecoveryKind[] = ['RETRY', 'RERUN', 'REPLAN', 'RESTART', 'SUPERSESSION', 'RESET_DERIVED_STATE'];
    const lineage: RecoveryGeneration[] = [];
    let parent: string | null = null;
    for (const kind of kinds) {
      const g = appendGeneration(lineage, { runId: 'DEV-RUN-001', kind, parentGeneration: parent });
      parent = g.id;
    }
    expect(lineage.length).toBe(6);
    expect(new Set(lineage.map((g) => g.kind)).size).toBe(6);
  });
});

describe('AC-827-04 · evidence provenance visible without inventing missing facts', () => {
  it('shows provenance for a recorded evidence record', () => {
    const record: EvidenceRecord = {
      runId: 'DEV-RUN-001',
      source: 'fixture',
      profile: 'DEV_NATIVE',
      ref: 'DWO-UR-30-V1',
      digest: 'sha256:abc123',
      provenance: 'materialized fixture pack',
    };
    const inspection = inspectEvidence('DEV-RUN-001', [record]);
    expect(inspection.records.length).toBe(1);
    expect(inspection.records[0].provenance).toBe('materialized fixture pack');
    expect(inspection.records[0].digest).toBe('sha256:abc123');
  });

  it('does not invent provenance for a missing fact (stays UNKNOWN)', () => {
    const inspection = inspectEvidence('DEV-RUN-999', []);
    expect(inspection.records.length).toBe(0);
    expect(inspection.missingFacts).toContain('DEV-RUN-999');
    expect(inspection.invented).toBe(false);
  });
});

describe('AC-827-05 · fixture and durable replay produce deterministic comparison evidence under FNR-02', () => {
  it('compares fixture vs durable replay frames under FNR-02', () => {
    const fixtureEvents = [fixtureEvent('DEV-RUN-001', 1, 'OPEN'), fixtureEvent('DEV-RUN-001', 2, 'ACCEPTED')];
    const log = new DurableLog();
    log.append({ eventId: 'E1', runId: 'DEV-RUN-001', ordinal: 1, payload: { runState: 'OPEN' } });
    log.append({ eventId: 'E2', runId: 'DEV-RUN-001', ordinal: 2, payload: { runState: 'ACCEPTED' } });
    const fixture = replayFromFixture('DEV-RUN-001', fixtureEvents);
    const durable = replayFromDurable(log, 'DEV-RUN-001');
    const comparison = compareReplayEvidence(fixture, durable);
    expect(comparison.contractId).toBe(FNR02_CONTRACT_ID);
    expect(comparison.result).toBe('EQUIVALENT');
  });

  it('reports NON_EQUIVALENT when fixture and durable frames diverge', () => {
    const fixtureEvents = [fixtureEvent('DEV-RUN-001', 1, 'OPEN'), fixtureEvent('DEV-RUN-001', 2, 'ACCEPTED')];
    const log = new DurableLog();
    log.append({ eventId: 'E1', runId: 'DEV-RUN-001', ordinal: 1, payload: { runState: 'OPEN' } });
    log.append({ eventId: 'E2', runId: 'DEV-RUN-001', ordinal: 2, payload: { runState: 'FAILED' } });
    const fixture = replayFromFixture('DEV-RUN-001', fixtureEvents);
    const durable = replayFromDurable(log, 'DEV-RUN-001');
    const comparison = compareReplayEvidence(fixture, durable);
    expect(comparison.result).toBe('NON_EQUIVALENT');
  });
});

describe('CURRENT vs REPLAY view mode', () => {
  it('builds a replay view with an explicit mode', () => {
    const view: ReplayView = {
      runId: 'DEV-RUN-001',
      mode: 'REPLAY',
      current: { runId: 'DEV-RUN-001', runState: 'OPEN', source: 'CURRENT', watermark: 1, digest: 'cur' },
      replay: { runId: 'DEV-RUN-001', runState: 'ACCEPTED', source: 'FIXTURE', watermark: 0, digest: 'rep' },
    };
    expect(view.mode).toBe('REPLAY');
    expect(view.replay.runState).toBe('ACCEPTED');
  });
});

describe('AC-827-01..05 · V2_EVIDENCE_REPLAY_READY derivation', () => {
  it('derives the token from a coherent evidence/replay foundation', () => {
    const decision = deriveV2EvidenceReplayReady(certInput());
    expect(decision.derivable).toBe(true);
    expect(decision.token).toBe('V2_EVIDENCE_REPLAY_READY');
    expect(decision.reasons).toEqual([]);
  });

  it('fails closed on non-deterministic fixture replay', () => {
    expect(deriveV2EvidenceReplayReady(certInput({ fixtureReplayDeterministic: false })).derivable).toBe(false);
  });

  it('fails closed on non-deterministic durable replay', () => {
    expect(deriveV2EvidenceReplayReady(certInput({ durableReplayDeterministic: false })).derivable).toBe(false);
  });

  it('fails closed when recovery generations are mutable', () => {
    expect(deriveV2EvidenceReplayReady(certInput({ recoveryImmutable: false })).derivable).toBe(false);
  });

  it('fails closed when provenance invents facts', () => {
    expect(deriveV2EvidenceReplayReady(certInput({ provenanceVisible: false })).derivable).toBe(false);
  });

  it('fails closed when FNR-02 comparison evidence is absent', () => {
    expect(deriveV2EvidenceReplayReady(certInput({ fnr02ComparisonEvidence: false })).derivable).toBe(false);
  });
});

describe('capabilities — evidence/replay/recovery are read-only', () => {
  it('exposes no effect capability anywhere', () => {
    for (const caps of [EVIDENCE_CAPABILITIES, RECOVERY_CAPABILITIES, REPLAY_CAPABILITIES]) {
      expect(caps).toEqual({
        read: true,
        write: false,
        approve: false,
        deny: false,
        merge: false,
        deploy: false,
      });
      expect(Object.isFrozen(caps)).toBe(true);
    }
  });
});
