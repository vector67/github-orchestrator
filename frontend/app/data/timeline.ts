import type { PullRequestCommits } from 'frontend/data/api';
import {
  layout,
  SPACING,
  type GraphNode,
  type Placed,
} from 'frontend/data/graph';

const SHORT = 7;
const BASE_LANE = 'base';
const STACK_LANE = 'stack';
const PR_LANE = 'pr';
const BAND_REACH = 12;
const SHA_DROP = 20;
const FLAG_DROP = 38;
const BOX_RISE = 18;
const LABEL_GAP = 20;
const DIAMOND = 8;

export interface Picked {
  from: string;
  to: string;
}

export type PresetName = 'all' | 'since-review' | 'this-commit';

export interface Preset {
  name: PresetName;
  label: string;
  available: boolean;
  active: boolean;
  picks: Picked | null;
}

export type DotStyle = 'base' | 'stack' | 'read' | 'unread';

export type DotShape = 'dot' | 'diamond';

export interface TimelineDot {
  sha: string;
  short: string;
  title: string;
  lane: string;
  style: DotStyle;
  shape: DotShape;
  path: string;
  x: number;
  y: number;
  shaY: number;
  pickable: boolean;
  inRange: boolean;
}

export interface TimelineLabel {
  kind: 'main' | 'stack' | 'head';
  text: string;
  opens: string | null;
  at: string;
  x: number;
  y: number;
}

export interface TimelineLane {
  lane: string;
  y: number;
  from: number;
  to: number;
}

export interface TimelineBand {
  x: number;
  y: number;
  width: number;
  height: number;
  middle: number;
  fromX: number;
  toX: number;
}

export interface TimelineFlag {
  x: number;
  top: number;
  bottom: number;
  textY: number;
  text: string;
}

export interface SinceFork {
  x: number;
  y: number;
  width: number;
  height: number;
  textY: number;
  text: string;
}

export interface TimelineHeader {
  count: string;
  branch: string;
  base: string;
  relation: string;
  fork: string;
  tip: string | null;
  behind: number;
}

export type CurveKind = 'fork' | 'merge';

export interface Timeline {
  width: number;
  height: number;
  lanes: TimelineLane[];
  curves: { path: string; lane: string; kind: CurveKind }[];
  dots: TimelineDot[];
  labels: TimelineLabel[];
  current: { sha: string; x: number; y: number } | null;
  band: TimelineBand;
  flag: TimelineFlag | null;
  since: SinceFork | null;
  header: TimelineHeader;
  presets: Preset[];
  order: string[];
  showing: Picked;
}

export interface TimelineInput {
  history: PullRequestCommits;
  read: Set<string>;
  branch: string | null;
  base: string | null;
  reviewedSha: string | null;
  reviewedAt: string | null;
  current: string | null;
  picked: Picked | null;
  hidden: boolean;
  repo: string;
  basePr: number | null;
}

export function dayOf(at: string): string {
  return new Date(at).toLocaleDateString('en-GB', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  });
}

function plural(count: number, one: string): string {
  return `${count} ${one}${count === 1 ? '' : 's'}`;
}

function sameRange(one: Picked, other: Picked | null): boolean {
  return one.from === other?.from && one.to === other.to;
}

function presetsOf(
  order: string[],
  input: TimelineInput,
  showing: Picked,
): Preset[] {
  const all = { from: order[0]!, to: order.at(-1)! };
  const reviewedAt = order.indexOf(input.reviewedSha ?? '');
  const sinceReview =
    reviewedAt >= 0 && reviewedAt < order.length - 1
      ? { from: order[reviewedAt + 1]!, to: all.to }
      : null;
  const { current, hidden } = input;
  return [
    {
      name: 'all',
      label: 'All',
      available: true,
      active: sameRange(all, showing),
      picks: hidden ? null : all,
    },
    {
      name: 'since-review',
      label: 'Since my review',
      available: sinceReview !== null,
      active: sinceReview !== null && sameRange(sinceReview, showing),
      picks: sinceReview,
    },
    {
      name: 'this-commit',
      label: 'This commit',
      available: current !== null,
      active: showing.from === showing.to && (!hidden || input.picked !== null),
      picks: hidden && current ? { from: current, to: current } : null,
    },
  ];
}

