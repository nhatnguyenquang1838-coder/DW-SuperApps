import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import UnifiedRunWorkspace from "@/components/dwo/UnifiedRunWorkspace";
import WorkspaceHeader from "@/components/dwo/WorkspaceHeader";
import ScenarioRunRail from "@/components/dwo/ScenarioRunRail";
import RunHierarchy from "@/components/dwo/RunHierarchy";
import NextFlowPanel from "@/components/dwo/NextFlowPanel";
import NodeInspector from "@/components/dwo/NodeInspector";
import RuntimePlayer from "@/components/dwo/RuntimePlayer";
import RuntimeGraphCanvas from "@/components/dwo/RuntimeGraphCanvas";
import { ReactFlowProvider } from "@xyflow/react";
import type { UnifiedRunWorkspaceModel, WorkspaceMode } from "@/lib/runtime/unifiedRuntime";

const makeModel = (overrides: Partial<UnifiedRunWorkspaceModel> = {}): UnifiedRunWorkspaceModel => ({
  runId: "T05-TEST-RUN",
  taskRef: "SCRUM-820",
  mode: "SIMULATED",
  status: "ACTIVE",
  hierarchy: null,
  nodes: [
    {
      id: "node-1",
      gateId: "G2_EXECUTION",
      title: "Login Capability Node",
      family: "runtime",
      nodeType: "login",
      authorityBoundary: "product/ui",
      sourceStatus: "ACTIVE",
      maturity: "stable",
      declaredGates: ["G2_EXECUTION"],
      purpose: "Render the login route entry screen",
      fileReads: ["lib/contracts/login.ts"],
      fileWrites: ["app/login/page.tsx"],
      artifacts: ["login.ts", "LoginForm.tsx"],
      runbook: ["Render login form", "Validate credentials", "Submit to API"],
      taskControllerHistory: [],
      executorHistory: [],
      checkpoints: [],
    },
    {
      id: "node-2",
      gateId: "G3_PR",
      title: "Auth Shell Node",
      family: "runtime",
      nodeType: "shell",
      authorityBoundary: "code_review",
      sourceStatus: "DONE",
      maturity: "stable",
      declaredGates: ["G3_PR"],
      purpose: "Compose the login screen shell",
      fileReads: [],
      fileWrites: ["components/auth/LoginShell.tsx"],
      artifacts: ["LoginShell.tsx"],
      runbook: ["Compose shell", "Render LoginForm"],
      taskControllerHistory: [],
      executorHistory: [],
      checkpoints: [],
    },
  ],
  edges: [
    { id: "dep-G2-G3", source: "node-1", target: "node-2", kind: "DEPENDENCY", state: "SATISFIED" },
  ],
  orderedSteps: [
    { nodeId: "node-1", sequence: 0 },
    { nodeId: "node-2", sequence: 1 },
  ],
  currentSequence: 0,
  canonicalHistoryAvailable: false,
  projectionStatus: "UNKNOWN",
  sourceDigest: null,
  ...overrides,
});

// ── WorkspaceHeader ────────────────────────────────────────────────

describe("WorkspaceHeader", () => {
  it("renders runId, mode badge, and status", () => {
    render(<WorkspaceHeader model={makeModel()} mode="SIMULATED" onModeChange={() => {}} />);
    expect(screen.getByTestId("workspace-header")).toBeInTheDocument();
    expect(screen.getByText("T05-TEST-RUN")).toBeInTheDocument();
    const badge = screen.getByTestId("workspace-header").querySelector('[data-mode="SIMULATED"]');
    expect(badge).toBeInTheDocument();
    expect(screen.getByText("ACTIVE")).toBeInTheDocument();
  });

  it("renders mode select with all three options", () => {
    render(<WorkspaceHeader model={makeModel()} mode="LIVE" onModeChange={() => {}} />);
    const select = screen.getByTestId("workspace-mode-select");
    expect(select).toBeInTheDocument();
    expect(select.querySelectorAll("option")).toHaveLength(3);
  });
});

// ── ScenarioRunRail ────────────────────────────────────────────────

