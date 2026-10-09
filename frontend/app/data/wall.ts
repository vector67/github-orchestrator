import type { FinishedRun, WallGroup } from 'frontend/data/api';

export interface Numbered {
  repo: string;
  number: number;
}

export type Level = 'needs' | 'draft' | 'working' | 'waiting' | 'parked';

const LEVELS: Record<WallGroup, Level> = {
  'needs-you': 'needs',
  draft: 'draft',
  'agent-working': 'working',
  'waiting-on-others': 'waiting',
  'on-hold': 'parked',
  mentioned: 'waiting',
};

export function levelOf(group: WallGroup): Level {
  return LEVELS[group];
}

export function keyOf(pr: Numbered): string {
  return `${pr.repo}#${pr.number}`;
}

export function numberIn(text: string): number | null {
  return /^\d+$/.test(text) ? Number(text) : null;
}

export function pageOf(pr: Numbered, under = ''): string {
  return `/pr/${pr.repo}/${pr.number}${under}`;
}

export function failingOf(pr: Numbered, runs: FinishedRun[]): FinishedRun[] {
  const own = runs.filter(
    (run) => run.repo === pr.repo && run.number === pr.number,
  );
  const settled = own.findIndex((run) => !run.failed);
  return settled < 0 ? own : own.slice(0, settled);
}
