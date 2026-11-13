"use client";

import { useEffect, useState } from 'react';
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
  onOpen?: (path: string, kind: string) => void;
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
  onOpen,
}: {
  paths: string[];
  kind: string;
  onOpen?: (path: string, kind: string) => void;
}) {
  if (!paths.length) return <div className="dwo-unknown">No entries.</div>;
  return (
    <div className="dwo-click-list">
      {paths.map((p) => (
        <button key={p} className="dwo-open-btn" data-kind={kind} disabled={!onOpen} title={!onOpen ? "Content viewer unavailable for this reference" : undefined} onClick={() => onOpen?.(p, kind)}>
          {p}
        </button>
      ))}
    </div>
  );
}

function EventList({ events, emptyText = "No events." }: { events: unknown[]; emptyText?: string }) {
  if (!events.length) return <div className="dwo-unknown">{emptyText}</div>;
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

export default function NodeInspector({ node, activeTab, onTabChange, onOpen }: NodeInspectorProps) {
  // SSR controls must not accept a first click before event handlers hydrate.
  const [interactive, setInteractive] = useState(false);
  useEffect(() => setInteractive(true), []);
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

  const hasNoCanonicalSourceContract = node.rawEvidence?.some(
    (evidence) => evidence.classification.reason === "NO_CANONICAL_SOURCE_CONTRACT",
  ) ?? false;
  const unavailableContractReason = hasNoCanonicalSourceContract
    ? " — no canonical source contract is available."
    : ".";

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
            disabled={!interactive}
            onClick={() => onTabChange(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Overview */}
      {activeTab === "overview" && (
        <div className="dwo-inspector-pane" data-pane="overview" data-testid="inspector-overview">
          <section className="dwo-inspector-group" aria-labelledby="inspector-state-heading">
            <h3 id="inspector-state-heading" className="dwo-inspector-group-title">State</h3>
            <Field label="Gate" value={node.gateId ?? "UNKNOWN"} />
            <Field label="Gate state" value={node.gateState ?? "UNKNOWN"} />
          </section>
          <section className="dwo-inspector-group" aria-labelledby="inspector-provenance-heading">
            <h3 id="inspector-provenance-heading" className="dwo-inspector-group-title">Provenance</h3>
            <Field label="Family / Node type" value={`${node.family ?? "—"} / ${node.nodeType ?? "—"}`} />
            <Field label="Authority boundary" value={node.authorityBoundary ?? "UNKNOWN"} />
            <Field label="Source status / maturity" value={`${node.sourceStatus ?? "—"} / ${node.maturity ?? "—"}`} />
            <Field label="Declared gates" value={node.declaredGates.length ? node.declaredGates.join(", ") : "—"} />
          </section>
          <section className="dwo-inspector-group" aria-labelledby="inspector-evidence-heading">
            <h3 id="inspector-evidence-heading" className="dwo-inspector-group-title">Evidence</h3>
            <Field label="Purpose" value={node.purpose ?? "—"} />
          </section>
        </div>
      )}

      {/* Files */}
      {activeTab === "files" && (
        <div className="dwo-inspector-pane" data-pane="files">
          <FieldWithChildren label="Reads">
            <ClickList paths={node.fileReads} kind="read" />
            <span className="dwo-unknown">File reads are not fixture evidence and cannot be opened here.</span>
          </FieldWithChildren>
          <FieldWithChildren label="Writes">
            <ClickList paths={node.fileWrites} kind="write" />
            <span className="dwo-unknown">File write references are read-only metadata; content access is unavailable.</span>
          </FieldWithChildren>
        </div>
      )}

      {/* Artifacts */}
      {activeTab === "artifacts" && (
        <div className="dwo-inspector-pane" data-pane="artifacts">
          <ClickList paths={node.artifacts} kind="artifact" onOpen={onOpen} />
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
            <div className="dwo-unknown">Runbook unavailable{unavailableContractReason}</div>
          )}
        </div>
      )}

      {/* History */}
      {activeTab === "history" && (
        <div className="dwo-inspector-pane" data-pane="history">
          <h4 className="dwo-h3">TaskController History</h4>
          <EventList events={node.taskControllerHistory} />
          {!node.taskControllerHistory.length && <div className="dwo-unknown">TaskController history unavailable{unavailableContractReason}</div>}
          <h4 className="dwo-h3">Executor History</h4>
          <EventList events={node.executorHistory} />
          {!node.executorHistory.length && <div className="dwo-unknown">Executor history unavailable{unavailableContractReason}</div>}
        </div>
      )}

      {/* Checkpoints */}
      {activeTab === "checkpoints" && (
        <div className="dwo-inspector-pane" data-pane="checkpoints">
          {node.checkpoints.length ? (
            <EventList events={node.checkpoints} />
          ) : (
            <>
              <div className="dwo-unknown">No checkpoints</div>
              <div className="dwo-unknown">Checkpoints unavailable{unavailableContractReason}</div>
            </>
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