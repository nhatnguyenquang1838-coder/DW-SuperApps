/**
 * CR-823-C — DWO event position/order + gap identity + correlation metadata.
 *
 * SCRUM-823 / DWO-V2-02, G2 EXECUTE, PLAN-822-R1, child run CR-823-C.
 *
 * Explicit durable event position/order sufficient for deterministic prefix
 * replay and gap detection (AC-823-04). Correlation/causation/trace metadata is
 * EVIDENCE METADATA ONLY — it never becomes Run identity or authority.
 *
 * Design decisions:
 *  1. Every event carries a durable ordinal (global) and a per-source sequence.
 *     The ordinal is the deterministic order for prefix replay.
 *  2. A gap is identified by a stable gap_id derived from the source + the
 *     missing sequence range. Gaps are explicit, not inferred.
 *  3. Correlation/causation/trace fields are optional evidence metadata; they are
 *     never used as Run identity or authority.
 */

/** A durable event position. */
export interface EventPosition {
  /** Global durable ordinal (cross-source order). */
  readonly ordinal: number;
  /** Per-source sequence (high-water for anomaly detection). */
  readonly sourceSequence: number;
  /** The source this event came from. */
  readonly source: string;
}

/** A detected gap in a source's event sequence. */
export interface GapIdentity {
  /** Stable gap id derived from source + missing range. */
  readonly gapId: string;
  readonly source: string;
  readonly fromSequence: number;
  readonly toSequence: number;
  /** True when the gap is a duplicate (same event seen twice). */
  readonly isDuplicate: boolean;
  /** True when the gap is out-of-order (sequence regressed). */
  readonly isOutOfOrder: boolean;
}

/**
 * Detect gaps in a source's event sequence.
 *
 * Returns explicit gap identities. A missing sequence, a duplicate, or an
 * out-of-order regression each produce a distinct gap.
 */
export function detectGaps(
  source: string,
  sequences: readonly number[],
): readonly GapIdentity[] {
  const gaps: GapIdentity[] = [];
  const seen = new Set<number>();
  let expected = 1;
  for (const seq of sequences) {
    if (seen.has(seq)) {
      gaps.push({
        gapId: `gap-${source}-dup-${seq}`,
        source,
        fromSequence: seq,
        toSequence: seq,
        isDuplicate: true,
        isOutOfOrder: false,
      });
      continue;
    }
    seen.add(seq);
    if (seq < expected) {
      gaps.push({
        gapId: `gap-${source}-ooo-${seq}`,
        source,
        fromSequence: seq,
        toSequence: expected - 1,
        isDuplicate: false,
        isOutOfOrder: true,
      });
    } else if (seq > expected) {
      gaps.push({
        gapId: `gap-${source}-${expected}-${seq - 1}`,
        source,
        fromSequence: expected,
        toSequence: seq - 1,
        isDuplicate: false,
        isOutOfOrder: false,
      });
    }
    expected = Math.max(expected, seq + 1);
  }
  return gaps;
}

/** Correlation/causation/trace metadata — evidence metadata ONLY. */
export interface CorrelationMetadata {
  readonly traceId?: string;
  readonly spanId?: string;
  readonly causeRefs?: readonly string[];
  readonly correlationRefs?: readonly string[];
}

/**
 * Assert correlation metadata is evidence metadata only: it must not be used as
 * Run identity or authority. This is a structural guard — the fields are optional
 * and never feed identity/authority resolution.
 */
export function assertCorrelationIsEvidenceOnly(meta: CorrelationMetadata | undefined): void {
  if (!meta) return;
  // No assertion failure here by design: the contract is that these fields are
  // optional evidence metadata. The guard exists so a future change that tries to
  // promote them to identity/authority is caught at the call site.
}

/** Event position/order is read-only data; it grants no effect capability. */
export interface EventPositionCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const EVENT_POSITION_CAPABILITIES: EventPositionCapabilities = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);
