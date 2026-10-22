import type { PullRequestCommit, PullRequestCommits } from 'frontend/data/api';
import {
  layout,
  SPACING,
  type GraphNode,
  type Placed,
  type Spacing,
} from 'frontend/data/graph';

const SHORT = 7;
const BASE_LANE = 'base';
const STACK_LANE = 'stack';
const PR_LANE = 'pr';
const GHOST_LANE = 'ghost';
const MATCHED_RISE = 14;
const OLD_FORK_SPAN = 2;
const BAND_REACH = 12;
const SHA_DROP = 20;
const DAY_DROP = 36;
const DAY_RISE = 14;
const DAY_GAP = 4;
const TICK = 7;
export const LONG = 20;
const TICKS: Spacing = { ...SPACING, column: 18 };
const FLAG_DROP = 38;
const BOX_RISE = 18;
const LABEL_GAP = 20;
const FLAG_RISE = 16;
const DIAMOND = 8;
const FAR = 20;
const KEPT = 2;
const RUN = 'run';
const RUN_SPAN = 2;
const RUN_REACH = 10;
const DATE_DROP = 28;
const DATE_RISE = 12;

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

export type DotStyle = 'base' | 'stack' | 'read' | 'unread' | 'ghost';

export type DotShape = 'dot' | 'diamond' | 'tick';

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
  pushed: boolean | null;
  showSha: boolean;
  date: string | null;
  dateY: number;
  dateAnchor: 'start' | 'middle';
  pickable: boolean;
  inRange: boolean;
  radius: number;
  matched: boolean;
  matchedY: number;
}

export interface TimelineDay {
  x: number;
  top: number;
  y: number;
  textX: number;
  text: string;
}

export interface Listed {
  short: string;
  subject: string;
}

export interface CollapsedRun {
  x: number;
  y: number;
  left: number;
  top: number;
  width: number;
  height: number;
  text: string;
  listed: Listed[];
}

export interface TimelineLabel {
  kind: 'main' | 'stack' | 'head' | 'origin' | 'local' | 'fork' | 'old-fork';
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
  dashed: boolean;
  unpushed: boolean;
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
  was: string | null;
  tip: string | null;
  main: string;
  behind: number;
}

export type CurveKind = 'fork' | 'merge' | 'ghost';

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
  collapsed: CollapsedRun | null;
  days: TimelineDay[];
  ghosts: string | null;
  header: TimelineHeader;
  presets: Preset[];
  order: string[];
  showing: Picked;
}

