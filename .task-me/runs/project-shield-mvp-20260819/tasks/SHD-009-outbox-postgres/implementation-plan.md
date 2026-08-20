1. Write failing atomicity/idempotency/divergence tests around existing SQLite writer.
2. Introduce audit UnitOfWork that appends event + outbox in one transaction without breaking existing facade semantics.
3. Add PostgresRunLedger/replica port, schema and idempotent sync/readback worker.
4. Add local/cloud assurance state and conflict classifications; run SQLite + TaskController regression suites.
