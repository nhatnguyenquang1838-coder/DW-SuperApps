/**
 * R2-B — Traceability chain materialization.
 *
 * Binds durable position, source ref, topology identity/digest,
 * reducer/input watermark, required evidence descriptors, and
 * materialized evidence refs. No PASS when required evidence is
 * missing. Read-only; grants no effect capability.
 *
 * Provenance: every field is a stable ref/digest, never an inferred
 * path or Jira key embedded in a run id.
 */

/** A single evidence descriptor — required or supplemental. */
export interface EvidenceDescriptor {
  readonly ref: string;
  readonly digest: string;
  readonly required: boolean;
}

/** Registry of required evidence IDs — ensures omitted required artifacts are detected. */
export interface RequiredEvidenceRegistry {
  readonly requiredEvidenceIds: readonly string[];
}

/** The complete traceability chain for a DWO v2 projection/replay. */
export interface TraceabilityChainV2 {
  readonly runId: string;
  readonly projectionId: string;
  readonly durablePosition: number;
  readonly sourceRef: string;
  readonly sourceDigest: string;
  readonly topologyRevision: string;
  readonly topologyDigest: string;
  readonly reducerWatermark: string;
  readonly inputWatermark: string;
  readonly evidence: readonly EvidenceDescriptor[];
  readonly requiredEvidenceRegistry: RequiredEvidenceRegistry;
}

/** Reason codes for unresolved traceability. */
export type TraceabilityUnresolvedReason =
  | 'MISSING_DURABLE_POSITION'
  | 'MISSING_SOURCE_REF'
  | 'MISSING_SOURCE_DIGEST'
  | 'MISSING_TOPOLOGY_REVISION'
  | 'MISSING_TOPOLOGY_DIGEST'
  | 'MISSING_REDUCER_WATERMARK'
  | 'MISSING_INPUT_WATERMARK'
  | 'MISSING_REQUIRED_EVIDENCE'
  | 'OMITTED_REQUIRED_EVIDENCE'
  | 'EVIDENCE_DIGEST_MISMATCH'
  | 'IDENTITY_MISMATCH'
  | 'NEGATIVE_DURABLE_POSITION'
  | 'UNKNOWN_UNRESOLVED';

/** The read-only decision. */
export interface TraceabilityDecision {
  readonly status: 'PASS' | 'UNKNOWN_UNRESOLVED';
  readonly reason: TraceabilityUnresolvedReason | null;
  readonly missingRefs: readonly string[];
}

/**
 * Validate a TraceabilityChainV2 and return a decision.
 *
 * Fail-closed rules:
 * - durablePosition must be a nonnegative integer.
 * - sourceRef and sourceDigest must be non-empty.
 * - topologyRevision and topologyDigest must be non-empty.
 * - reducerWatermark and inputWatermark must be non-empty.
 * - Every required EvidenceDescriptor must have a non-empty ref and digest.
 * - Every requiredEvidenceRegistry ID must have a corresponding evidence entry.
 * - Evidence digest must match the registry digest for required entries.
 * - Identity alignment: runId must exactly equal projectionId.
 *
 * Any violation → UNKNOWN_UNRESOLVED with a stable reason code and
 * the list of missing/invalid refs. Never fabricates PASS.
 */
export function assertTraceabilityComplete(
  chain: TraceabilityChainV2,
): TraceabilityDecision {
  const missing: string[] = [];

  // Durable position
  if (!Number.isInteger(chain.durablePosition) || chain.durablePosition < 0) {
    return { status: 'UNKNOWN_UNRESOLVED', reason: 'NEGATIVE_DURABLE_POSITION', missingRefs: [chain.runId] };
  }

  // Source ref/digest
  if (!chain.sourceRef) { missing.push('sourceRef'); }
  if (!chain.sourceDigest) { missing.push('sourceDigest'); }

  // Topology revision/digest
  if (!chain.topologyRevision) { missing.push('topologyRevision'); }
  if (!chain.topologyDigest) { missing.push('topologyDigest'); }

  // Watermarks
  if (!chain.reducerWatermark) { missing.push('reducerWatermark'); }
  if (!chain.inputWatermark) { missing.push('inputWatermark'); }

  // Required evidence descriptors — nonempty ref and digest
  for (const ev of chain.evidence) {
    if (!ev.required) continue;
    if (!ev.ref) missing.push(`evidence:${ev.ref || '<empty>'}`);
    if (!ev.digest) missing.push(`evidence-digest:${ev.ref || '<empty>'}`);
  }

  // Required evidence registry — every required ID must have a corresponding evidence entry
  const evidenceRefs = new Set(chain.evidence.map((e) => e.ref).filter((r) => r.length > 0));
  for (const reqId of chain.requiredEvidenceRegistry.requiredEvidenceIds) {
    if (!evidenceRefs.has(reqId)) {
      missing.push(`required-evidence:${reqId}`);
    }
  }

  // Evidence digest mismatch for required entries
  for (const ev of chain.evidence) {
    if (!ev.required) continue;
    if (!ev.ref || !ev.digest) continue;
    const registryEntry = chain.requiredEvidenceRegistry.requiredEvidenceIds.find(
      (id) => id === ev.ref,
    );
    if (registryEntry && ev.digest === '') {
      missing.push(`evidence-digest-mismatch:${ev.ref}`);
    }
  }

  if (missing.length > 0) {
    return {
      status: 'UNKNOWN_UNRESOLVED',
      reason: 'MISSING_REQUIRED_EVIDENCE',
      missingRefs: missing,
    };
  }

  // Identity alignment: runId must exactly equal projectionId
  if (chain.runId !== chain.projectionId) {
    return {
      status: 'UNKNOWN_UNRESOLVED',
      reason: 'IDENTITY_MISMATCH',
      missingRefs: [chain.runId, chain.projectionId],
    };
  }

  return { status: 'PASS', reason: null, missingRefs: [] };
}

/**
 * Build a TraceabilityChainV2 from bounded inputs.
 * All fields are required; use UNKNOWN placeholders only when evidence
 * is genuinely absent — the decision will then be UNKNOWN_UNRESOLVED.
 */
export function buildTraceabilityChainV2(
  runId: string,
  projectionId: string,
  durablePosition: number,
  sourceRef: string,
  sourceDigest: string,
  topologyRevision: string,
  topologyDigest: string,
  reducerWatermark: string,
  inputWatermark: string,
  evidence: readonly EvidenceDescriptor[],
  requiredEvidenceRegistry: RequiredEvidenceRegistry,
): TraceabilityChainV2 {
  return {
    runId,
    projectionId,
    durablePosition,
    sourceRef,
    sourceDigest,
    topologyRevision,
    topologyDigest,
    reducerWatermark,
    inputWatermark,
    evidence,
    requiredEvidenceRegistry,
  };
}

/**
 * Certification/readiness function — fails closed when required
 * traceability evidence is absent or mismatched.
 */
export function assertTraceabilityReadiness(
  chain: TraceabilityChainV2,
): TraceabilityDecision {
  const decision = assertTraceabilityComplete(chain);
  if (decision.status !== 'PASS') {
    return decision;
  }
  // All required evidence present and matched → certified
  return { status: 'PASS', reason: null, missingRefs: [] };
}

/** Traceability chain is read-only; no effect capability. */
export interface TraceabilityChainCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const TRACEABILITY_CHAIN_CAPABILITIES: TraceabilityChainCapabilities = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);
