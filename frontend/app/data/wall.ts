import type { FinishedRun, WallGroup } from 'frontend/data/api';

export interface Numbered {
  repo: string;
  number: number;
}

export type Level = 'needs' | 'working' | 'waiting' | 'parked';

const LEVELS: Record<WallGroup, Level> = {
  'needs-you': 'needs',
  'agent-working': 'working',
  'waiting-on-others': 'waiting',
  parked: 'parked',
};

export function levelOf(group: WallGroup): Level {
  return LEVELS[group];
}

const NAMES: Record<WallGroup, string> = {
  'needs-you': 'Needs you',
  'agent-working': 'Agent working',
  'waiting-on-others': 'Waiting on others',
  parked: 'Parked',
};

export function nameOf(group: WallGroup): string {
  return NAMES[group];
}

export function keyOf(pr: Numbered): string {
  return `${pr.repo}#${pr.number}`;
}

export function numberIn(text: string): number | null {
  const number = Number(text);
  return /^\d+$/.test(text) && Number.isSafeInteger(number) ? number : null;
}

export function namesARepo(owner: string, name: string): boolean {
  return [owner, name].every((part) => /^[A-Za-z0-9_.-]+$/.test(part));
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