export interface TimelineInput {
  history: PullRequestCommits;
  read: Set<string>;
  matched: Set<string>;
  fresh: string[];
  branch: string | null;
  base: string | null;
  reviewedSha: string | null;
  reviewedAt: string | null;
  current: string | null;
  picked: Picked | null;
  hidden: boolean;
  repo: string;
  basePr: number | null;
  unpushed: Set<string>;
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
  const firstFresh = input.fresh[0];
  const sinceReview = input.history.reviewed
    ? firstFresh
      ? { from: firstFresh, to: all.to }
      : null
    : reviewedAt >= 0 && reviewedAt < order.length - 1
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

function keptOf(history: PullRequestCommits): {
  kept: PullRequestCommit[];
  run: PullRequestCommit[];
} {
  const sent = history.base_commits;
  if (history.behind <= FAR || sent.length <= KEPT)
    return { kept: sent, run: [] };
  return { kept: sent.slice(-KEPT), run: sent.slice(0, -KEPT) };
}

function baseNodesOf(history: PullRequestCommits, lane: string): GraphNode[] {
  const { kept, run } = keptOf(history);
  const nodes = kept.map((one) => ({
    id: one.sha,
    lane,
    parents: one.parents,
  }));
  if (!run.length) return nodes;
  return [
    { id: RUN, lane, parents: [history.fork], span: RUN_SPAN },
    ...nodes.map((one, index) => (index ? one : { ...one, parents: [RUN] })),
  ];
}

function collapsedOf(
  history: PullRequestCommits,
  placed: Map<string, Placed>,
  spacing: Spacing,
): CollapsedRun | null {
  const { run } = keptOf(history);
  const at = placed.get(RUN);
  if (!at || !run.length) return null;
  const hidden = history.behind - KEPT - run.length;
  const listed = run.map((one) => ({
    short: one.sha.slice(0, SHORT),
    subject: one.subject,
  }));
  if (hidden > 0)
    listed.splice(history.base_commits.length / 2, 0, {
      short: '',
      subject: `⋯ ${hidden} more`,
    });
  const width = Math.max(
    RUN_SPAN * spacing.column - 2 * RUN_REACH,
    SPACING.column,
  );
  return {
    x: at.x,
    y: at.y,
    left: at.x - width / 2,
    top: at.y - RUN_REACH,
    width,
    height: 2 * RUN_REACH,
    text: `⋯ ${plural(history.behind - KEPT, 'commit')}`,
    listed,
  };
}

function ghostsOf(history: PullRequestCommits): PullRequestCommit[] {
  const present = new Set(history.commits.map((one) => one.sha));
  return (history.reviewed?.commits ?? []).filter(
    (one) => !present.has(one.sha),
  );
}

function oldForkOf(history: PullRequestCommits): GraphNode[] {
  const fork = history.reviewed?.fork;
  if (!fork || !ghostsOf(history).length) return [];
  const known = [
    ...outsideOf(history),
    ...history.base_commits.map((one) => one.sha),
  ];
  if (known.includes(fork)) return [];
  return [{ id: fork, lane: BASE_LANE, parents: [], span: OLD_FORK_SPAN }];
}

function nodesOf(history: PullRequestCommits): GraphNode[] {
  const onBase = history.stack ? STACK_LANE : BASE_LANE;
  return [
    ...oldForkOf(history),
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
    ...baseNodesOf(history, onBase),
    ...history.commits.map((one) => ({
      id: one.sha,
      lane: PR_LANE,
      parents: one.parents,
    })),
    ...ghostsOf(history).map((one) => ({
      id: one.sha,
      lane: GHOST_LANE,
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
  if (!reviewed || !input.reviewedAt) return null;
  const sequence =
    reviewed.lane === PR_LANE
      ? order
      : reviewed.lane === GHOST_LANE
        ? ghostsOf(input.history).map((one) => one.sha)
        : [];
  if (!sequence.length) return null;
  const next = placed.get(sequence[sequence.indexOf(reviewed.id) + 1] ?? '');
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
  const first =
    placed.get(RUN) ?? placed.get(history.base_commits[0]?.sha ?? '');
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

function tickAt(x: number, y: number): string {
  return `M ${x} ${y - TICK} L ${x} ${y + TICK}`;
}

function daysOf(
  history: PullRequestCommits,
  placed: Map<string, Placed>,
): TimelineDay[] {
  return history.commits.flatMap((one, index) => {
    const text = dayOf(one.authored_at);
    const before = history.commits[index - 1];
    const at = placed.get(one.sha);
    if (!at || (before && dayOf(before.authored_at) === text)) return [];
    return [
      {
        x: at.x,
        top: at.y + DAY_RISE,
        y: at.y + DAY_DROP,
        textX: at.x + DAY_GAP,
        text,
      },
    ];
  });
}

function diamondAt(x: number, y: number): string {
  return `M ${x} ${y - DIAMOND} L ${x + DIAMOND} ${y} L ${x} ${y + DIAMOND} L ${x - DIAMOND} ${y} Z`;
}

function styleOf(node: Placed, read: Set<string>): DotStyle {
  if (node.lane === BASE_LANE) return 'base';
  if (node.lane === STACK_LANE) return 'stack';
  if (node.lane === GHOST_LANE) return 'ghost';
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
  if (merges) return `last synced with ${base} at`;
  return input.history.reviewed
    ? `now forked from ${base} at`
    : `forked from ${base} at`;
}

export function timelineBuilt(input: TimelineInput): Timeline | null {
  const { history, read } = input;
  const order = history.commits.map((one) => one.sha);
  if (!order.length) return null;
  const stack = history.stack;
  const long = order.length > LONG;
  const spacing = long ? TICKS : SPACING;
  const ghosts = ghostsOf(history);
  const oldFork = oldForkOf(history)[0];
  const graph = layout(
    [
      BASE_LANE,
      ...(stack ? [STACK_LANE] : []),
      PR_LANE,
      ...(ghosts.length ? [GHOST_LANE] : []),
    ],
    nodesOf(history),
    spacing,
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
      ...ghosts,
    ].map((one) => [one.sha, one.subject]),
  );
  const merges = new Set(
    history.commits
      .filter((one) => one.parents.length > 1)
      .map((one) => one.sha),
  );
  const folded = keptOf(history).run.length > 0;
  const dates = new Map(
    folded
      ? [
          [history.fork, history.fork_at],
          [history.base_tip, history.base_commits.at(-1)!.authored_at],
        ]
      : [],
  );
  const placed = [...graph.nodes.values()].filter((node) => node.id !== RUN);
  const dots = placed.map((node) => {
    const at = order.indexOf(node.id);
    const date = dates.get(node.id);
    const short = node.id.slice(0, SHORT);
    const subject = subjects.get(node.id);
    const shape: DotShape = merges.has(node.id)
      ? 'diamond'
      : long && at >= 0
        ? 'tick'
        : 'dot';
    return {
      sha: node.id,
      short,
      title: subject ? `${short} ${subject}` : short,
      lane: node.lane,
      style: styleOf(node, read),
      shape,
      path:
        shape === 'diamond'
          ? diamondAt(node.x, node.y)
          : shape === 'tick'
            ? tickAt(node.x, node.y)
            : '',
      x: node.x,
      y: node.y,
      shaY: node.y + SHA_DROP,
      showSha:
        at >= 0 &&
        (!long || [showing.from, showing.to, input.current].includes(node.id)),
      date: date ? dayOf(date) : null,
      dateY: node.id === history.fork ? node.y - DATE_RISE : node.y + DATE_DROP,
      dateAnchor:
        node.id === history.fork ? ('start' as const) : ('middle' as const),
      pushed: node.lane === PR_LANE ? !input.unpushed.has(node.id) : null,
      pickable: at >= 0,
      inRange: at >= from && at <= to && at >= 0,
      radius: at >= 0 || node.lane === GHOST_LANE ? 6 : 4,
      matched: input.matched.has(node.id),
      matchedY: node.y - MATCHED_RISE,
    };
  });
  const lastPushed = graph.nodes.get(
    order.findLast((sha) => !input.unpushed.has(sha)) ?? '',
  );
  const firstUnpushed = graph.nodes.get(
    order.find((sha) => input.unpushed.has(sha)) ?? '',
  );
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
    lanes: graph.lanes.flatMap((one) => {
      const plain = { ...one, dashed: false, unpushed: false };
      if (one.lane === BASE_LANE) return [{ ...plain, from: 0 }];
      if (one.lane === GHOST_LANE) return [{ ...plain, dashed: true }];
      if (one.lane !== PR_LANE || !firstUnpushed) return [plain];
      const split = lastPushed?.x ?? one.from;
      return [
        ...(lastPushed ? [{ ...plain, to: split }] : []),
        { ...plain, from: split, dashed: true, unpushed: true },
      ];
    }),
    curves: graph.edges
      .filter((one) => one.crossing)
      .map((one) => ({
        path: one.path,
        lane: one.lane,
        kind:
          one.lane === GHOST_LANE
            ? ('ghost' as const)
            : one.parent > 0
              ? ('merge' as const)
              : ('fork' as const),
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
      ...(firstUnpushed
        ? [
            {
              ...label('origin', 'origin', lastPushed ?? firstUnpushed),
              x: lastPushed
                ? (lastPushed.x + firstUnpushed.x) / 2
                : firstUnpushed.x,
              y: firstUnpushed.y - FLAG_RISE,
            },
            label('local', 'local', head),
          ]
        : [label('head', 'head', head)]),
      ...forkLabelsOf(graph.nodes, oldFork?.id, history.fork),
    ],
    current: ringed ? { sha: ringed.id, x: ringed.x, y: ringed.y } : null,
    band: bandOf(
      graph.nodes.get(showing.from) ?? head,
      graph.nodes.get(showing.to) ?? head,
    ),
    flag: flagOf(order, input, graph.nodes, spacing.column),
    since: sinceOf(history, graph.nodes, base),
    collapsed: collapsedOf(history, graph.nodes, spacing),
    days: long ? daysOf(history, graph.nodes) : [],
    ghosts: ghosts.length
      ? `your review saw ${ghosts.map((one) => one.sha.slice(0, SHORT)).join(' ')}, rewritten since`
      : null,
    header: {
      count: merges.size
        ? `${plural(order.length - merges.size, 'commit')} and ${plural(merges.size, 'merge')}`
        : plural(order.length, 'commit'),
      branch: input.branch ?? 'this branch',
      base,
      relation: relationOf(input, base, merges.size),
      fork: stack ? '' : history.fork.slice(0, SHORT),
      was: oldFork && !stack ? oldFork.id.slice(0, SHORT) : null,
      tip: stack || history.behind ? null : `${base}'s tip`,
      main: stack?.branch ?? base,
      behind: history.behind,
    },
    presets: presetsOf(order, input, showing),
    order,
    showing,
  };
}

function forkLabelsOf(
  placed: Map<string, Placed>,
  oldFork: string | undefined,
  fork: string,
): TimelineLabel[] {
  const was = placed.get(oldFork ?? '');
  const now = placed.get(fork);
  if (!was || !now) return [];
  const above = (
    kind: TimelineLabel['kind'],
    text: string,
    at: Placed,
  ): TimelineLabel => ({
    kind,
    text,
    opens: null,
    at: at.id,
    x: at.x,
    y: at.y - FLAG_RISE,
  });
  return [
    above('old-fork', 'was forked', was),
    above('fork', 'now forked', now),
  ];
}

export function ordered(order: string[], one: string, other: string): Picked {
  return order.indexOf(one) <= order.indexOf(other)
    ? { from: one, to: other }
    : { from: other, to: one };
}
