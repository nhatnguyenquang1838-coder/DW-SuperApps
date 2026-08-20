# Decisions
Local write + outbox is one transaction. PostgreSQL is provider-neutral; Supabase is low-ops MVP option, RDS fits protected AWS/VPC deployment. Shared durability is explicit assurance, not implicit network success.
