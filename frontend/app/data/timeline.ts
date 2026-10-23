import type { PullRequestCommit, PullRequestCommits } from 'frontend/data/api';
import {
  layout,
  SPACING,
  type GraphLayout,
  type GraphNode,
  type Placed,
  type Spacing,
} from 'frontend/data/graph';

const SHORT = 7;
const BASE_LANE = 'base';
const STACK_LANE = 'stack';
const PR_LANE = 'pr';
const GHOST_LANE = 'ghost';
const ORIGIN_LANE = 'origin';
const MATCHED_RISE = 14;
const OLD_FORK_SPAN = 2;
const BAND_REACH = 12;
const SHA_DROP = 20;
const DAY_DROP = 36;
const DAY_RISE = 14;
const DAY_GAP = 4;
const TICK = 7;
const DOT_ROOM = 40;
const TICK_ROOM = 10;
const DOTS: Spacing = { ...SPACING, column: DOT_ROOM, most: SPACING.most };
const TICKS: Spacing = { ...SPACING, column: TICK_ROOM, most: DOT_ROOM };
const EARLIER = 'earlier';
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
const DATE_RISE = 18;
const DATE_ROW = 14;
const RUN_GAP = 4;
const LABEL_CHAR = 7.5;
const LABEL_PAD = 6;
const LABEL_REACH = 10;

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

export type DotStyle =
  'base' | 'stack' | 'read' | 'unread' | 'ghost' | 'origin';

export type DotShape = 'dot' | 'diamond' | 'tick';

export type Drawn = 'dot' | 'tick' | 'fold';

export function drawnAs(columns: number, room: number): Drawn {
  if (!room || !columns) return 'dot';
  const each = room / columns;
  return each >= DOT_ROOM ? 'dot' : each >= TICK_ROOM ? 'tick' : 'fold';
}

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

export interface Pill {
  x: number;
  y: number;
  left: number;
  top: number;
  width: number;
  height: number;
  text: string;
}

export interface CollapsedRun extends Pill {
  listed: Listed[];
}

export interface TimelineLabel {
  kind: 'main' | 'stack' | 'head' | 'origin' | 'local' | 'fork' | 'old-fork';
  text: string;
  opens: string | null;
  at: string;
  x: number;
  y: number;
  box: LabelBox | null;
}

export interface LabelBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

function boxed(label: TimelineLabel): TimelineLabel {
  return {
    ...label,
    box: {
      x: label.x - LABEL_PAD,
      y: label.y - LABEL_REACH,
      width: label.text.length * LABEL_CHAR + 2 * LABEL_PAD,
      height: 2 * LABEL_REACH,
    },
  };
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
  diverged: DivergedHeader | null;
}

export interface DivergedHeader {
  here: number;
  other: string;
  from: string;
  chip: string;
}

export type CurveKind = 'fork' | 'merge' | 'ghost';

export interface TimelineKey {
  merge: boolean;
  tick: boolean;
  unpushed: boolean;
  origin: boolean;
}

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
  collapsed: CollapsedRun[];
  earlier: Pill | null;
  days: TimelineDay[];
  ghosts: string | null;
  header: TimelineHeader;
  presets: Preset[];
  key: TimelineKey;
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
  standing: Standing;
  across: number;
  unfolded: boolean;
}

