import type { GateId, LoginEpicRun, RuntimeNode } from "@/lib/loginEpicRuntimeGraph";

/** Display direction for the run-level graph. */
export type DisplayDir = "LR" | "TD";
/** Display form for nodes inside a gate (fanout styles). */
export type DisplayForm = "stack" | "grid";
export interface LayoutOpts {
  dir: DisplayDir;
  form: DisplayForm;
  /** Group nodes inside a gate by their `family`. */
  group: boolean;
}

export interface LayoutNode {
  id: string;
  gateId: GateId;
  family: string;
  boundary: string;
  x: number;
  y: number;
  w: number;
  h: number;
}
export interface LayoutGate {
  id: GateId;
  boundary: string;
  x: number;
  y: number;
  w: number;
  h: number;
  headerH: number;
  /** family sub-groups (for grouping display) */
  families: { family: string; x: number; y: number; w: number; h: number }[];
}
export interface LayoutEdge {
  id: string;
  source: string;
  target: string;
  kind: "route" | "fanout";
}
export interface RunLayout {
  nodes: LayoutNode[];
  gates: LayoutGate[];
  edges: LayoutEdge[];
  width: number;
  height: number;
}

const NODE_W = 232;
const NODE_H = 108;
const GAP = 16;
const PAD = 14;
const HEADER_H = 96;
const GATE_GAP = 130;
const MARGIN = 40;

function familyOrder(gate: { nodes: RuntimeNode[] }): string[] {
  const seen: string[] = [];
  for (const n of gate.nodes) if (!seen.includes(n.family)) seen.push(n.family);
  return seen;
}

/**
 * Compute a deterministic run-level layout. Two directions (LR: gates flow
 * left→right; TD: gates flow top→down), two fanout forms (stack: single
 * column/row; grid: wrapped columns/rows), and optional family grouping.
 * Gate boxes render as a full-width header banner + body so node cards never
 * overlap the gate info. Pure function of (run, opts).
 */
export function computeRunLayout(run: LoginEpicRun, opts: LayoutOpts): RunLayout {
  const nodes: LayoutNode[] = [];
  const gates: LayoutGate[] = [];
  const { dir, form, group } = opts;

  let maxX = 0;
  let maxY = 0;

  run.gates.forEach((gate, gi) => {
    const gx = MARGIN + (dir === "LR" ? gi * (0) : 0);
    const gy = MARGIN + (dir === "TD" ? gi * (0) : 0);
    const boundary = gate.nodes[0]?.boundary ?? "unknown";
    const fams = familyOrder(gate);

    // ---- layout nodes inside the gate ----
    const placed: { n: RuntimeNode; x: number; y: number }[] = [];
    let bodyW = 0;
    let bodyH = 0;

    if (group) {
      // Each family becomes a sub-column (LR) / sub-row (TD) band, laid out in
      // a grid. Compute the full grid extent so the gate box wraps ALL families.
      const colW = NODE_W + GAP;
      const rowH = NODE_H + GAP;
      const famCount = fams.length;
      const maxInFam = Math.max(1, ...fams.map((f) => gate.nodes.filter((n) => n.family === f).length));
      fams.forEach((fam, fi) => {
        const famNodes = gate.nodes.filter((n) => n.family === fam);
        famNodes.forEach((n, ni) => {
          const x = dir === "LR" ? fi * colW : ni * colW;
          const y = dir === "LR" ? ni * rowH : fi * rowH;
          placed.push({ n, x, y });
        });
      });
      // grid extent: (famCount columns) x (maxInFam rows) for LR; swapped for TD
      bodyW = (dir === "LR" ? famCount : maxInFam) * colW;
      bodyH = (dir === "LR" ? maxInFam : famCount) * rowH;
    } else {
      const cols = form === "grid" ? Math.max(1, Math.ceil(Math.sqrt(gate.nodes.length))) : 1;
      const rows = Math.ceil(gate.nodes.length / cols);
      gate.nodes.forEach((n, ni) => {
        const col = ni % cols;
        const row = Math.floor(ni / cols);
        const x = dir === "LR" ? col * (NODE_W + GAP) : row * (NODE_W + GAP);
        const y = dir === "LR" ? row * (NODE_H + GAP) : col * (NODE_H + GAP);
        placed.push({ n, x, y });
      });
      bodyW = (dir === "LR" ? cols : rows) * (NODE_W + GAP);
      bodyH = (dir === "LR" ? rows : cols) * (NODE_H + GAP);
    }

    // gate box size
    const gw = PAD * 2 + bodyW;
    const gh = HEADER_H + PAD + bodyH + PAD;

    // gate position along the main axis
    const gPos = gi * (dir === "LR" ? gw + GATE_GAP : gh + GATE_GAP);
    const gxx = dir === "LR" ? MARGIN + gPos : MARGIN;
    const gyy = dir === "TD" ? MARGIN + gPos : MARGIN;

    // emit nodes (offset into gate box)
    placed.forEach((p) => {
      const nx = gxx + PAD + p.x;
      const ny = gyy + HEADER_H + PAD + p.y;
      nodes.push({
        id: p.n.id,
        gateId: gate.id,
        family: p.n.family,
        boundary: p.n.boundary,
        x: nx,
        y: ny,
        w: NODE_W,
        h: NODE_H,
      });
      maxX = Math.max(maxX, nx + NODE_W);
      maxY = Math.max(maxY, ny + NODE_H);
    });

    // family bands (for grouping) — each band wraps exactly its family's grid cell
    const colW = NODE_W + GAP;
    const rowH = NODE_H + GAP;
    const famBands = group
      ? fams.map((fam, fi) => {
          const famNodes = gate.nodes.filter((n) => n.family === fam);
          const fw = dir === "LR" ? NODE_W : famNodes.length * colW - GAP;
          const fh = dir === "LR" ? famNodes.length * rowH - GAP : NODE_H;
          return {
            family: fam,
            x: gxx + PAD + (dir === "LR" ? fi * colW : 0),
            y: gyy + HEADER_H + PAD + (dir === "LR" ? 0 : fi * rowH),
            w: fw,
            h: fh,
          };
        })
      : [];

    gates.push({ id: gate.id, boundary, x: gxx, y: gyy, w: gw, h: gh, headerH: HEADER_H, families: famBands });
  });

  // ---- edges ----
  const edges: LayoutEdge[] = [];
  // route spine (linear across gates)
  run.route.forEach((step, i) => {
    if (i === 0) return;
    edges.push({ id: `route-${i}`, source: run.route[i - 1].node_id, target: step.node_id, kind: "route" });
  });
  // fanout: a SINGLE representative edge from the last node of gate gi to the
  // first node of gate gi+1 (shows the gate→gate dependency without the
  // bipartite tangle that overlapped node cards when group/fanout was on).
  run.gates.forEach((gate, gi) => {
    if (gi === run.gates.length - 1) return;
    const next = run.gates[gi + 1];
    const a = gate.nodes[gate.nodes.length - 1];
    const b = next.nodes[0];
    if (a && b) edges.push({ id: `fan-${a.id}->${b.id}`, source: a.id, target: b.id, kind: "fanout" });
  });

  return { nodes, gates, edges, width: maxX + MARGIN, height: maxY + MARGIN };
}