describe("ScenarioRunRail", () => {
  it("renders run id and source digest", () => {
    render(<ScenarioRunRail model={makeModel()} selectedRunId="T05-TEST-RUN" onSelectRun={() => {}} />);
    expect(screen.getByTestId("scenario-run-rail")).toBeInTheDocument();
    expect(screen.getByText("T05-TEST-RUN")).toBeInTheDocument();
  });

  it("shows UNKNOWN when sourceDigest is null", () => {
    render(<ScenarioRunRail model={makeModel({ sourceDigest: null })} selectedRunId="T05-TEST-RUN" onSelectRun={() => {}} />);
    expect(screen.getByText("UNKNOWN")).toBeInTheDocument();
  });
});

// ── RunHierarchy ────────────────────────────────────────────────────

describe("RunHierarchy", () => {
  it("renders UNAVAILABLE when hierarchy is null", () => {
    render(<RunHierarchy model={makeModel({ hierarchy: null })} />);
    expect(screen.getByTestId("run-hierarchy")).toBeInTheDocument();
    expect(screen.getByText("UNAVAILABLE")).toBeInTheDocument();
  });

  it("renders hierarchy when provided", () => {
    const hierarchy = { root: { child: "leaf" } };
    render(<RunHierarchy model={makeModel({ hierarchy })} />);
    expect(screen.getByTestId("hierarchy-tree")).toBeInTheDocument();
  });
});

// ── NextFlowPanel ───────────────────────────────────────────────────

describe("NextFlowPanel", () => {
  it("shows UNKNOWN when currentSequence is null", () => {
    render(<NextFlowPanel model={makeModel({ currentSequence: null })} />);
    expect(screen.getByTestId("nextflow-panel")).toBeInTheDocument();
    const pane = screen.getByTestId("nextflow-panel");
    expect(pane).toHaveTextContent("UNKNOWN");
  });

  it("shows RESOLVED when next node is available", () => {
    render(<NextFlowPanel model={makeModel({ currentSequence: 0 })} />);
    expect(screen.getByTestId("nextflow-status")).toHaveTextContent("RESOLVED");
  });

  it("shows BLOCKED at final step", () => {
    render(<NextFlowPanel model={makeModel({ currentSequence: 1, orderedSteps: [{ nodeId: "node-1", sequence: 0 }, { nodeId: "node-2", sequence: 1 }] })} />);
    expect(screen.getByTestId("nextflow-status")).toHaveTextContent("BLOCKED");
  });
});

// ── NodeInspector ───────────────────────────────────────────────────

describe("NodeInspector", () => {
  const node = makeModel().nodes[0]!;

  it("renders empty state when no node selected", () => {
    render(<NodeInspector node={null} activeTab="overview" onTabChange={() => {}} />);
    expect(screen.getByTestId("node-inspector")).toBeInTheDocument();
    expect(screen.getByText("No node selected")).toBeInTheDocument();
  });

  it("renders all 7 tabs", () => {
    render(<NodeInspector node={node} activeTab="overview" onTabChange={() => {}} />);
    expect(screen.getByText("Overview")).toBeInTheDocument();
    expect(screen.getByText("Files")).toBeInTheDocument();
    expect(screen.getByText("Artifacts")).toBeInTheDocument();
    expect(screen.getByText("Runbook")).toBeInTheDocument();
    expect(screen.getByText("History")).toBeInTheDocument();
    expect(screen.getByText("Checkpoints")).toBeInTheDocument();
    expect(screen.getByText("Raw")).toBeInTheDocument();
  });

  it("renders Overview tab content", () => {
    const { container } = render(<NodeInspector node={node} activeTab="overview" onTabChange={() => {}} />);
    const pane = container.querySelector('[data-pane="overview"]');
    expect(pane).toHaveTextContent("G2_EXECUTION");
    expect(pane).toHaveTextContent("runtime / login");
  });

  it("renders Files tab with reads and writes labels", () => {
    render(<NodeInspector node={node} activeTab="files" onTabChange={() => {}} />);
    expect(screen.getByText("Reads")).toBeInTheDocument();
    expect(screen.getByText("Writes")).toBeInTheDocument();
  });

  it("renders Artifacts tab", () => {
    render(<NodeInspector node={node} activeTab="artifacts" onTabChange={() => {}} />);
    expect(screen.getByText("login.ts")).toBeInTheDocument();
    expect(screen.getByText("LoginForm.tsx")).toBeInTheDocument();
  });

  it("renders Runbook tab", () => {
    render(<NodeInspector node={node} activeTab="runbook" onTabChange={() => {}} />);
    expect(screen.getByText("1. Render login form")).toBeInTheDocument();
  });

  it("renders History tab with empty state", () => {
    render(<NodeInspector node={node} activeTab="history" onTabChange={() => {}} />);
    expect(screen.getAllByText("No events.")).toHaveLength(2);
  });

  it("renders Checkpoints tab with empty state", () => {
    render(<NodeInspector node={node} activeTab="checkpoints" onTabChange={() => {}} />);
    expect(screen.getByText("No checkpoints")).toBeInTheDocument();
  });

  it("renders Raw tab with JSON", () => {
    const { container } = render(<NodeInspector node={node} activeTab="raw" onTabChange={() => {}} />);
    expect(container.querySelector('[data-pane="raw"]')).toHaveTextContent('"id": "node-1"');
  });
});

