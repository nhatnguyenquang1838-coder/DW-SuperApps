/**
 * CR-827-C — Deterministic replay (fixture + durable) + FNR-02 comparison.
 *
 * SCRUM-827 / DWO-V2-06, G2 EXECUTE, PLAN-827-R1, child run CR-827-C.
 *
 * Deterministic replay reconstructs expected frames from official fixtures
 * (AC-827-01) and from durable history under the accepted ordering/rebuild
 * contract (AC-827-02). Fixture and durable replay produce deterministic
 * comparison evidence under the FNR-02 contract (AC-827-05). A CURRENT vs REPLAY
 * view mode lets the UX show the live state alongside the reconstructed frame.
 *
 * Design decisions:
 *  1. Replay is a pure function of an ordered event prefix; the same prefix
 *     always yields the same frame and digest.
 *  2. Durable replay uses the DurableLog watermark (highest contiguous position)
 *     as the reconstruction source, honoring the SCRUM-825 ordering/rebuild
 *     contract.
 *  3. Comparison uses the frozen FNR-02 contract (compareStates) so fixture and
 *     durable frames are compared under the canonical structured-state equality.
 */

import { DurableLog } from './durableOrder';
import { compareStates, FNR02_CONTRACT_ID } from './comparisonContract';

/** A replay event consumed by the replay reducer. */
export interface ReplayEvent {
  readonly eventId: string;
  readonly runId: string;
  readonly ordinal: number;
  readonly runState?: string | null;
}

/** A reconstructed replay frame. */
export interface ReplayCheckpoint {
  readonly runId: string;
  readonly runState: string | 'UNKNOWN';
  readonly source: 'FIXTURE' | 'DURABLE' | 'CURRENT';
  readonly watermark: number;
  readonly digest: string;
}

/** The CURRENT vs REPLAY view mode. */
export type ReplayViewMode = 'CURRENT' | 'REPLAY';

/** A replay view pairing the current state with the reconstructed frame. */
export interface ReplayView {
  readonly runId: string;
  readonly mode: ReplayViewMode;
  readonly current: ReplayCheckpoint;
  readonly replay: ReplayCheckpoint;
}

/** The result of comparing fixture vs durable replay under FNR-02. */
export interface ReplayComparison {
  readonly contractId: string;
  readonly result: 'EQUIVALENT' | 'NON_EQUIVALENT';
  readonly fixtureDigest: string;
  readonly durableDigest: string;
}

/** Deterministic canonical digest of a frame. */
function frameDigest(runId: string, runState: string, watermark: number): string {
  return `sha256:${JSON.stringify({ runId, runState, watermark })}`;
}

/**
 * Replay a fixture event prefix into a deterministic frame.
 *
 * Events are applied in ordinal order; the last runState wins. The same prefix
 * always produces the same frame and digest (AC-827-01).
 */
export function replayFromFixture(
  runId: string,
  events: readonly ReplayEvent[],
): ReplayCheckpoint {
  const ordered = [...events]
    .filter((e) => e.runId === runId)
    .sort((a, b) => a.ordinal - b.ordinal);
  let runState: string | 'UNKNOWN' = 'UNKNOWN';
  for (const e of ordered) {
    if (e.runState != null) runState = e.runState;
  }
  const watermark = ordered.length;
  return {
    runId,
    runState,
    source: 'FIXTURE',
    watermark,
    digest: frameDigest(runId, runState, watermark),
  };
}

/**
 * Replay a durable log into a deterministic frame.
 *
 * Uses the DurableLog watermark (highest contiguous position) as the
 * reconstruction source, honoring the SCRUM-825 ordering/rebuild contract
 * (AC-827-02). Payloads carry the runState.
 */
export function replayFromDurable(
  log: DurableLog,
  runId: string,
): ReplayCheckpoint {
  const events = log.read();
  const ordered = [...events]
    .filter((e) => e.runId === runId)
    .sort((a, b) => a.ordinal - b.ordinal);
  let runState: string | 'UNKNOWN' = 'UNKNOWN';
  for (const e of ordered) {
    const payload = e.payload as { runState?: string } | undefined;
    if (payload?.runState != null) runState = payload.runState;
  }
  const watermark = log.watermark().position;
  return {
    runId,
    runState,
    source: 'DURABLE',
    watermark,
    digest: frameDigest(runId, runState, watermark),
  };
}

/**
 * Compare fixture vs durable replay frames under the FNR-02 contract.
 *
 * The comparison uses the frozen FNR-02 structured-state equality so the result
 * is deterministic and canonical (AC-827-05).
 */
export function compareReplayEvidence(
  fixture: ReplayCheckpoint,
  durable: ReplayCheckpoint,
): ReplayComparison {
  const result = compareStates(
    { runId: fixture.runId, runState: fixture.runState },
    { runId: durable.runId, runState: durable.runState },
  );
  return {
    contractId: FNR02_CONTRACT_ID,
    result,
    fixtureDigest: fixture.digest,
    durableDigest: durable.digest,
  };
}

/** The replay surface is read-only; it grants no effect capability. */
export interface ReplayCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const REPLAY_CAPABILITIES: ReplayCapabilities = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);
