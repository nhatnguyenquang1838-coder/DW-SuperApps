import type { SimGate, SimNode, Selection, HistoryEvent, Checkpoint } from "@/lib/simRun";

type Props = {
  selection: Selection;
  gate: SimGate;
  node: SimNode | undefined; // undefined when selection.kind === "gate"
  onOpenArtifact: (path: string, kind: string) => void;
};

function EventList({ events, tag }: { events: HistoryEvent[]; tag: string }) {
  return (
    <>
      {events.map((e) => (
        <div className="sr-event" key={e.event_id}>
          <b>
            {tag} · {e.type}
          </b>
          <div>
            {e.event_id} · {e.actor} · {e.outcome} · {(e.evidence ?? []).join(", ")}
          </div>
        </div>
      ))}
    </>
  );
}

function CheckpointList({ checkpoints }: { checkpoints: Checkpoint[] }) {
  return (
    <>
      {checkpoints.map((c) => (
        <div className="sr-event" key={c.checkpoint_id}>
          <b>{c.checkpoint_id}</b>
          <div>
            rev={c.revision} · lease={c.lease_owner} · fencing={c.fencing_token} ·
            status={c.status}
          </div>
        </div>
      ))}
    </>
  );
}

function ClickList({
  paths,
  kind,
  onOpen,
}: {
  paths: string[];
  kind: string;
  onOpen: (path: string, kind: string) => void;
}) {
  if (!paths.length) return <div className="sr-field">No entries.</div>;
  return (
    <div className="sr-click-list">
      {paths.map((p) => (
        <button
          key={p}
          className="sr-open-btn"
          onClick={() => onOpen(p, kind)}
        >
          {p}
        </button>
      ))}
    </div>
  );
}

/**
 * Right-hand inspector panel. Tabs: Overview / Artifacts / Runbook / History /
 * Raw. When a NODE is selected, History splits into TaskController History,
 * Executor History and Checkpoints. Artifacts/read/impl-refs open a modal.
 */
export default function Inspector({ selection, gate, node, onOpenArtifact }: Props) {
  const id = node ? `${node.node_label ?? node.node_id} · ${node.node_id}` : gate.id;
  const title = node ? node.title : gate.label;
  const desc = node ? node.description : gate.summary;

  return (
    <div className="sr-inspector-body">
      <div className="sr-current">
        <div className="sr-current-id">{id}</div>
        <div className="sr-current-name">{title}</div>
        <div className="sr-current-desc">{desc}</div>
      </div>

      <div className="sr-tabs">
        {["overview", "artifacts", "runbook", "history", "raw"].map((t) => (
          <button key={t} className="sr-tab" data-tab={t}>
            {t[0].toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {/* Overview */}
      <div className="sr-tab-pane" data-pane="overview">
        {node ? (
          <>
            <div className="sr-field">
              <div className="sr-label">Gate</div>
              <div className="sr-value">
                {gate.id} · {gate.label}
              </div>
            </div>
            <div className="sr-field">
              <div className="sr-label">Family / Node type</div>
              <div className="sr-value sr-mono">
                {node.family} / {node.node_type}
              </div>
            </div>
            <div className="sr-field">
              <div className="sr-label">Authority boundary</div>
              <div className="sr-value">{node.authority_boundary}</div>
            </div>
            <div className="sr-field">
              <div className="sr-label">Source status / maturity</div>
              <div className="sr-value">
                {node.source_status ?? "—"} / {node.maturity ?? "—"}
              </div>
            </div>
            <div className="sr-field">
              <div className="sr-label">Declared gates</div>
              <div className="sr-value">{(node.declared_gates ?? []).join(", ")}</div>
            </div>
          </>
        ) : (
          <>
            <div className="sr-field">
              <div className="sr-label">Gate artifacts</div>
              <div className="sr-value">{gate.gate_artifacts.length}</div>
            </div>
            <div className="sr-field">
              <div className="sr-label">Runtime nodes in this simulated run</div>
              <div className="sr-value">{gate.nodes.length}</div>
            </div>
            <div className="sr-field">
              <div className="sr-label">Gate history</div>
              <div className="sr-value">
                TaskController {gate.taskcontroller_history.length} · Executor{" "}
                {gate.executor_history.length}
              </div>
            </div>
          </>
        )}
      </div>

      {/* Artifacts */}
      <div className="sr-tab-pane" data-pane="artifacts" hidden>
        {node ? (
          <>
            <div className="sr-field">
              <div className="sr-label">Reads</div>
              <ClickList
                paths={node.reads}
                kind="read"
                onOpen={onOpenArtifact}
              />
            </div>
            <div className="sr-field">
              <div className="sr-label">Artifacts produced / observed</div>
              <ClickList
                paths={node.artifacts}
                kind="artifact"
                onOpen={onOpenArtifact}
              />
            </div>
            <div className="sr-field">
              <div className="sr-label">Implementation refs</div>
              <ClickList
                paths={node.implementation_refs ?? []}
                kind="implementation-ref"
                onOpen={onOpenArtifact}
              />
            </div>
          </>
        ) : (
          <div className="sr-field">
            <div className="sr-label">Gate artifacts</div>
            <ClickList
              paths={gate.gate_artifacts}
              kind="gate-artifact"
              onOpen={onOpenArtifact}
            />
          </div>
        )}
      </div>

      {/* Runbook */}
      <div className="sr-tab-pane" data-pane="runbook" hidden>
        {node ? (
          node.runbook.map((s, i) => (
            <div className="sr-event" key={i}>
              <b>
                {i + 1}. {s}
              </b>
              <div>Node task/runbook step for {node.node_id}</div>
            </div>
          ))
        ) : (
          <div className="sr-event">
            <b>Gate runbook</b>
            <div>Open gate → execute node sequence → validate artifacts → close gate / advance boundary.</div>
          </div>
        )}
      </div>

      {/* History */}
      <div className="sr-tab-pane" data-pane="history" hidden>
        {node ? (
          <>
            <h3 className="sr-h3">TaskController History</h3>
            <EventList events={node.taskcontroller_history} tag="TC" />
            <h3 className="sr-h3">Executor History</h3>
            <EventList events={node.executor_history} tag="Executor" />
            <h3 className="sr-h3">Checkpoints</h3>
            <CheckpointList checkpoints={node.checkpoints} />
          </>
        ) : (
          <>
            <EventList events={gate.taskcontroller_history} tag="TC" />
            <EventList events={gate.executor_history} tag="Executor" />
          </>
        )}
      </div>

      {/* Raw */}
      <div className="sr-tab-pane" data-pane="raw" hidden>
        <pre className="sr-raw">
          {JSON.stringify(node ?? gate, null, 2)}
        </pre>
      </div>
    </div>
  );
}
