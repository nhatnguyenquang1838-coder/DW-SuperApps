/**
 * R2-E — ParentCompositionContractV2.
 *
 * `isParentComplete` in recursiveTopology.ts answers a narrower question:
 * "is the parent's OWN gate state terminal?" It deliberately ignores children,
 * which is correct for independence but insufficient for composition — a parent
 * sitting at G6/PASSED with unverified children is not composed.
 *
 * This module supplies the missing half: the explicit contract that says WHICH
 * children are required, which handoff receipts must exist, and which
 * parent-level and target-level proofs are separate obligations.
 *
 * The failure this prevents: reading a parent's G6/PASSED (or its children's
 * G6/PASSED) as proof that the composed deliverable exists. Child acceptance
 * is evidence ABOUT a child. Composition is a separate claim about the parent,
 * and target acceptance is a separate claim again.
 *
 * Every field is explicitly present and explicitly proven. A missing receipt
 * is unresolved, not waived.
 */

/** One required child's declared composition participation. */
export interface RequiredChildDeclaration {
  readonly runId: string;
  /** Digest pinning the child's terminal state record. */
  readonly completionDigest: string | 'UNKNOWN';
  /** The handoff receipt ref proving this child's work was handed over. */
  readonly handoffReceiptRef: string | 'UNKNOWN';
}

/** One optional child's declaration — absence never blocks composition. */
export interface OptionalChildDeclaration {
  readonly runId: string;
  readonly completionDigest: string | 'UNKNOWN';
  readonly handoffReceiptRef: string | 'UNKNOWN';
}

/**
 * The explicit parent composition contract.
 *
 * `requiredHandoffReceiptRefs` is the receipt set the CONTRACT requires, and
 * `requiredChildren` is the per-child evidence. Both must hold — a receipt set
 * without per-child evidence does not prove any particular child composed.
 */
export interface ParentCompositionContractV2 {
  readonly parentRunId: string;
  readonly revisionId: string;
  readonly requiredChildren: readonly RequiredChildDeclaration[];
  readonly optionalChildren: readonly OptionalChildDeclaration[];
  /** Receipt refs the contract requires, independent of per-child refs. */
  readonly requiredHandoffReceiptRefs: readonly string[];
  /** Proves the composed parent artifact. Separate from child evidence. */
  readonly parentVerificationRef: string | 'UNKNOWN';
  /** Proves the target accepted the composed result. Separate again. */
  readonly targetAcceptanceRef: string | 'UNKNOWN';
}

/** The parent's own declared gate position and gate state. */
export interface ParentOwnState {
  readonly gate: string | 'UNKNOWN';
  readonly gateState: string | 'UNKNOWN';
}

/** Reason codes for why composition did not complete. */
export type CompositionReason =
  | 'COMPOSED'
  | 'COMPOSITION_COMPLETE_NOT_ACCEPTED'
  | 'MISSING_PARENT_STATE'
  | 'MISSING_REVISION_ID'
  | 'MISSING_PARENT_VERIFICATION'
  | 'MISSING_TARGET_ACCEPTANCE'
  | 'MISSING_REQUIRED_CHILD'
  | 'MISSING_CHILD_COMPLETION_DIGEST'
  | 'MISSING_CHILD_HANDOFF_RECEIPT'
  | 'MISSING_REQUIRED_RECEIPT'
  | 'UNEXPECTED_RECEIPT'
  | 'CHILD_DIGEST_MISMATCH'
  | 'UNKNOWN_UNRESOLVED';

/** The read-only composition decision. */
export interface CompositionDecision {
  /** True only when every composition obligation is proven. */
  readonly composed: boolean;
  /** True only when composed AND target acceptance is proven. */
  readonly accepted: boolean;
  readonly reason: CompositionReason;
  readonly missingRefs: readonly string[];
  /** Per-required-child completion status, keyed by runId. */
  readonly childCompletion: Readonly<Record<string, boolean>>;
}

const UNRESOLVED = 'UNKNOWN';

function isEstablished(value: string | 'UNKNOWN'): value is string {
  return typeof value === 'string' && value.length > 0 && value !== UNRESOLVED;
}

/**
 * Evaluate parent composition against the explicit contract.
 *
 * Composition is a conjunction of independent obligations:
 *   1. the contract itself is identified (parent run + revision);
 *   2. every required child has proven completion AND an explicit handoff
 *      receipt — a child at G6/PASSED with no receipt is unresolved;
 *   3. every receipt the contract requires actually exists;
 *   4. the parent carries its own verification ref — a child's success is
 *      never a substitute;
 *   5. target acceptance is proven separately and is NOT implied by (4).
 *
 * The parent's own gate position is deliberately NOT sufficient: reaching G6
 * without the evidence below leaves composition unresolved. That is the whole
 * point of the contract.
 */
