/**
 * CR-823-D — FNR-02 deterministic certification comparison contract.
 *
 * SCRUM-823 / DWO-V2-02, G2 EXECUTE, PLAN-822-R1, child run CR-823-D.
 *
 * FNR-02 is the canonical owner of the deterministic certification comparison
 * contract used by SCRUM-824/825/830/832. It is FROZEN here, versioned, and has
 * cross-runtime golden/test vectors proving equivalent and non-equivalent states.
 *
 * Design decisions:
 *  1. Certification equality is VERSIONED STRUCTURED-STATE EQUALITY, NOT a
 *     lightweight UI digest. The contract explicitly separates the two.
 *  2. Comparison is deterministic: included/excluded fields, ordering rules,
 *     null/UNKNOWN handling, and normalization are all explicit.
 *  3. V2_CONTRACT_FROZEN is DERIVED from machine-readable state, never asserted.
 */

/** The FNR-02 comparison contract schema id + version. */
export const FNR02_CONTRACT_ID = 'gwc.dwo.fnr02-comparison';
export const FNR02_CONTRACT_VERSION = 1;

/** Comparison mode: certification uses structured-state equality, not UI digest. */
export type ComparisonMode = 'STRUCTURED_STATE_EQUALITY' | 'CANONICAL_DIGEST';

/** The frozen FNR-02 comparison contract. */
export interface Fnr02ComparisonContract {
  readonly contractId: typeof FNR02_CONTRACT_ID;
  readonly contractVersion: typeof FNR02_CONTRACT_VERSION;
  readonly mode: ComparisonMode;
  /** Fields included in certification comparison. */
  readonly includedFields: readonly string[];
  /** Fields excluded from certification comparison (e.g. UI-only digests). */
  readonly excludedFields: readonly string[];
  /** Deterministic ordering rule for array/collection fields. */
  readonly orderingRule: 'SORTED_KEYS' | 'SEQUENCE_ORDER';
  /** null/UNKNOWN handling. */
  readonly nullUnknownHandling: 'FAIL_CLOSED' | 'EQUAL_IF_BOTH_UNKNOWN';
  /** Normalization/canonicalization rule. */
  readonly normalization: 'JCS_SORTED_KEYS';
  /** Cross-runtime golden vectors proving equivalent and non-equivalent states. */
  readonly crossRuntimeVectors: readonly CrossRuntimeVector[];
}

/** A cross-runtime golden vector. */
export interface CrossRuntimeVector {
  readonly id: string;
  readonly description: string;
  readonly expected: 'EQUIVALENT' | 'NON_EQUIVALENT';
  readonly left: unknown;
  readonly right: unknown;
}

/**
 * The frozen FNR-02 contract with cross-runtime vectors.
 *
 * The vectors prove: two structurally identical states are EQUIVALENT; two states
 * differing in an included field are NON_EQUIVALENT; a UI-only digest difference
 * does NOT make certification states non-equivalent (UI digest is excluded).
 */
export const FNR02_CONTRACT: Fnr02ComparisonContract = Object.freeze({
  contractId: FNR02_CONTRACT_ID,
  contractVersion: FNR02_CONTRACT_VERSION,
  mode: 'STRUCTURED_STATE_EQUALITY',
  includedFields: ['runId', 'runState', 'gates', 'sourceProfile', 'syncState', 'semanticQualification', 'authorityState', 'anomalyCount'],
  excludedFields: ['uiDigest', 'uiLayout', 'traceId', 'spanId'],
  orderingRule: 'SORTED_KEYS',
  nullUnknownHandling: 'FAIL_CLOSED',
  normalization: 'JCS_SORTED_KEYS',
  crossRuntimeVectors: [
    {
      id: 'VEC-01',
      description: 'structurally identical states are equivalent',
      expected: 'EQUIVALENT',
      left: { runId: 'DEV-RUN-001', runState: 'OPEN', gates: [{ namespace: 'UR_G', gate: 'G2', state: 'ACTIVE' }] },
      right: { runId: 'DEV-RUN-001', runState: 'OPEN', gates: [{ namespace: 'UR_G', gate: 'G2', state: 'ACTIVE' }] },
    },
    {
      id: 'VEC-02',
      description: 'states differing in an included field are non-equivalent',
      expected: 'NON_EQUIVALENT',
      left: { runId: 'DEV-RUN-001', runState: 'OPEN' },
      right: { runId: 'DEV-RUN-001', runState: 'ACCEPTED' },
    },
    {
      id: 'VEC-03',
      description: 'a UI-only digest difference does not make certification states non-equivalent',
      expected: 'EQUIVALENT',
      left: { runId: 'DEV-RUN-001', runState: 'OPEN', uiDigest: 'abc' },
      right: { runId: 'DEV-RUN-001', runState: 'OPEN', uiDigest: 'def' },
    },
    {
      id: 'VEC-04',
      description: 'a gate namespace conflation is non-equivalent',
      expected: 'NON_EQUIVALENT',
      left: { runId: 'DEV-RUN-001', gates: [{ namespace: 'UR_G', gate: 'G2', state: 'ACTIVE' }] },
      right: { runId: 'DEV-RUN-001', gates: [{ namespace: 'GWC_EFFECT', gate: 'G4_MERGE', state: 'ACTIVE' }] },
    },
  ],
} as const);

