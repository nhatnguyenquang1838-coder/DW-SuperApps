/**
 * CR-827-A — Evidence Inspector.
 *
 * SCRUM-827 / DWO-V2-06, G2 EXECUTE, PLAN-827-R1, child run CR-827-A.
 *
 * The Evidence Inspector surfaces source/profile/ref/digest/provenance fields for
 * a run's evidence. Provenance is shown as RECORDED; a missing fact stays UNKNOWN
 * and is never invented (AC-827-04).
 *
 * Design decisions:
 *  1. Evidence is read-only data; the inspector never fabricates a fact.
 *  2. A run with no recorded evidence reports missingFacts and invented=false.
 *  3. Provenance is carried verbatim from the record; absent provenance stays
 *     UNKNOWN, never synthesized.
 */

/** A single evidence record with provenance fields. */
export interface EvidenceRecord {
  readonly runId: string;
  readonly source: string;
  readonly profile: string;
  readonly ref: string;
  readonly digest: string;
  readonly provenance: string;
}

/** The result of inspecting a run's evidence. */
export interface EvidenceInspection {
  readonly runId: string;
  readonly records: readonly EvidenceRecord[];
  /** Run ids that have no recorded evidence (facts are missing, not invented). */
  readonly missingFacts: readonly string[];
  /** True when the inspector fabricated any fact. Always false by construction. */
  readonly invented: false;
}

/**
 * Inspect a run's evidence.
 *
 * Returns the recorded records verbatim. A run with no records is reported as a
 * missing fact; the inspector never invents provenance or a digest.
 */
export function inspectEvidence(
  runId: string,
  records: readonly EvidenceRecord[],
): EvidenceInspection {
  const matching = records.filter((r) => r.runId === runId);
  return {
    runId,
    records: matching,
    missingFacts: matching.length === 0 ? [runId] : [],
    invented: false,
  };
}

/** The evidence inspector is read-only; it grants no effect capability. */
export interface EvidenceCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const EVIDENCE_CAPABILITIES: EvidenceCapabilities = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);
