# Evidence Model

Use a typed local evidence graph.

Nodes:
- requirement, acceptance_criterion, design_decision;
- system, service, API, event, database, table;
- package, file, symbol, configuration, test;
- task.

Edges:
- satisfies, implements, requires_change;
- imports, calls, reads, writes;
- publishes, consumes, tested_by;
- blocks, requires, parallel_with.

Every claim must include provenance:

```json
{
  "source_path": "path/in/repo",
  "line_or_symbol": "verified reference",
  "evidence_type": "explicit|lexical|structural|historical|test",
  "confidence": 0.0
}
```

Never promote semantic similarity alone to a verified implementation target.
