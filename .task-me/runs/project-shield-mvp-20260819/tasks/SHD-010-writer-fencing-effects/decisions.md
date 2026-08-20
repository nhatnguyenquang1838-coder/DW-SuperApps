# Decisions
Use single-writer epoch/fencing, not general distributed consensus. Protected effect identity is explicit and idempotent. Shared ledger is mutation-ownership truth across hosts; conflicting records never use last-write-wins.
