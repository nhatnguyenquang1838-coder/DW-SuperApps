/**
 * CR-821-B — Universal source drift classification (FNR-03).
 *
 * SCRUM-821 / DWO-V2-00, G2 EXECUTE, PLAN-821-R2, child run CR-821-B.
 *
 * Contract sources:
 *   - C4 §21.3 FNR-03 D-W-03..D-W-06, the canonical six-value drift taxonomy
 *   - Handoff §8 drift classification + REPLAN_REQUIRED rule
 *   - BRD FNR-014 (moving refs are not certification evidence)
 *
 * Design decisions that matter:
 *
 *  1. The taxonomy is a six-value ENUM, never a numeric threshold. There is no
 *     "how far did the head move" scoring. FNR-03 deliberately forbids magnitude
 *     heuristics: two different SHAs with an identical contract are COMPATIBLE.
 *
 *  2. Classification is derived from CONTRACT EVIDENCE, not from the branch name or
 *     commit distance. `classifyDrift` consumes an explicit evidence record.
 *
 *  3. BLOCKING_CONTRACT_DRIFT is the only value that forces REPLAN_REQUIRED. Every
 *     other value triggers affected-scope revalidation, not a restart. This encodes
 *     the handoff rule that normal release-development head movement does not
 *     automatically restart the Epic.
 *
 *  4. Classification is a pure function. It observes; it never resolves refs,
 *     never mutates state, and grants no authority.
 */

/** The canonical FNR-03 taxonomy, re-exported from the binding registry vocabulary. */
export type DriftClassification =
  | 'COMPATIBLE'
  | 'ADAPTER_CHANGE'
  | 'REDUCER_CHANGE'
  | 'UI_CHANGE'
  | 'QUALIFICATION_CHANGE'
  | 'BLOCKING_CONTRACT_DRIFT';

export const DRIFT_CLASSIFICATIONS: readonly DriftClassification[] = [
  'COMPATIBLE',
  'ADAPTER_CHANGE',
  'REDUCER_CHANGE',
  'UI_CHANGE',
  'QUALIFICATION_CHANGE',
  'BLOCKING_CONTRACT_DRIFT',
];

/** Contract-bearing surfaces, mapped to the FNR-03 classification they imply. */
export type ContractSurface =
  /** Source binding / adapter / projection contract v2 boundary. */
  | 'ADAPTER'
  /** UniversalRun reducer, recursive topology, blocking path. */
  | 'REDUCER'
  /** Any DWO presentation surface. */
  | 'UI'
  /** Semantic + resilience qualification subject. */
  | 'QUALIFICATION';

/**
 * The ordered precedence used when several contract surfaces moved at once.
 *
 * Precedence is BLOCKING > REDUCER > ADAPTER > QUALIFICATION > UI > COMPATIBLE.
 *
 * Rationale, from the handoff: after SCRUM-824 a reducer/core-contract review is
 * mandatory precisely so that later UX work cannot hide a reducer semantic defect.
 * A reducer change therefore must not be downgraded to a UI or adapter label just
 * because other surfaces also moved.
 */
const PRECEDENCE: readonly DriftClassification[] = [
  'BLOCKING_CONTRACT_DRIFT',
  'REDUCER_CHANGE',
  'ADAPTER_CHANGE',
  'QUALIFICATION_CHANGE',
  'UI_CHANGE',
  'COMPATIBLE',
];

export interface DriftEvidence {
  /** The previously bound exact SHA. */
  readonly previousSha: string;
  /** The newly resolved exact SHA. */
  readonly currentSha: string;
  /** JCS+SHA-256 content digest of the previously consumed kernel contract. */
  readonly previousContractDigest: string;
  /** JCS+SHA-256 content digest of the currently offered kernel contract. */
  readonly currentContractDigest: string;
  /**
   * Contract surfaces that actually changed, determined by exact digest comparison.
   * A caller MUST NOT pass surfaces it has not diffed; `classifyDrift` trusts this
   * field because the diff requires repository access DWO does not have.
   */
  readonly changedSurfaces: readonly ContractSurface[];
  /**
   * The lifecycle profile identity offered by the new source. A profile change is
   * definitionally blocking, because the kernel treats it as an unsupported subject.
   */
  readonly lifecycleProfileChanged: boolean;
  /**
   * Set when the new source declares itself incompatible for this DWO surface set.
   * Fail-closed: an explicit incompatibility declaration is never downgraded.
   */
  readonly declaresIncompatible?: boolean;
}

export type RevalidationDirective =
  /** Re-verify the named surfaces. The plan stays valid. */
  | 'AFFECTED_REVALIDATION'
  /** The active RuntimePlan is invalidated; a new immutable revision is required. */
  | 'REPLAN_REQUIRED'
  /** No contract surface moved. Continue. */
  | 'NO_ACTION';

