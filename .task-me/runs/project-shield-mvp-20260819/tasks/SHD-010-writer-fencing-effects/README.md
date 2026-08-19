# SHD-010 — Writer fencing & effect recovery
Sequence numbers alone cannot prevent split-brain side effects. Require current writer epoch/fencing token and a shared-durable EffectIntent before protected mutation. Recovery with missing receipt performs provider-state reconciliation instead of blind retry.
