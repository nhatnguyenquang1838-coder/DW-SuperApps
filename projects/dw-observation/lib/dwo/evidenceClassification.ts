/**
 * Evidence classification follows only explicit local source-contract bindings.
 * This fixture pack contains no canonical bindings for runbooks, TaskController
 * history, Executor history, or replay checkpoints; receipts remain raw evidence.
 */
export type EvidenceClassification =
  | { readonly kind: "raw"; readonly reason: "NO_CANONICAL_SOURCE_CONTRACT" };

export interface EvidenceSourceCandidate {
  readonly sourcePath: string;
  readonly content: string;
  readonly record: unknown;
}

export function classifyEvidenceSource(_source: EvidenceSourceCandidate): EvidenceClassification {
  return { kind: "raw", reason: "NO_CANONICAL_SOURCE_CONTRACT" };
}
