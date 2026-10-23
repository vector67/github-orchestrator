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
  at: number;
  from: number;
  to: number;
}

export interface GraphLayout {
  nodes: Map<string, Placed>;
  edges: GraphEdge[];
  lanes: LaneLine[];
  column: number;
  widest: number;
  vertical: boolean;
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

function edgePath(from: Placed, to: Placed, vertical: boolean): string {
  if (vertical ? from.x === to.x : from.y === to.y)
    return `M ${from.x} ${from.y} L ${to.x} ${to.y}`;
  if (vertical) {
    const bend = (from.y + to.y) / 2;
    return `M ${from.x} ${from.y} C ${from.x} ${bend}, ${to.x} ${bend}, ${to.x} ${to.y}`;
  }
  const bend = (from.x + to.x) / 2;
  return `M ${from.x} ${from.y} C ${bend} ${from.y}, ${bend} ${to.y}, ${to.x} ${to.y}`;
}

function ranksOf(
  lanes: string[],
  nodes: GraphNode[],
  columns: Map<string, number>,
): Map<string, number> {
  const start = (node: GraphNode) =>
    columns.get(node.id)! - ((node.span ?? 1) - 1) / 2;
  return new Map(
    [...nodes]
      .sort(
        (one, other) =>
          start(one) - start(other) ||
          lanes.indexOf(one.lane) - lanes.indexOf(other.lane),
      )
      .map((node, rank) => [node.id, rank]),
  );
}

export function layout(
  lanes: string[],
  nodes: GraphNode[],
  spacing: Spacing = SPACING,
  across = 0,
  vertical = false,
): GraphLayout {
  const columns = vertical
    ? ranksOf(lanes, nodes, columnsOf(nodes))
    : columnsOf(nodes);
  const widest = Math.max(0, ...columns.values());
  const fitted = widest
    ? (across - spacing.left - spacing.right) / widest
    : spacing.column;
  const column = vertical
    ? spacing.column
    : Math.min(Math.max(fitted, spacing.column), spacing.most);
  const along = (at: number) =>
    (vertical ? spacing.top : spacing.left) + at * column;
  const beside = (row: number) =>
    (vertical ? spacing.left : spacing.top) + row * spacing.row;
  const placed = new Map<string, Placed>();
  for (const node of nodes) {
    const at = columns.get(node.id)!;
    const row = lanes.indexOf(node.lane);
    placed.set(node.id, {
      ...node,
      column: at,
      row,
      x: vertical ? beside(row) : along(at),
      y: vertical ? along(at) : beside(row),
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
          path: edgePath(from, to, vertical),
        },
      ];
    }),
  );
  const lines = lanes.flatMap((lane) => {
    const ats = [...placed.values()]
      .filter((one) => one.lane === lane)
      .map((one) => (vertical ? one.y : one.x));
    if (!ats.length) return [];
    return [
      {
        lane,
        at: beside(lanes.indexOf(lane)),
        from: Math.min(...ats),
        to: Math.max(...ats),
      },
    ];
  });
  const lengthwise =
    along(widest) + (vertical ? spacing.bottom : spacing.right);
  const crosswise =
    beside(lanes.length - 1) + (vertical ? spacing.right : spacing.bottom);
  return {
    nodes: placed,
    edges,
    lanes: lines,
    column,
    widest,
    vertical,
    width: vertical
      ? Math.max(across, crosswise)
      : column === fitted
        ? across
        : lengthwise,
    height: vertical ? lengthwise : crosswise,
  };
}