/** Normalize a state for comparison: JCS sorted keys, keep only included fields. */
export function normalizeForComparison(
  state: Record<string, unknown>,
  contract: Fnr02ComparisonContract = FNR02_CONTRACT,
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const key of Object.keys(state).sort()) {
    // FNR-02 contract: only includedFields participate in certification
    // equality. A field outside includedFields (and not excluded) must NOT
    // make two otherwise-identical states non-equivalent — otherwise the
    // declared includedFields list is dead and comparison is not the
    // versioned structured-state equality the contract promises.
    if (!contract.includedFields.includes(key)) continue;
    if (contract.excludedFields.includes(key)) continue;
    out[key] = state[key];
  }
  return out;
}

/** Recursive canonical serializer: sorted keys at every level, no replacer filtering. */
function canonicalStringify(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map(canonicalStringify).join(',')}]`;
  }
  if (value !== null && typeof value === 'object') {
    const obj = value as Record<string, unknown>;
    const keys = Object.keys(obj).sort();
    return `{${keys.map((k) => `${JSON.stringify(k)}:${canonicalStringify(obj[k])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

/**
 * Compare two states under the FNR-02 contract.
 *
 * Returns EQUIVALENT when the normalized included fields are structurally equal,
 * NON_EQUIVALENT otherwise. null/UNKNOWN handling is FAIL_CLOSED: a null on one
 * side and a value on the other is non-equivalent.
 */
export function compareStates(
  left: Record<string, unknown>,
  right: Record<string, unknown>,
  contract: Fnr02ComparisonContract = FNR02_CONTRACT,
): 'EQUIVALENT' | 'NON_EQUIVALENT' {
  const l = normalizeForComparison(left, contract);
  const r = normalizeForComparison(right, contract);
  return canonicalStringify(l) === canonicalStringify(r)
    ? 'EQUIVALENT'
    : 'NON_EQUIVALENT';
}

/** Inputs from which V2_CONTRACT_FROZEN is derived. */
export interface ContractFrozenInput {
  readonly contractId: string;
  readonly contractVersion: number;
  readonly mode: ComparisonMode;
  readonly hasCrossRuntimeVectors: boolean;
  readonly vectorsPass: boolean;
}

export interface ContractFrozenDecision {
  readonly derivable: boolean;
  readonly token: string | null;
  readonly reasons: readonly string[];
}

/**
 * Derive V2_CONTRACT_FROZEN. Fails closed on any incoherent input.
 */
export function deriveV2ContractFrozen(input: ContractFrozenInput): ContractFrozenDecision {
  const reasons: string[] = [];
  if (input.contractId !== FNR02_CONTRACT_ID) {
    reasons.push(`contract id ${input.contractId}, expected ${FNR02_CONTRACT_ID}`);
  }
  if (input.contractVersion !== FNR02_CONTRACT_VERSION) {
    reasons.push(`contract version ${input.contractVersion}, expected ${FNR02_CONTRACT_VERSION}`);
  }
  if (input.mode !== 'STRUCTURED_STATE_EQUALITY') {
    reasons.push(`comparison mode ${input.mode}, expected STRUCTURED_STATE_EQUALITY (not UI digest)`);
  }
  if (!input.hasCrossRuntimeVectors) {
    reasons.push('no cross-runtime vectors');
  }
  if (!input.vectorsPass) {
    reasons.push('cross-runtime vectors do not pass');
  }
  if (reasons.length === 0) {
    return { derivable: true, token: 'V2_CONTRACT_FROZEN', reasons: [] };
  }
  return { derivable: false, token: null, reasons };
}

/** Exit-token registry. */
export const EXIT_TOKENS = Object.freeze({
  v2ContractFrozen: 'V2_CONTRACT_FROZEN',
} as const);
