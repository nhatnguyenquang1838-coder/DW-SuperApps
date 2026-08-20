1. Add tests for schedule signal, review origin/depth/idempotency and budget.
2. Implement SelfReviewProfile + due-trigger normalization.
3. Implement bounded review workflow using deterministic scorers first and optional provider reviewers.
4. Persist review outputs/audit refs; prove self-review terminal event cannot recursively trigger POST_RUN review.
