export interface GraphNode {
  id: string;
  lane: string;
  parents: string[];
}

export interface Placed extends GraphNode {
  column: number;
  row: number;
  x: number;
  y: number;
}

export interface GraphEdge {
  from: string;
  to: string;
  lane: string;
  crossing: boolean;
  path: string;
}

export interface LaneLine {
  lane: string;
  y: number;
  from: number;
  to: number;
}

export interface GraphLayout {
  nodes: Map<string, Placed>;
  edges: GraphEdge[];
  lanes: LaneLine[];
  width: number;
  height: number;
}

export interface Spacing {
  left: number;
  top: number;
  column: number;
  row: number;
  right: number;
  bottom: number;
}

export const SPACING: Spacing = {
  left: 24,
  top: 32,
  column: 56,
  row: 48,
  right: 72,
  bottom: 48,
};

function columnsOf(nodes: GraphNode[]): Map<string, number> {
  const columns = new Map<string, number>();
  const lastInLane = new Map<string, number>();
  for (const node of nodes) {
    const after = [
      ...node.parents.map((parent) => columns.get(parent)),
      lastInLane.get(node.lane),
    ].filter((one): one is number => one !== undefined);
    const column = after.length ? Math.max(...after) + 1 : 0;
    columns.set(node.id, column);
    lastInLane.set(node.lane, column);
  }
  return columns;
}

function edgePath(from: Placed, to: Placed): string {
  if (from.y === to.y) return `M ${from.x} ${from.y} L ${to.x} ${to.y}`;
  const bend = (from.x + to.x) / 2;
  return `M ${from.x} ${from.y} C ${bend} ${from.y}, ${bend} ${to.y}, ${to.x} ${to.y}`;
}

export function layout(
  lanes: string[],
  nodes: GraphNode[],
  spacing: Spacing = SPACING,
): GraphLayout {
  const columns = columnsOf(nodes);
  const placed = new Map<string, Placed>();
  for (const node of nodes) {
    const column = columns.get(node.id)!;
    const row = lanes.indexOf(node.lane);
    placed.set(node.id, {
      ...node,
      column,
      row,
      x: spacing.left + column * spacing.column,
      y: spacing.top + row * spacing.row,
    });
  }
  const edges = [...placed.values()].flatMap((to) =>
    to.parents
      .map((parent) => placed.get(parent))
      .filter((from): from is Placed => from !== undefined)
      .map((from) => ({
        from: from.id,
        to: to.id,
        lane: to.lane,
        crossing: from.row !== to.row,
        path: edgePath(from, to),
      })),
  );
  const lines = lanes.flatMap((lane) => {
    const xs = [...placed.values()]
      .filter((one) => one.lane === lane)
      .map((one) => one.x);
    if (!xs.length) return [];
    return [
      {
        lane,
        y: spacing.top + lanes.indexOf(lane) * spacing.row,
        from: Math.min(...xs),
        to: Math.max(...xs),
      },
    ];
  });
  const widest = Math.max(0, ...columns.values());
  return {
    nodes: placed,
    edges,
    lanes: lines,
    width: spacing.left + widest * spacing.column + spacing.right,
    height: spacing.top + (lanes.length - 1) * spacing.row + spacing.bottom,
  };
}