export function evaluateParentCompositionContract(
  contract: ParentCompositionContractV2,
  parentState: ParentOwnState,
  presentReceiptRefs: readonly string[],
  expectedChildDigests: Readonly<Record<string, string>> = {},
): CompositionDecision {
  const missing: string[] = [];
  const childCompletion: Record<string, boolean> = {};

  if (!isEstablished(contract.parentRunId)) {
    missing.push('parentRunId');
  }
  if (!isEstablished(contract.revisionId)) {
    // A composition claim without a revision is not a claim about any
    // particular version of the parent.
    missing.push('revisionId');
  }

  // 2. Required children — completion AND an explicit handoff receipt each.
  for (const child of contract.requiredChildren) {
    let ok = true;
    if (!isEstablished(child.runId)) {
      missing.push(`required-child:${child.runId || '<empty>'}`);
      ok = false;
    }
    if (!isEstablished(child.completionDigest)) {
      missing.push(`child-completion:${child.runId}`);
      ok = false;
    }
    const expected = expectedChildDigests[child.runId];
    if (expected !== undefined && expected !== child.completionDigest) {
      // The declared child digest disagrees with the authoritative record.
      missing.push(`child-digest-mismatch:${child.runId}`);
      ok = false;
    }
    if (!isEstablished(child.handoffReceiptRef)) {
      missing.push(`child-handoff:${child.runId}`);
      ok = false;
    }
    childCompletion[child.runId] = ok;
  }

  // 3. Required receipts must exist. An unexpected extra receipt is a fact
  //    worth surfacing, but not by itself a composition failure.
  const present = new Set(presentReceiptRefs);
  for (const ref of contract.requiredHandoffReceiptRefs) {
    if (!isEstablished(ref)) {
      missing.push(`required-receipt:${ref || '<empty>'}`);
      continue;
    }
    if (!present.has(ref)) {
      missing.push(`required-receipt:${ref}`);
    }
  }

  // 4. Parent verification is its own obligation.
  if (!isEstablished(contract.parentVerificationRef)) {
    missing.push('parentVerificationRef');
  }

  // 5. Target acceptance is separate and evaluated separately.
  const accepted = isEstablished(contract.targetAcceptanceRef);

  // The parent's own gate position is recorded as context. It is deliberately
  // NOT an input to `composed`: a parent at G6/PASSED with unproven children
  // or a missing verification ref stays unresolved.
  if (!isEstablished(parentState.gate) || !isEstablished(parentState.gateState)) {
    missing.push('parentState');
  }

  if (missing.length > 0) {
    return {
      composed: false,
      accepted: false,
      reason: classifyComposition(missing),
      missingRefs: missing,
      childCompletion,
    };
  }

  if (!accepted) {
    // Composition obligations are all proven, but the target has not accepted.
    // This is a real, distinct outcome — not a composition failure.
    return {
      composed: true,
      accepted: false,
      reason: 'COMPOSITION_COMPLETE_NOT_ACCEPTED',
      missingRefs: ['targetAcceptanceRef'],
      childCompletion,
    };
  }

  return {
    composed: true,
    accepted: true,
    reason: 'COMPOSED',
    missingRefs: [],
    childCompletion,
  };
}

/**
 * Map composition violations onto the most specific single reason.
 * Precedence follows obligation order: contract identity, then child
 * evidence, then receipts, then parent verification, then acceptance.
 */
function classifyComposition(missing: readonly string[]): CompositionReason {
  const has = (p: string) => missing.some((m) => m.startsWith(p));

  if (has('child-digest-mismatch')) return 'CHILD_DIGEST_MISMATCH';
  if (has('required-child')) return 'MISSING_REQUIRED_CHILD';
  if (has('child-completion')) return 'MISSING_CHILD_COMPLETION_DIGEST';
  if (has('child-handoff')) return 'MISSING_CHILD_HANDOFF_RECEIPT';
  if (has('required-receipt')) return 'MISSING_REQUIRED_RECEIPT';
  if (has('parentVerificationRef')) return 'MISSING_PARENT_VERIFICATION';
  if (has('targetAcceptanceRef')) return 'MISSING_TARGET_ACCEPTANCE';
  if (has('parentState')) return 'MISSING_PARENT_STATE';
  if (has('revisionId') || has('parentRunId')) return 'MISSING_REVISION_ID';
  return 'UNKNOWN_UNRESOLVED';
}

/**
 * Guard: a parent must never be treated as composed on child state alone.
 * Returns true only when the contract decision itself says composed.
 */
export function isParentComposedUnderContract(decision: CompositionDecision): boolean {
  return decision.composed;
}

/** Parent composition is read-only; it grants no effect capability. */
export interface ParentCompositionCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const PARENT_COMPOSITION_CAPABILITIES: ParentCompositionCapabilities = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);