export interface Standing {
  offOrigin: Set<string>;
  diverged: { here: number; there: PullRequestCommit[] } | null;
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

interface Fold {
  id: string;
  text: string;
  listed: Listed[];
}

type Stretch = { commit: PullRequestCommit } | { fold: Fold };

interface Sited {
  commit: PullRequestCommit;
  at: number;
}

function sitedOf(history: PullRequestCommits): Sited[] {
  const sent = history.base_commits;
  const skipped = history.behind - sent.length;
  return sent.map((commit, index) => ({
    commit,
    at: skipped && index >= sent.length / 2 ? index + skipped : index,
  }));
}

function listedOf(sited: Sited[], from: number, to: number): Listed[] {
  const inside = sited.filter((one) => one.at >= from && one.at <= to);
  const listed: Listed[] = [];
  let next = from;
  for (const one of [...inside, { commit: null, at: to + 1 }]) {
    if (one.at > next)
      listed.push({ short: '', subject: `⋯ ${one.at - next} more` });
    if (one.commit)
      listed.push({
        short: one.commit.sha.slice(0, SHORT),
        subject: one.commit.subject,
      });
    next = one.at + 1;
  }
  return listed;
}

function stretchesOf(history: PullRequestCommits): Stretch[] {
  const sited = sitedOf(history);
  if (history.behind <= FAR || sited.length <= KEPT)
    return sited.map(({ commit }) => ({ commit }));
  const drawn = [...history.base_forks, ...sited.slice(-KEPT)]
    .filter((one) => one.at < history.behind)
    .sort((one, other) => one.at - other.at)
    .filter((one, index, all) => one.at !== all[index - 1]?.at);
  const stretches: Stretch[] = [];
  let next = 0;
  for (const one of drawn) {
    if (one.at > next)
      stretches.push({
        fold: {
          id: `${RUN}-${next}`,
          text: `⋯ ${one.at - next}`,
          listed: listedOf(sited, next, one.at - 1),
        },
      });
    stretches.push({ commit: one.commit });
    next = one.at + 1;
  }
  const last = stretches.findLast((one) => 'fold' in one);
  if (last && 'fold' in last) last.fold.text = `${last.fold.text} more`;
  return stretches;
}

function foldsOf(history: PullRequestCommits): Fold[] {
  return stretchesOf(history).flatMap((one) =>
    'fold' in one ? [one.fold] : [],
  );
}

function spanOf(text: string, column: number): number {
  return Math.max(
    RUN_SPAN,
    Math.ceil(
      (text.length * LABEL_CHAR + 2 * LABEL_PAD + 2 * RUN_REACH) / column,
    ),
  );
}

function pillAt(at: Placed, column: number, text: string): Pill {
  const width = (at.span ?? RUN_SPAN) * column - 2 * RUN_REACH;
  return {
    x: at.x,
    y: at.y,
    left: at.x - width / 2,
    top: at.y - RUN_REACH,
    width,
    height: 2 * RUN_REACH,
    text,
  };
}

function earlierText(count: number): string {
  return `⋯ ${count} earlier`;
}

function baseNodesOf(
  history: PullRequestCommits,
  lane: string,
  column: number,
): GraphNode[] {
  const stretches = stretchesOf(history);
  if (!stretches.some((one) => 'fold' in one))
    return stretches.flatMap((one) =>
      'commit' in one
        ? [{ id: one.commit.sha, lane, parents: one.commit.parents }]
        : [],
    );
  let before = history.fork;
  return stretches.map((one) => {
    const node =
      'fold' in one
        ? {
            id: one.fold.id,
            lane,
            parents: [before],
            span: spanOf(one.fold.text, column),
          }
        : { id: one.commit.sha, lane, parents: [before] };
    before = node.id;
    return node;
  });
}

function collapsedOf(
  history: PullRequestCommits,
  placed: Map<string, Placed>,
  column: number,
): CollapsedRun[] {
  return foldsOf(history).flatMap((fold) => {
    const at = placed.get(fold.id);
    if (!at) return [];
    return [{ ...pillAt(at, column, fold.text), listed: fold.listed }];
  });
}

function forkCommitsOf(history: PullRequestCommits): PullRequestCommit[] {
  return history.base_forks.map((one) => one.commit);
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
    ...[...history.base_commits, ...forkCommitsOf(history)].map(
      (one) => one.sha,
    ),
  ];
  if (known.includes(fork)) return [];
  return [{ id: fork, lane: BASE_LANE, parents: [], span: OLD_FORK_SPAN }];
}

function originForkOf(
  history: PullRequestCommits,
  there: PullRequestCommit[],
): GraphNode[] {
  const known = new Set([
    ...outsideOf(history),
    ...[
      ...history.base_commits,
      ...forkCommitsOf(history),
      ...history.commits,
      ...there,
    ].map((one) => one.sha),
  ]);
  const fork = there[0]?.parents[0];
  if (!fork || known.has(fork)) return [];
  return [{ id: fork, lane: BASE_LANE, parents: [history.fork] }];
}

