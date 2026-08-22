import { useState } from "react";
import type { LoginEpicRun, RuntimeNode, RuntimeGate } from "@/lib/loginEpicRuntimeGraph";
import { makeArtifactPreview } from "@/lib/loginEpicRuntimeGraph";

type Tab = "overview" | "files" | "artifacts" | "runbook" | "history" | "raw";

const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "files", label: "Files" },
  { id: "artifacts", label: "Artifacts" },
  { id: "runbook", label: "Runbook" },
  { id: "history", label: "History" },
  { id: "raw", label: "Raw" },
];

/**
 * RuntimeDetailsPanel — right panel with 6 tabs. History splits TaskController /
 * Executor; Files splits reads/writes; Artifacts includes checkpoints. Every
 * file/artifact/checkpoint row opens ArtifactModal (via onOpen).
 */
export default function RuntimeDetailsPanel({
  run,
  gate,
  node,
  onOpen,
}: {
  run: LoginEpicRun;
  gate: RuntimeGate | undefined;
  node: RuntimeNode | undefined;
  onOpen: (path: string, kind: string) => void;
}) {
  const [tab, setTab] = useState<Tab>("overview");

  if (!node || !gate) {
    return (
      <div className="leg-details" data-testid="runtime-details-panel">
        <div className="leg-current">Select a runtime node to inspect its details.</div>
      </div>
    );
  }

  return (
    <div className="leg-details" data-testid="runtime-details-panel">
      <div className="leg-current">
        <div className="leg-current-id">{node.id}</div>
        <div className="leg-current-name">{node.title}</div>
        <div className="leg-current-purpose">{node.purpose}</div>
        <div className="leg-current-meta">
          {gate.id} · {node.family} · {node.boundary}
        </div>
      </div>
      <div className="leg-tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={`leg-tab${tab === t.id ? " active" : ""}`}
            data-testid={`runtime-detail-tab-${t.id}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "overview" && (
        <div className="leg-pane" data-pane="overview">
          <div className="leg-field"><span>Gate</span><b>{gate.id} · {gate.label}</b></div>
          <div className="leg-field"><span>Family / Type</span><b>{node.family} / {node.type}</b></div>
          <div className="leg-field"><span>Boundary</span><b>{node.boundary}</b></div>
        </div>
      )}

      {tab === "files" && (
        <div className="leg-pane" data-pane="files">
          <div className="leg-field">
            <span>File Reads</span>
            {node.fileReads.length ? (
              node.fileReads.map((p) => (
                <button key={p} className="leg-open" data-testid="runtime-file-read" onClick={() => onOpen(p, "fileRead")}>
                  {p}
                </button>
              ))
            ) : (
              <i>none</i>
            )}
          </div>
          <div className="leg-field">
            <span>File Writes / Source-code writes</span>
            {node.fileWrites.length ? (
              node.fileWrites.map((p) => (
                <button key={p} className="leg-open" data-testid="runtime-file-write" onClick={() => onOpen(p, "fileWrite")}>
                  {p}
                </button>
              ))
            ) : (
              <i>none</i>
            )}
          </div>
        </div>
      )}

      {tab === "artifacts" && (
        <div className="leg-pane" data-pane="artifacts">
          <div className="leg-field">
            <span>Artifacts</span>
            {node.artifacts.map((p) => (
              <button key={p} className="leg-open" data-testid="runtime-artifact" onClick={() => onOpen(p, "artifact")}>
                {p}
              </button>
            ))}
          </div>
          <div className="leg-field">
            <span>Checkpoints</span>
            {node.checkpoints.length ? (
              node.checkpoints.map((p) => (
                <button key={p} className="leg-open" data-testid="runtime-checkpoint" onClick={() => onOpen(p, "checkpoint")}>
                  {p}
                </button>
              ))
            ) : (
              <i>none</i>
            )}
          </div>
        </div>
      )}

      {tab === "runbook" && (
        <div className="leg-pane" data-pane="runbook">
          {node.runbook.map((s, i) => (
            <div key={i} className="leg-event"><b>{i + 1}. {s}</b></div>
          ))}
        </div>
      )}

      {tab === "history" && (
        <div className="leg-pane" data-pane="history">
          <h3>TaskController History</h3>
          {node.taskControllerHistory.length ? (
            node.taskControllerHistory.map((e, i) => (
              <div key={i} className="leg-event"><b>{e}</b></div>
            ))
          ) : (
            <i>none</i>
          )}
          <h3>Executor History</h3>
          {node.executorHistory.length ? (
            node.executorHistory.map((e, i) => (
              <div key={i} className="leg-event"><b>{e}</b></div>
            ))
          ) : (
            <i>none</i>
          )}
        </div>
      )}

      {tab === "raw" && (
        <div className="leg-pane" data-pane="raw">
          <pre className="leg-raw">{JSON.stringify(node, null, 2)}</pre>
        </div>
      )}

      {/* keep makeArtifactPreview referenced for deterministic preview generation */}
      <span hidden>{makeArtifactPreview({ run, gate, node, path: node.artifacts[0] ?? "n/a", cursor: 0 }).length}</span>
    </div>
  );
}