// ── RuntimePlayer ───────────────────────────────────────────────────

describe("RuntimePlayer", () => {
  it("renders all controls", () => {
    render(
      <RuntimePlayer
        cursor={0}
        len={3}
        mode="SIMULATED"
        speed={750}
        playing={false}
        label="G2_EXECUTION · Login Capability Node"
        onFirst={() => {}}
        onPrev={() => {}}
        onToggle={() => {}}
        onNext={() => {}}
        onLast={() => {}}
        onScrub={() => {}}
        onMode={() => {}}
        onSpeed={() => {}}
      />,
    );
    expect(screen.getByTestId("runtime-player")).toBeInTheDocument();
    expect(screen.getByTestId("player-first")).toBeInTheDocument();
    expect(screen.getByTestId("player-prev")).toBeInTheDocument();
    expect(screen.getByTestId("player-play")).toBeInTheDocument();
    expect(screen.getByTestId("player-next")).toBeInTheDocument();
    expect(screen.getByTestId("player-last")).toBeInTheDocument();
  });

  it("shows cursor position", () => {
    render(
      <RuntimePlayer
        cursor={1}
        len={5}
        mode="REPLAY"
        speed={750}
        playing={false}
        label="test"
        onFirst={() => {}}
        onPrev={() => {}}
        onToggle={() => {}}
        onNext={() => {}}
        onLast={() => {}}
        onScrub={() => {}}
        onMode={() => {}}
        onSpeed={() => {}}
      />,
    );
    expect(screen.getByText("2 / 5")).toBeInTheDocument();
  });
});

// ── UnifiedRunWorkspace shell ───────────────────────────────────────

describe("UnifiedRunWorkspace", () => {
  it("renders the full component tree", () => {
    const model = makeModel();
    render(
      <ReactFlowProvider>
        <UnifiedRunWorkspace model={model} />
      </ReactFlowProvider>,
    );

    // Shell root
    expect(screen.getByTestId("unified-run-workspace")).toBeInTheDocument();

    // Sub-components
    expect(screen.getByTestId("workspace-header")).toBeInTheDocument();
    expect(screen.getByTestId("scenario-run-rail")).toBeInTheDocument();
    expect(screen.getByTestId("run-hierarchy")).toBeInTheDocument();
    expect(screen.getByTestId("runtime-graph-canvas")).toBeInTheDocument();
    expect(screen.getByTestId("node-inspector")).toBeInTheDocument();
    expect(screen.getByTestId("nextflow-panel")).toBeInTheDocument();
    expect(screen.getByTestId("runtime-player")).toBeInTheDocument();
  });

  it("hierarchy and dependency graph are distinct regions", () => {
    const model = makeModel();
    render(
      <ReactFlowProvider>
        <UnifiedRunWorkspace model={model} />
      </ReactFlowProvider>,
    );
    // Left panel has hierarchy, center has canvas (dependency graph)
    const left = screen.getByTestId("workspace-left");
    const center = screen.getByTestId("workspace-center");
    expect(left).toHaveTextContent("Hierarchy");
    expect(center).toHaveTextContent("Layout");
  });

  it("renders UNAVAILABLE for missing hierarchy (fail-closed)", () => {
    const model = makeModel({ hierarchy: null });
    render(
      <ReactFlowProvider>
        <UnifiedRunWorkspace model={model} />
      </ReactFlowProvider>,
    );
    const hierarchy = screen.getByTestId("run-hierarchy");
    expect(hierarchy).toHaveTextContent("UNAVAILABLE");
  });
});