function nodesOf(
  history: PullRequestCommits,
  there: PullRequestCommit[],
  column: number,
  earlier: number,
): GraphNode[] {
  const onBase = history.stack ? STACK_LANE : BASE_LANE;
  const hidden = new Set(
    history.commits.slice(0, earlier).map((one) => one.sha),
  );
  const via = (parents: string[]) => [
    ...new Set(parents.map((one) => (hidden.has(one) ? EARLIER : one))),
  ];
  const first = history.commits[0];
  return [
    ...oldForkOf(history),
    ...outsideOf(history).map((id) => ({
      id,
      lane: BASE_LANE,
      parents: [],
    })),
    ...originForkOf(history, there),
    ...(history.stack?.commits ?? []).map((one) => ({
      id: one.sha,
      lane: STACK_LANE,
      parents: one.parents,
    })),
    ...baseNodesOf(history, onBase, column),
    ...(earlier && first
      ? [
          {
            id: EARLIER,
            lane: PR_LANE,
            parents: first.parents,
            span: spanOf(earlierText(earlier), column),
          },
        ]
      : []),
    ...history.commits.slice(earlier).map((one) => ({
      id: one.sha,
      lane: PR_LANE,
      parents: via(one.parents),
    })),
    ...ghostsOf(history).map((one) => ({
      id: one.sha,
      lane: GHOST_LANE,
      parents: via(one.parents),
    })),
    ...there.map((one) => ({
      id: one.sha,
      lane: ORIGIN_LANE,
      parents: via(one.parents),
    })),
  ];
}

interface Drawing {
  graph: GraphLayout;
  ticked: boolean;
  earlier: number;
}

