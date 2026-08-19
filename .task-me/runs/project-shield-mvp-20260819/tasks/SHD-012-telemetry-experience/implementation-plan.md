1. Define telemetry attributes and redaction tests around semantic IDs.
2. Add trace/span context propagation through Shield↔TaskController adapter and a minimal OTLP/exporter abstraction.
3. Implement ExperienceRecord derivation/eligibility/provenance and dataset roles.
4. Add deterministic scorer interface and fixtures for future eval provider integration; measure no-audit-loss when exporter fails.