function outsideOf(history: PullRequestCommits): string[] {
  const under = history.stack?.commits ?? [];
  const own = new Set(
    [...under, ...history.commits, ...history.base_commits].map(
      (one) => one.sha,
    ),
  );
  return [
    ...new Set(
      [
        ...[...under, ...history.commits].flatMap((one) => one.parents),
        history.fork,
      ].filter((parent) => !own.has(parent)),
    ),
  ];
}

function nodesOf(history: PullRequestCommits): GraphNode[] {
  const onBase = history.stack ? STACK_LANE : BASE_LANE;
  return [
    ...outsideOf(history).map((id) => ({
      id,
      lane: BASE_LANE,
      parents: [],
    })),
    ...(history.stack?.commits ?? []).map((one) => ({
      id: one.sha,
      lane: STACK_LANE,
      parents: one.parents,
    })),
    ...history.base_commits.map((one) => ({
      id: one.sha,
      lane: onBase,
      parents: one.parents,
    })),
    ...history.commits.map((one) => ({
      id: one.sha,
      lane: PR_LANE,
      parents: one.parents,
    })),
  ];
}

function bandOf(from: Placed, to: Placed): TimelineBand {
  return {
    x: from.x - BAND_REACH,
    y: from.y - BAND_REACH,
    width: to.x - from.x + 2 * BAND_REACH,
    height: 2 * BAND_REACH,
    middle: from.y,
    fromX: from.x - BAND_REACH,
    toX: to.x + BAND_REACH,
  };
}

function flagOf(
  order: string[],
  input: TimelineInput,
  placed: Map<string, Placed>,
  column: number,
): TimelineFlag | null {
  const reviewed = placed.get(input.reviewedSha ?? '');
  if (!reviewed || !input.reviewedAt || reviewed.lane !== PR_LANE) return null;
  const next = placed.get(order[order.indexOf(reviewed.id) + 1] ?? '');
  const x = next ? (reviewed.x + next.x) / 2 : reviewed.x + column / 2;
  return {
    x,
    top: reviewed.y - BAND_REACH,
    bottom: reviewed.y + FLAG_DROP - BAND_REACH,
    textY: reviewed.y + FLAG_DROP,
    text: `you reviewed ${dayOf(input.reviewedAt)}`,
  };
}

function sinceOf(
  history: PullRequestCommits,
  placed: Map<string, Placed>,
  base: string,
): SinceFork | null {
  const first = placed.get(history.base_commits[0]?.sha ?? '');
  const last = placed.get(history.base_commits.at(-1)?.sha ?? '');
  if (!first || !last) return null;
  return {
    x: first.x - BAND_REACH,
    y: first.y - BAND_REACH,
    width: last.x - first.x + 2 * BAND_REACH,
    height: 2 * BAND_REACH,
    textY: first.y - BOX_RISE,
    text: `${plural(history.behind, 'commit')} on ${base} since the fork`,
  };
}

function diamondAt(x: number, y: number): string {
  return `M ${x} ${y - DIAMOND} L ${x + DIAMOND} ${y} L ${x} ${y + DIAMOND} L ${x - DIAMOND} ${y} Z`;
}

function styleOf(node: Placed, read: Set<string>): DotStyle {
  if (node.lane === BASE_LANE) return 'base';
  if (node.lane === STACK_LANE) return 'stack';
  return read.has(node.id) ? 'read' : 'unread';
}

function lastOn(lane: string, placed: Map<string, Placed>): Placed | null {
  return [...placed.values()]
    .filter((one) => one.lane === lane)
    .reduce<Placed | null>(
      (last, one) => (last && last.x >= one.x ? last : one),
      null,
    );
}

function relationOf(
  input: TimelineInput,
  base: string,
  merges: number,
): string {
  const { stack } = input.history;
  if (stack) {
    const named = input.basePr ? `#${input.basePr} ${base}` : base;
    return `base is ${named}, which is based on ${stack.branch}`;
  }
  return merges ? `last synced with ${base} at` : `forked from ${base} at`;
}

