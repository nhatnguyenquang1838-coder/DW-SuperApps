// Read-only DAG view: renders observed gates/nodes as recorded in the
// projection. No edges are inferred; only explicitly recorded state is shown.
export default function DagView({
  gates,
  nodes,
}: {
  gates: Record<string, Record<string, unknown>>;
  nodes: Record<string, Record<string, unknown>>;
}) {
  const gateEntries = Object.entries(gates);
  const nodeEntries = Object.entries(nodes);

  return (
    <div className="rounded-lg border border-edge bg-panel p-4">
      <h2 className="mb-3 text-base font-semibold">Read-only DAG</h2>

      <h3 className="mb-1 text-sm text-muted">Gates</h3>
      {gateEntries.length === 0 ? (
        <p className="mb-3 text-sm text-muted">—</p>
      ) : (
        <ul className="mb-4 space-y-1">
          {gateEntries.map(([name, g]) => (
            <li
              key={name}
              className="flex items-center gap-3 rounded border border-edge/60 bg-surface px-3 py-1.5 text-sm"
            >
              <span className="code font-medium">{name}</span>
              <span className="rounded bg-edge px-2 py-0.5 text-xs">
                {(g.status as string) ?? "—"}
              </span>
              {g.approved_by ? (
                <span className="text-xs text-muted">
                  approved_by:{" "}
                  {typeof g.approved_by === "object"
                    ? JSON.stringify(g.approved_by)
                    : String(g.approved_by)}
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      )}

      <h3 className="mb-1 text-sm text-muted">Nodes</h3>
      {nodeEntries.length === 0 ? (
        <p className="text-sm text-muted">—</p>
      ) : (
        <ul className="space-y-1">
          {nodeEntries.map(([name, n]) => (
            <li
              key={name}
              className="flex items-center gap-3 rounded border border-edge/60 bg-surface px-3 py-1.5 text-sm"
            >
              <span className="code font-medium">{name}</span>
              <span className="rounded bg-edge px-2 py-0.5 text-xs">
                {(n.status as string) ?? "—"}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
