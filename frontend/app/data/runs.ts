import type {
  FinishedRun,
  HubState,
  RunsToday,
  WatcherHealth,
} from 'frontend/data/api';
import {
  clockOf,
  exitWordOf,
  lengthOf,
  relativeOf,
  runNameOf,
} from 'frontend/data/dashboard';

export interface Said {
  text: string;
  alarm: boolean;
}

export interface Fact extends Said {
  label: string;
}

export interface RunCell {
  key: string;
  text: string;
}

export interface RunRow {
  run: FinishedRun;
  cells: RunCell[];
}

const STATE_WORDS: Record<HubState, Said> = {
  watching: { text: 'watching', alarm: false },
  setup: { text: 'in setup, polling nothing', alarm: true },
  broken: { text: 'config broken, polling nothing', alarm: true },
};

function clockAt(iso: string): string {
  return clockOf(Date.parse(iso));
}

function agedAt(iso: string, now: number): string {
  return `${clockAt(iso)}, ${relativeOf(iso, now)}`;
}

function secondsUntil(iso: string, now: number): number {
  return (Date.parse(iso) - now) / 1000;
}

export function pollOf(
  watcher: WatcherHealth,
  state: HubState | null,
  now: number,
): Said {
  if (state && state !== 'watching') return STATE_WORDS[state];
  const polled = watcher.polled_at;
  if (watcher.last_error) {
    return { text: `polls failing: ${watcher.last_error}`, alarm: true };
  }
  if (!polled) return { text: 'no poll yet', alarm: false };
  if (watcher.overdue) {
    return { text: `no poll since ${agedAt(polled, now)}`, alarm: true };
  }
  return { text: `polled ${agedAt(polled, now)}`, alarm: false };
}

function counted(runs: number): string {
  return runs === 1 ? '1 run' : `${runs} runs`;
}

function costWords(today: RunsToday): string {
  return today.cost_usd === null ? '' : ` · ~$${today.cost_usd.toFixed(2)}`;
}

export function todayOf(today: RunsToday): string {
  return `${counted(today.runs)} today${costWords(today)}`;
}

function failedFact(runs: FinishedRun[]): Fact[] {
  const failed = runs.filter((run) => run.failed).length;
  if (!failed) return [];
  return [
    {
      label: 'Failed',
      text: `${failed} of ${runs.length} this week`,
      alarm: true,
    },
  ];
}

export function factsOf(
  watcher: WatcherHealth,
  state: HubState | null,
  today: RunsToday,
  runs: FinishedRun[],
  now: number,
): Fact[] {
  const polled = watcher.polled_at;
  const due = watcher.next_poll_at;
  const unpriced =
    today.cost_usd !== null && today.unpriced
      ? `, ${today.unpriced} without a cost`
      : '';
  const facts: Fact[] = [
    ...(state ? [{ label: 'Watcher', ...STATE_WORDS[state] }] : []),
    {
      label: 'Last poll',
      text: polled ? agedAt(polled, now) : 'none yet',
      alarm: watcher.overdue,
    },
  ];
  if (due) {
    const seconds = secondsUntil(due, now);
    facts.push({
      label: 'Next poll',
      text: seconds > 0 ? `in ${lengthOf(seconds)}` : 'due now',
      alarm: watcher.overdue,
    });
  }
  if (watcher.last_error) {
    facts.push({ label: 'Last error', text: watcher.last_error, alarm: true });
  }
  facts.push({
    label: 'Today',
    text: `${counted(today.runs)}${costWords(today)}${unpriced}`,
    alarm: false,
  });
  return [...facts, ...failedFact(runs)];
}

function endedOf(iso: string, now: number): string {
  const ended = new Date(Date.parse(iso));
  if (ended.toDateString() === new Date(now).toDateString()) {
    return clockAt(iso);
  }
  return ended.toLocaleString('en-GB', {
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

function exitOf(run: FinishedRun): string {
  return run.failed && run.exit_code === 0
    ? 'errored'
    : exitWordOf(run.exit_code);
}

function repeats(run: FinishedRun, other: FinishedRun): boolean {
  return (
    run.failed &&
    other.failed &&
    run.repo === other.repo &&
    run.number === other.number &&
    runNameOf(run.event) === runNameOf(other.event)
  );
}

function spanOf(runs: FinishedRun[], now: number): string {
  const newest = endedOf(runs[0]!.ended_at, now);
  const oldest = endedOf(runs.at(-1)!.ended_at, now);
  return newest === oldest ? newest : `${oldest}–${newest}`;
}

function costOf(runs: FinishedRun[]): string {
  const costs = runs.flatMap((run) =>
    run.cost_usd === null ? [] : [run.cost_usd],
  );
  if (!costs.length) return '—';
  return `$${costs.reduce((sum, cost) => sum + cost, 0).toFixed(2)}`;
}

function cellsOf(runs: FinishedRun[], now: number): RunCell[] {
  const run = runs[0]!;
  const name = runNameOf(run.event);
  return [
    { key: 'ended', text: spanOf(runs, now) },
    { key: 'pr', text: run.number === null ? '—' : `#${run.number}` },
    {
      key: 'event',
      text: runs.length > 1 ? `${name} · ${runs.length} failed` : name,
    },
    {
      key: 'took',
      text: lengthOf(runs.reduce((sum, one) => sum + one.elapsed_seconds, 0)),
    },
    { key: 'exit', text: exitOf(run) },
    { key: 'cost', text: costOf(runs) },
  ];
}

export function rowsOf(runs: FinishedRun[], now: number): RunRow[] {
  const groups: FinishedRun[][] = [];
  let stretch: FinishedRun[][] = [];
  for (const run of runs) {
    const same = stretch.find((group) => repeats(group[0]!, run));
    if (same) {
      same.push(run);
      continue;
    }
    const group = [run];
    groups.push(group);
    stretch = run.failed ? [...stretch, group] : [];
  }
  return groups.map((group) => ({
    run: group[0]!,
    cells: cellsOf(group, now),
  }));
}
