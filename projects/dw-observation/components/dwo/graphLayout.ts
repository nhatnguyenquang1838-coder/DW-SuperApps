export type GraphDirection = "LR" | "TD";
export type GraphForm = "stack" | "grid";
export interface RuntimeGraphLayoutInput { id: string; gateId?: string | null; title?: string; purpose?: string | null }
export interface GraphRect { x: number; y: number; width: number; height: number }
export interface RuntimeGraphLayoutOptions { direction: GraphDirection; form: GraphForm; grouped: boolean }
export interface RuntimeGraphLayout { nodes: Record<string, GraphRect>; groups: Array<{ id: string; x: number; y: number; width: number; height: number; nodeIds: string[] }> }

const CARD_W = 288;
const CARD_GAP = 32;
const GROUP_PAD = 16;
const GROUP_HEAD = 56;
const GROUP_GAP = 40;

export function estimateRuntimeCardHeight(node: RuntimeGraphLayoutInput): number {
  const titleLines = Math.max(1, Math.ceil((node.title?.length ?? 1) / 34));
  const purposeLines = Math.ceil((node.purpose?.length ?? 0) / 42);
  return Math.max(184, 184 + Math.max(0, titleLines - 1) * 22 + purposeLines * 20);
}

export function computeRuntimeGraphLayout(nodes: RuntimeGraphLayoutInput[], options: RuntimeGraphLayoutOptions): RuntimeGraphLayout {
  const groupsMap = new Map<string, RuntimeGraphLayoutInput[]>();
  for (const node of nodes) {
    const key = node.gateId || "ungated";
    groupsMap.set(key, [...(groupsMap.get(key) ?? []), node]);
  }
  const entries = [...groupsMap.entries()];
  const nodeRects: Record<string, GraphRect> = {};
  const groupRects: RuntimeGraphLayout["groups"] = [];

  if (!options.grouped) {
    const cols = options.form === "stack" ? 1 : Math.max(1, Math.ceil(Math.sqrt(nodes.length)));
    const gridStepY = Math.max(...nodes.map(estimateRuntimeCardHeight), 184) + CARD_GAP;
    let stackY = 0;
    nodes.forEach((node, i) => {
      const col = i % cols;
      const row = Math.floor(i / cols);
      const height = estimateRuntimeCardHeight(node);
      let x: number;
      let y: number;
      if (options.form === "stack") {
        x = options.direction === "LR" ? i * (CARD_W + CARD_GAP) : 0;
        y = options.direction === "LR" ? 0 : stackY;
        stackY += height + CARD_GAP;
      } else {
        x = options.direction === "LR" ? col * (CARD_W + CARD_GAP) : row * (CARD_W + CARD_GAP);
        y = options.direction === "LR" ? row * gridStepY : col * gridStepY;
      }
      nodeRects[node.id] = { x, y, width: CARD_W, height };
    });
    return { nodes: nodeRects, groups: [] };
  }

  const grouped = entries.map(([id, members]) => {
    const cols = options.form === "stack" ? 1 : Math.max(1, Math.ceil(Math.sqrt(members.length)));
    const cards = members.map(node => ({ node, height: estimateRuntimeCardHeight(node) }));
    const rows = Math.ceil(cards.length / cols);
    const rowHeights = Array.from({ length: rows }, (_, row) => Math.max(...cards.slice(row * cols, (row + 1) * cols).map(card => card.height)));
    const width = GROUP_PAD * 2 + cols * CARD_W + (cols - 1) * CARD_GAP;
    const height = GROUP_HEAD + GROUP_PAD + rowHeights.reduce((a, b) => a + b, 0) + Math.max(0, rows - 1) * CARD_GAP + GROUP_PAD;
    return { id, members, cols, rowHeights, width, height, span: options.direction === "LR" ? width : height };
  });
  const stack = options.form === "stack";
  const laneCols = stack ? Math.max(1, grouped.length) : Math.max(1, Math.ceil(Math.sqrt(grouped.length)));
  const laneRowHeights: number[] = [];
  grouped.forEach((group, i) => {
    const col = i % laneCols;
    const row = Math.floor(i / laneCols);
    laneRowHeights[row] = Math.max(laneRowHeights[row] ?? 0, group.height);
    const x = options.direction === "LR" ? col * (Math.max(...grouped.map(item => item.width)) + GROUP_GAP) : row * (Math.max(...grouped.map(item => item.width)) + GROUP_GAP);
    const y = options.direction === "LR" ? row * (Math.max(...grouped.map(item => item.height)) + GROUP_GAP) : col * (Math.max(...grouped.map(item => item.height)) + GROUP_GAP);
    groupRects.push({ id: group.id, x, y, width: group.width, height: group.height, nodeIds: group.members.map(member => member.id) });
    group.members.forEach((node, j) => {
      const colIn = j % group.cols;
      const rowIn = Math.floor(j / group.cols);
      const priorHeight = group.rowHeights.slice(0, rowIn).reduce((a, b) => a + b, 0) + rowIn * CARD_GAP;
      nodeRects[node.id] = { x: x + GROUP_PAD + colIn * (CARD_W + CARD_GAP), y: y + GROUP_HEAD + GROUP_PAD + priorHeight, width: CARD_W, height: estimateRuntimeCardHeight(node) };
    });
  });
  return { nodes: nodeRects, groups: groupRects };
}