export interface DriftDecision {
  readonly classification: DriftClassification;
  readonly directive: RevalidationDirective;
  /** Surfaces that must be re-verified. Empty only for NO_ACTION / COMPATIBLE. */
  readonly surfacesToRevalidate: readonly ContractSurface[];
  /**
   * True when the new head moved but the contract did not. This is the case the
   * handoff calls out explicitly: head movement alone is not a restart trigger.
   */
  readonly headMovedContractUnchanged: boolean;
  readonly rationale: string;
}

/** Map one changed contract surface to its implied classification. */
const SURFACE_TO_CLASSIFICATION: Record<ContractSurface, DriftClassification> = {
  REDUCER: 'REDUCER_CHANGE',
  ADAPTER: 'ADAPTER_CHANGE',
  UI: 'UI_CHANGE',
  QUALIFICATION: 'QUALIFICATION_CHANGE',
};

function strongest(classifications: readonly DriftClassification[]): DriftClassification {
  for (const level of PRECEDENCE) {
    if (classifications.includes(level)) return level;
  }
  return 'COMPATIBLE';
}

const EMPTY: readonly ContractSurface[] = [];

/**
 * Classify drift from exact contract evidence.
 *
 * Fails closed toward BLOCKING: an explicit incompatibility declaration, a lifecycle
 * profile change, or a contract digest change with no surface attribution all
 * classify as blocking rather than assuming compatibility.
 */
export function classifyDrift(evidence: DriftEvidence): DriftDecision {
  const headMoved = evidence.previousSha !== evidence.currentSha;
  const contractUnchanged =
    evidence.previousContractDigest === evidence.currentContractDigest &&
    evidence.changedSurfaces.length === 0 &&
    !evidence.lifecycleProfileChanged;

  if (evidence.declaresIncompatible === true || evidence.lifecycleProfileChanged) {
    return {
      classification: 'BLOCKING_CONTRACT_DRIFT',
      directive: 'REPLAN_REQUIRED',
      surfacesToRevalidate: EMPTY,
      headMovedContractUnchanged: false,
      rationale: evidence.lifecycleProfileChanged
        ? 'lifecycle profile identity changed; kernel treats the new profile as an unsupported qualification subject'
        : 'source declares itself incompatible for the active DWO surface set',
    };
  }

  // Contract digest changed but no surface was attributed. We cannot prove which
  // contract moved, so we must not claim it was benign.
  if (evidence.previousContractDigest !== evidence.currentContractDigest && evidence.changedSurfaces.length === 0) {
    return {
      classification: 'BLOCKING_CONTRACT_DRIFT',
      directive: 'REPLAN_REQUIRED',
      surfacesToRevalidate: EMPTY,
      headMovedContractUnchanged: false,
      rationale:
        'kernel contract digest changed with no attributable surface diff; drift cannot be scoped, so it fails closed',
    };
  }

  if (evidence.changedSurfaces.length === 0) {
    return {
      classification: 'COMPATIBLE',
      directive: contractUnchanged && !headMoved ? 'NO_ACTION' : 'AFFECTED_REVALIDATION',
      surfacesToRevalidate: EMPTY,
      headMovedContractUnchanged: headMoved,
      rationale: headMoved
        ? 'release-development head advanced but the consumed contract is byte-identical'
        : 'same exact SHA and identical contract; nothing to revalidate',
    };
  }

  const classification = strongest(
    evidence.changedSurfaces.map((s) => SURFACE_TO_CLASSIFICATION[s]),
  );

  return {
    classification,
    // Only BLOCKING forces a replan. Everything else revalidates the affected scope.
    directive: 'AFFECTED_REVALIDATION',
    surfacesToRevalidate: [...new Set(evidence.changedSurfaces)].sort(),
    headMovedContractUnchanged: false,
    rationale: `contract surfaces changed: ${[...new Set(evidence.changedSurfaces)].sort().join(', ')}`,
  };
}

/**
 * Replan gate.
 *
 * Kept separate so the plan-boundary rule is one named decision rather than an
 * inline ternary that can drift. Only BLOCKING_CONTRACT_DRIFT replans.
 */
export function requiresReplan(classification: DriftClassification): boolean {
  return classification === 'BLOCKING_CONTRACT_DRIFT';
}

/** DWO observes and classifies. It never resolves, rebinds, or grants authority. */
export interface DriftCapabilities {
  readonly observe: true;
  readonly classify: true;
  readonly resolveRef: false;
  readonly rebind: false;
  readonly writeBinding: false;
  readonly consumeAuthority: false;
}

export const DRIFT_CAPABILITIES: DriftCapabilities = Object.freeze({
  observe: true,
  classify: true,
  resolveRef: false,
  rebind: false,
  writeBinding: false,
  consumeAuthority: false,
} as const);