export function timelineBuilt(input: TimelineInput): Timeline | null {
  const { history, read } = input;
  const order = history.commits.map((one) => one.sha);
  if (!order.length) return null;
  const stack = history.stack;
  const graph = layout(
    stack ? [BASE_LANE, STACK_LANE, PR_LANE] : [BASE_LANE, PR_LANE],
    nodesOf(history),
  );
  const base = input.base ?? 'main';
  const showing =
    input.picked ??
    (input.hidden || !input.current
      ? { from: order[0]!, to: order.at(-1)! }
      : { from: input.current, to: input.current });
  const from = order.indexOf(showing.from);
  const to = order.indexOf(showing.to);
  const subjects = new Map(
    [
      ...(stack?.commits ?? []),
      ...history.base_commits,
      ...history.commits,
    ].map((one) => [one.sha, one.subject]),
  );
  const merges = new Set(
    history.commits
      .filter((one) => one.parents.length > 1)
      .map((one) => one.sha),
  );
  const dots = [...graph.nodes.values()].map((node) => {
    const at = order.indexOf(node.id);
    const short = node.id.slice(0, SHORT);
    const subject = subjects.get(node.id);
    const shape: DotShape = merges.has(node.id) ? 'diamond' : 'dot';
    return {
      sha: node.id,
      short,
      title: subject ? `${short} ${subject}` : short,
      lane: node.lane,
      style: styleOf(node, read),
      shape,
      path: shape === 'diamond' ? diamondAt(node.x, node.y) : '',
      x: node.x,
      y: node.y,
      shaY: node.y + SHA_DROP,
      pickable: at >= 0,
      inRange: at >= from && at <= to && at >= 0,
    };
  });
  const main = lastOn(BASE_LANE, graph.nodes)!;
  const under = lastOn(STACK_LANE, graph.nodes);
  const head = graph.nodes.get(order.at(-1)!)!;
  const label = (
    kind: TimelineLabel['kind'],
    text: string,
    at: Placed,
    opens: string | null = null,
  ): TimelineLabel => ({
    kind,
    text,
    opens,
    at: at.id,
    x: at.x + LABEL_GAP,
    y: at.y,
  });
  const ringed = input.hidden
    ? undefined
    : graph.nodes.get(input.current ?? '');
  return {
    width: graph.width,
    height: graph.height,
    lanes: graph.lanes.map((one) =>
      one.lane === BASE_LANE ? { ...one, from: 0 } : one,
    ),
    curves: graph.edges
      .filter((one) => one.crossing)
      .map((one) => ({
        path: one.path,
        lane: one.lane,
        kind: one.parent > 0 ? ('merge' as const) : ('fork' as const),
      })),
    dots,
    labels: [
      label('main', stack?.branch ?? base, main),
      ...(under
        ? [
            label(
              'stack',
              input.basePr ? `#${input.basePr} ${base}` : base,
              under,
              input.basePr ? `/pr/${input.repo}/${input.basePr}/diff` : null,
            ),
          ]
        : []),
      label('head', 'head', head),
    ],
    current: ringed ? { sha: ringed.id, x: ringed.x, y: ringed.y } : null,
    band: bandOf(
      graph.nodes.get(showing.from) ?? head,
      graph.nodes.get(showing.to) ?? head,
    ),
    flag: flagOf(order, input, graph.nodes, SPACING.column),
    since: sinceOf(history, graph.nodes, base),
    header: {
      count: merges.size
        ? `${plural(order.length - merges.size, 'commit')} and ${plural(merges.size, 'merge')}`
        : plural(order.length, 'commit'),
      branch: input.branch ?? 'this branch',
      base,
      relation: relationOf(input, base, merges.size),
      fork: stack ? '' : history.fork.slice(0, SHORT),
      tip: stack || history.behind ? null : `${base}'s tip`,
      behind: history.behind,
    },
    presets: presetsOf(order, input, showing),
    order,
    showing,
  };
}

export function ordered(order: string[], one: string, other: string): Picked {
  return order.indexOf(one) <= order.indexOf(other)
    ? { from: one, to: other }
    : { from: other, to: one };
}
