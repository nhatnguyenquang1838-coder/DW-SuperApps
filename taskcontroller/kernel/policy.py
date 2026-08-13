"""WP1 DONE acceptance policy (exact review binding; no fuzzy matching).

REVIEWING -> DONE is allowed only when a ReviewResult with verdict=PASS is
exactly bound to the target node/artifact and its evidence + criteria cover
the contract's required_evidence and acceptance_criteria as subsets (exact
item equality; extras allowed).
"""

from __future__ import annotations

from taskcontroller.domain.enums import ReviewVerdict
from taskcontroller.domain.models import ReviewResult, TaskContract
from taskcontroller.domain.values import NodeState
from taskcontroller.kernel.errors import ReviewNotBinding


def evaluate_done_acceptance(
    contract: TaskContract,
    node: NodeState,
    reviews: list[ReviewResult],
) -> ReviewResult:
    """Return the PASS review that binds the node to DONE, or raise
    ReviewNotBinding if no exact-binding PASS review exists.

    Binding rule (exact item equality, subset semantics):
    - verdict == PASS
    - target_ref == node.contract_ref OR target_ref in node.artifact_refs (exact equality)
    - set(contract.required_evidence[].evidence_id) ⊆ set(review.evidence_refs)
    - set(contract.acceptance_criteria) ⊆ set(review.criteria)
    - plan_version + run_version must match the contract's (checked in plans.py;
      this function additionally verifies they match the contract).
    """
    nid = node.status  # placeholder: node carrier
    contract_evidence: set[str] = {
        e.evidence_id for e in contract.required_evidence if hasattr(e, "evidence_id")
    }
    contract_criteria: set[str] = set(contract.acceptance_criteria)

    for r in reviews:
        if r.verdict != ReviewVerdict.PASS.value:
            continue
        if not _target_refs_bind(r, node):
            continue
        review_evidence: set[str] = set(r.evidence_refs or [])
        review_criteria: set[str] = set(r.criteria or [])
        if not contract_evidence.issubset(review_evidence):
            continue
        if not contract_criteria.issubset(review_criteria):
            continue
        # verify version alignment with the contract
        if r.plan_version != getattr(contract, "plan_version", ""):
            continue
        if r.run_version != getattr(contract, "run_version", ""):
            continue
        return r

    raise ReviewNotBinding(
        f"no exact-binding PASS review for node contract_ref={node.contract_ref!r}, "
        f"acceptance_criteria={contract_criteria!r}, required_evidence={contract_evidence!r}"
    )


def _target_refs_bind(review: ReviewResult, node: NodeState) -> bool:
    """Exact equality binding between review.target_ref and node's contract_ref
    or produced artifact_refs."""
    target = review.target_ref
    if target == node.contract_ref:
        return True
    return target in list(node.artifact_refs or [])