1. Add split-brain/stale-writer/failover tests before implementation.
2. Implement shared-durable RunWriterLease with monotonic epoch/fencing token.
3. Implement EffectIntent/EffectReceipt stores and pre-effect validation/idempotency.
4. Implement recovery reconciliation for missing receipt and stale writer sync; integrate with TaskController checkpoint recovery tests.
