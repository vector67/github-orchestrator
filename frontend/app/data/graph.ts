export interface GraphNode {
  id: string;
  lane: string;
  parents: string[];
  span?: number;
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
  parent: number;
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
  column: number;
  widest: number;
  width: number;
  height: number;
}

export interface Spacing {
  left: number;
  top: number;
  column: number;
  most: number;
  row: number;
  right: number;
  bottom: number;
}

export const SPACING: Spacing = {
  left: 24,
  top: 32,
  column: 56,
  most: 112,
  row: 48,
  right: 72,
  bottom: 48,
};

function columnsOf(nodes: GraphNode[]): Map<string, number> {
  const columns = new Map<string, number>();
  const ends = new Map<string, number>();
  const lastInLane = new Map<string, number>();
  for (const node of nodes) {
    const after = [
      ...node.parents.map((parent) => ends.get(parent)),
      lastInLane.get(node.lane),
    ].filter((one): one is number => one !== undefined);
    const column = after.length ? Math.max(...after) + 1 : 0;
    const end = column + (node.span ?? 1) - 1;
    columns.set(node.id, (column + end) / 2);
    ends.set(node.id, end);
    lastInLane.set(node.lane, end);
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
  across = 0,
): GraphLayout {
  const columns = columnsOf(nodes);
  const widest = Math.max(0, ...columns.values());
  const fitted = widest
    ? (across - spacing.left - spacing.right) / widest
    : spacing.column;
  const column = Math.min(Math.max(fitted, spacing.column), spacing.most);
  const placed = new Map<string, Placed>();
  for (const node of nodes) {
    const at = columns.get(node.id)!;
    const row = lanes.indexOf(node.lane);
    placed.set(node.id, {
      ...node,
      column: at,
      row,
      x: spacing.left + at * column,
      y: spacing.top + row * spacing.row,
    });
  }
  const edges = [...placed.values()].flatMap((to) =>
    to.parents.flatMap((parent, index) => {
      const from = placed.get(parent);
      if (!from) return [];
      return [
        {
          from: from.id,
          to: to.id,
          lane: to.lane,
          parent: index,
          crossing: from.row !== to.row,
          path: edgePath(from, to),
        },
      ];
    }),
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
  return {
    nodes: placed,
    edges,
    lanes: lines,
    column,
    widest,
    width:
      column === fitted
        ? across
        : spacing.left + widest * column + spacing.right,
    height: spacing.top + (lanes.length - 1) * spacing.row + spacing.bottom,
  };
}