function drawingOf(
  input: TimelineInput,
  lanes: string[],
  there: PullRequestCommit[],
  keep: number,
): Drawing {
  const { history, across } = input;
  const top = foldsOf(history).length ? DATE_ROW : 0;
  const room = across && across - SPACING.left - SPACING.right;
  const drawn = (spacing: Spacing, earlier: number): Drawing => ({
    graph: layout(
      lanes,
      nodesOf(history, there, spacing.column, earlier),
      { ...spacing, top: spacing.top + top },
      across,
    ),
    ticked: spacing === TICKS,
    earlier,
  });
  const dots = drawn(DOTS, 0);
  if (drawnAs(dots.graph.widest, room) === 'dot') return dots;
  const ticks = drawn(TICKS, 0);
  if (input.unfolded || drawnAs(ticks.graph.widest, room) === 'tick')
    return ticks;
  let best = ticks;
  for (let earlier = 1; earlier <= keep; earlier += 1) {
    const folded = drawn(TICKS, earlier);
    if (folded.graph.widest < best.graph.widest) best = folded;
    if (drawnAs(folded.graph.widest, room) === 'tick') return folded;
  }
  return best;
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
  if (
    !reviewed ||
    !input.reviewedAt ||
    input.standing.offOrigin.has(reviewed.id)
  )
    return null;
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
  collapsed: CollapsedRun[],
): SinceFork | null {
  const opening = stretchesOf(history)[0];
  const first = placed.get(
    opening && 'fold' in opening
      ? opening.fold.id
      : (opening?.commit.sha ?? ''),
  );
  const last = placed.get(history.base_commits.at(-1)?.sha ?? '');
  if (!first || !last) return null;
  const pill = collapsed.find((one) => one.x === first.x);
  const x = pill ? pill.left - RUN_GAP : first.x - BAND_REACH;
  return {
    x,
    y: first.y - BAND_REACH,
    width: last.x + BAND_REACH - x,
    height: 2 * BAND_REACH,
    textY: first.y - BOX_RISE - (collapsed.length ? DATE_ROW : 0),
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
  if (node.lane === ORIGIN_LANE) return 'origin';
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
  const { diverged } = input.standing;
  const there = diverged?.there ?? [];
  const offOrigin = diverged ? new Set<string>() : input.standing.offOrigin;
  const order = history.commits.map((one) => one.sha);
  if (!order.length) return null;
  const stack = history.stack;
  const folded = foldsOf(history).length > 0;
  const ghosts = ghostsOf(history);
  const oldFork = oldForkOf(history)[0];
  const base = input.base ?? 'main';
  const showing =
    input.picked ??
    (input.hidden || !input.current
      ? { from: order[0]!, to: order.at(-1)! }
      : { from: input.current, to: input.current });
  const from = order.indexOf(showing.from);
  const to = order.indexOf(showing.to);
  const kept = [
    from,
    to,
    input.hidden ? -1 : order.indexOf(input.current ?? ''),
  ].filter((one) => one >= 0);
  const drawing = drawingOf(
    input,
    [
      BASE_LANE,
      ...(stack ? [STACK_LANE] : []),
      ...(there.length ? [ORIGIN_LANE] : []),
      PR_LANE,
      ...(ghosts.length ? [GHOST_LANE] : []),
    ],
    there,
    Math.min(order.length - 1, ...kept),
  );
  const { graph, ticked } = drawing;
  const shelved = graph.nodes.get(EARLIER);
  const subjects = new Map(
    [
      ...(stack?.commits ?? []),
      ...history.base_commits,
      ...forkCommitsOf(history),
      ...history.commits,
      ...ghosts,
      ...there,
    ].map((one) => [one.sha, one.subject]),
  );
  const merges = new Set(
    history.commits
      .filter((one) => one.parents.length > 1)
      .map((one) => one.sha),
  );
  const dates = new Map(
    folded
      ? [
          [history.fork, history.fork_at],
          [history.base_tip, history.base_commits.at(-1)!.authored_at],
        ]
      : [],
  );
  const leaving = new Set(forkCommitsOf(history).map((one) => one.sha));
  const placed = [...graph.nodes.values()].filter(
    (node) => !node.id.startsWith(RUN) && node.id !== EARLIER,
  );
  const dots = placed.map((node) => {
    const at = order.indexOf(node.id);
    const date = dates.get(node.id);
    const short = node.id.slice(0, SHORT);
    const subject = subjects.get(node.id);
    const shape: DotShape = merges.has(node.id)
      ? 'diamond'
      : ticked &&
          (at >= 0 || node.lane === ORIGIN_LANE || node.lane === GHOST_LANE)
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
        (folded && leaving.has(node.id)) ||
        (at >= 0 &&
          (!ticked ||
            [showing.from, showing.to, input.current].includes(node.id))),
      date: date ? dayOf(date) : null,
      dateY: node.id === history.fork ? node.y - DATE_RISE : node.y + DATE_DROP,
      dateAnchor:
        node.id === history.fork ? ('start' as const) : ('middle' as const),
      pushed: node.lane === PR_LANE ? !offOrigin.has(node.id) : null,
      pickable: at >= 0,
      inRange: at >= from && at <= to && at >= 0,
      radius:
        at >= 0 || node.lane === GHOST_LANE || node.lane === ORIGIN_LANE
          ? 6
          : 4,
      matched: input.matched.has(node.id),
      matchedY: node.y - MATCHED_RISE,
    };
  });
  const lastPushed = graph.nodes.get(
    order.findLast((sha) => !offOrigin.has(sha)) ?? '',
  );
  const firstUnpushed = graph.nodes.get(
    order.find((sha) => offOrigin.has(sha)) ?? '',
  );
  const main = lastOn(BASE_LANE, graph.nodes)!;
  const under = lastOn(STACK_LANE, graph.nodes);
  const head = graph.nodes.get(order.at(-1)!)!;
  const originHead = graph.nodes.get(there.at(-1)?.sha ?? '');
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
    box: null,
  });
  const collapsed = collapsedOf(history, graph.nodes, graph.column);
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
          ]
        : []),
      ...(originHead ? [boxed(label('origin', 'origin', originHead))] : []),
      firstUnpushed || originHead
        ? boxed(label('local', 'local', head))
        : label('head', 'head', head),
      ...forkLabelsOf(graph.nodes, oldFork?.id, history.fork),
    ],
    current: ringed ? { sha: ringed.id, x: ringed.x, y: ringed.y } : null,
    band: bandOf(
      graph.nodes.get(showing.from) ?? head,
      graph.nodes.get(showing.to) ?? head,
    ),
    flag: flagOf(order, input, graph.nodes, graph.column),
    since: sinceOf(history, graph.nodes, base, collapsed),
    collapsed,
    earlier: shelved
      ? pillAt(shelved, graph.column, earlierText(drawing.earlier))
      : null,
    days: ticked ? daysOf(history, graph.nodes) : [],
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
      tip:
        stack || history.behind || oldFork || diverged ? null : `${base}'s tip`,
      main: stack?.branch ?? base,
      behind: diverged ? 0 : history.behind,
      diverged: diverged
        ? {
            here: diverged.here,
            other: `${plural(there.length, 'other commit')}`,
            from: there[0]?.parents[0]?.slice(0, SHORT) ?? '',
            chip: `diverged from origin · ${diverged.here} here, ${there.length} on origin`,
          }
        : null,
    },
    presets: presetsOf(order, input, showing),
    key: {
      merge: merges.size > 0,
      tick: ticked,
      unpushed: firstUnpushed !== undefined,
      origin: originHead !== undefined,
    },
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
    box: null,
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
