/**
 * CR-824-D — V2_REDUCER_CERTIFIED derivation.
 *
 * SCRUM-824 / DWO-V2-03, G2 EXECUTE, PLAN-824-R1, child run CR-824-D.
 *
 * The WS3 exit token V2_REDUCER_CERTIFIED is DERIVED from machine-readable state,
 * never asserted. It holds exactly when:
 *   1. the reducer is deterministic (same event prefix -> same state);
 *   2. missing facts stay UNKNOWN/PARTIAL;
 *   3. parent completion is never inferred solely from child-local success;
 *   4. recursive Root/Child/Atomic reduction + dependency blocking path are correct;
 *   5. the reducer conforms to the fixture stream.
 */
import { reduceEventPrefix, type ReducerEvent } from './reducer';
import { isParentComplete, type RunTree } from './recursiveTopology';
import { assertTraceabilityReadiness, type TraceabilityChainV2, type TraceabilityDecision } from './traceabilityChain';
import { AuthorityEvidence, type AuthorityDecision } from './authorityVocabulary';
import type { CompositionDecision } from './parentComposition';

export interface ReducerCertificationInput {
  /** Determinism: same prefix reduced twice yields identical state. */
  readonly deterministic: boolean;
  /** Missing facts stay UNKNOWN/PARTIAL. */
  readonly missingFactsStayUnknown: boolean;
  /** Parent completion never inferred solely from child-local success. */
  readonly parentCompositionIndependent: boolean;
  /** Recursive reduction + blocking path correct. */
  readonly recursiveAndBlockingCorrect: boolean;
  /** Reducer conforms to the fixture stream. */
  readonly fixtureConformance: boolean;
  /** C3: traceability readiness must be PASS before certification issues a token. */
  readonly traceabilityDecision: TraceabilityDecision;
  /** R2-D: authority decision where authority is required. Absent = not applicable. */
  readonly authorityDecision?: AuthorityDecision | null;
  /** R2-E: explicit parent composition decision where a composed parent is required. Absent = not applicable. */
  readonly parentComposition?: CompositionDecision | null;
  /** R2-D: explicit source evidence used to derive the authority decision (audit provenance). */
  readonly authorityEvidence?: AuthorityEvidence | null;
}

export interface ReducerCertificationDecision {
  readonly derivable: boolean;
  readonly token: string | null;
  readonly reasons: readonly string[];
}

/**
 * Derive V2_REDUCER_CERTIFIED. Fails closed on any incoherent input.
 */
export function deriveV2ReducerCertified(
  input: ReducerCertificationInput,
): ReducerCertificationDecision {
  const reasons: string[] = [];
  if (!input.deterministic) reasons.push('reducer is not deterministic');
  if (!input.missingFactsStayUnknown) reasons.push('missing facts do not stay UNKNOWN/PARTIAL');
  if (!input.parentCompositionIndependent) reasons.push('parent completion inferred from child-local success');
  if (!input.recursiveAndBlockingCorrect) reasons.push('recursive reduction or blocking path incorrect');
  if (!input.fixtureConformance) reasons.push('reducer does not conform to fixture stream');
  // C3: certification cannot issue PASS/token when traceability is unresolved
  if (input.traceabilityDecision.status !== 'PASS') {
    reasons.push(`traceability unresolved: ${input.traceabilityDecision.reason ?? 'unknown'}`);
  }
  // R2-D: when authority evidence is present, GRANTED is required.
  // Absence of the field = authority not applicable to this run.
  if (input.authorityDecision !== undefined && input.authorityDecision !== null) {
    const ad = input.authorityDecision;
    if (!ad.granted) {
      reasons.push(`authority not granted: ${ad.state} (${ad.reason})`);
    }
  }
  // R2-E: when a composition decision is present, composed is required.
  // Absence of the field = parent composition not applicable to this run.
  if (input.parentComposition !== undefined && input.parentComposition !== null) {
    const pc = input.parentComposition;
    if (!pc.composed) {
      reasons.push(`parent not composed: ${pc.reason}`);
    }
  }
  if (reasons.length === 0) {
    return { derivable: true, token: 'V2_REDUCER_CERTIFIED', reasons: [] };
  }
  return { derivable: false, token: null, reasons };
}

/**
 * C3 integration surface: derive certification from a real traceability
 * chain. This is the path that makes traceability a gate on the exit token
 * rather than an optional helper a caller may forget to invoke.
 *
 * It does not duplicate the derivation — it resolves the traceability
 * decision via assertTraceabilityReadiness and delegates to the single
 * deriveV2ReducerCertified decision function.
 */
export function deriveV2ReducerCertifiedFromChain(
  input: Omit<ReducerCertificationInput, 'traceabilityDecision'>,
  chain: TraceabilityChainV2,
): ReducerCertificationDecision {
  const traceabilityDecision = assertTraceabilityReadiness(chain);
  return deriveV2ReducerCertified({ ...input, traceabilityDecision });
}

/**
 * Determinism check: reduce the same ordered prefix twice and assert identical
 * state. Returns true when the two reductions are structurally equal.
 */
export function assertDeterministicReduction(
  runId: string,
  events: readonly ReducerEvent[],
): boolean {
  const a = reduceEventPrefix(runId, events);
  const b = reduceEventPrefix(runId, events);
  return JSON.stringify(a) === JSON.stringify(b);
}

/**
 * Parent-composition independence check: a parent whose children are all ACCEPTED
 * but whose own gate is not G6/PASSED must NOT be complete.
 */
export function assertParentCompositionIndependent(
  tree: RunTree,
  parentId: string,
  childrenAccepted: boolean,
): boolean {
  const parent = tree.nodes[parentId];
  if (!parent) return false;
  const complete = isParentComplete(tree, parentId);
  // F5: independence holds across BOTH the gate position and the gateState
  // dimension. If children are accepted but the parent is not G6/PASSED, the
  // parent must NOT be complete.
  if (childrenAccepted) {
    const atG6 = parent.state.gate === 'G6';
    const passed = parent.state.gateState === 'PASSED';
    if (!atG6 || !passed) {
      return complete === false;
    }
  }
  return true;
}

/** Reducer certification is read-only; it grants no effect capability. */
export interface CertificationCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const CERTIFICATION_CAPABILITIES: CertificationCapabilities = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);

/** Exit-token registry. */
export const EXIT_TOKENS = Object.freeze({
  v2ReducerCertified: 'V2_REDUCER_CERTIFIED',
} as const);
