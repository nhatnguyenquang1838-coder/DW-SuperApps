"use client";

import type { UnifiedRuntimeNode } from "@/lib/runtime/unifiedRuntime";

type InspectorTab =
  | "overview"
  | "files"
  | "artifacts"
  | "runbook"
  | "history"
  | "checkpoints"
  | "raw";

interface NodeInspectorProps {
  node: UnifiedRuntimeNode | null;
  activeTab: InspectorTab;
  onTabChange: (tab: InspectorTab) => void;
}

const TABS: { id: InspectorTab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "files", label: "Files" },
  { id: "artifacts", label: "Artifacts" },
  { id: "runbook", label: "Runbook" },
  { id: "history", label: "History" },
  { id: "checkpoints", label: "Checkpoints" },
  { id: "raw", label: "Raw" },
];

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="dwo-inspector-field">
      <span className="dwo-inspector-label">{label}</span>
      <span className="dwo-inspector-value">{value}</span>
    </div>
  );
}

function FieldWithChildren({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="dwo-inspector-field">
      <span className="dwo-inspector-label">{label}</span>
      <span className="dwo-inspector-value">{children}</span>
    </div>
  );
}

function ClickList({
  paths,
  kind,
}: {
  paths: string[];
  kind: string;
}) {
  if (!paths.length) return <div className="dwo-unknown">No entries.</div>;
  return (
    <div className="dwo-click-list">
      {paths.map((p) => (
        <button key={p} className="dwo-open-btn" data-kind={kind}>
          {p}
        </button>
      ))}
    </div>
  );
}

function EventList({ events }: { events: unknown[] }) {
  if (!events.length) return <div className="dwo-unknown">No events.</div>;
  return (
    <>
      {events.map((e, i) => (
        <div key={i} className="dwo-event">
          <b>{JSON.stringify(e)}</b>
        </div>
      ))}
    </>
  );
}

export default function NodeInspector({ node, activeTab, onTabChange }: NodeInspectorProps) {
  if (!node) {
    return (
      <div className="dwo-inspector" data-testid="node-inspector" data-state="empty">
        <div className="dwo-inspector-tabs">
          {TABS.map((t) => (
            <button
              key={t.id}
              className="dwo-inspector-tab"
              data-tab={t.id}
              disabled
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="dwo-inspector-pane">
          <span className="dwo-unknown">No node selected</span>
        </div>
      </div>
    );
  }

  return (
    <div className="dwo-inspector" data-testid="node-inspector" data-state="loaded">
      <div className="dwo-inspector-current">
        <div className="dwo-inspector-id" data-testid="inspector-node-id">
          {node.id}
        </div>
        <div className="dwo-inspector-name" data-testid="inspector-node-title">
          {node.title}
        </div>
        <div className="dwo-inspector-meta">
          {node.family ?? "—"} / {node.nodeType ?? "—"}
        </div>
      </div>

      <div className="dwo-inspector-tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={`dwo-inspector-tab${activeTab === t.id ? " active" : ""}`}
            data-tab={t.id}
            onClick={() => onTabChange(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Overview */}
      {activeTab === "overview" && (
        <div className="dwo-inspector-pane" data-pane="overview">
          <Field label="Gate" value={node.gateId ?? "UNKNOWN"} />
          <Field label="Family / Node type" value={`${node.family ?? "—"} / ${node.nodeType ?? "—"}`} />
          <Field label="Authority boundary" value={node.authorityBoundary ?? "UNKNOWN"} />
          <Field label="Source status / maturity" value={`${node.sourceStatus ?? "—"} / ${node.maturity ?? "—"}`} />
          <Field label="Declared gates" value={node.declaredGates.length ? node.declaredGates.join(", ") : "—"} />
          <Field label="Purpose" value={node.purpose ?? "—"} />
        </div>
      )}

      {/* Files */}
      {activeTab === "files" && (
        <div className="dwo-inspector-pane" data-pane="files">
          <FieldWithChildren label="Reads">
            <ClickList paths={node.fileReads} kind="read" />
          </FieldWithChildren>
          <FieldWithChildren label="Writes">
            <ClickList paths={node.fileWrites} kind="write" />
          </FieldWithChildren>
        </div>
      )}

      {/* Artifacts */}
      {activeTab === "artifacts" && (
        <div className="dwo-inspector-pane" data-pane="artifacts">
          <ClickList paths={node.artifacts} kind="artifact" />
        </div>
      )}

      {/* Runbook */}
      {activeTab === "runbook" && (
        <div className="dwo-inspector-pane" data-pane="runbook">
          {node.runbook.length ? (
            node.runbook.map((step, i) => (
              <div key={i} className="dwo-event">
                <b>{i + 1}. {step}</b>
              </div>
            ))
          ) : (
            <div className="dwo-unknown">No runbook entries</div>
          )}
        </div>
      )}

      {/* History */}
      {activeTab === "history" && (
        <div className="dwo-inspector-pane" data-pane="history">
          <h4 className="dwo-h3">TaskController History</h4>
          <EventList events={node.taskControllerHistory} />
          <h4 className="dwo-h3">Executor History</h4>
          <EventList events={node.executorHistory} />
        </div>
      )}

      {/* Checkpoints */}
      {activeTab === "checkpoints" && (
        <div className="dwo-inspector-pane" data-pane="checkpoints">
          {node.checkpoints.length ? (
            <EventList events={node.checkpoints} />
          ) : (
            <div className="dwo-unknown">No checkpoints</div>
          )}
        </div>
      )}

      {/* Raw */}
      {activeTab === "raw" && (
        <div className="dwo-inspector-pane" data-pane="raw">
          <pre className="dwo-raw">
            {JSON.stringify(node, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}