import Service from '@ember/service';
import { tracked } from '@glimmer/tracking';

export type CommitSizing = 'full' | 'minimal' | 'hidden';

export const COMMIT_SIZINGS: CommitSizing[] = ['full', 'minimal', 'hidden'];

export type AutoRead =
  'off' | 'instant' | '2s' | '5s' | '10s' | '30s' | 'bottom';

export const AUTO_READS: AutoRead[] = [
  'off',
  'instant',
  '2s',
  '5s',
  '10s',
  '30s',
  'bottom',
];

const SIZING = 'commit-box-sizing';
const DISMISSED = 'commit-notes-dismissed';
const SKIP_MERGES = 'commit-skip-merges';
const AUTO_READ = 'commit-auto-read';

function autoReading(): AutoRead {
  try {
    const kept = localStorage.getItem(AUTO_READ);
    return AUTO_READS.find((one) => one === kept) ?? 'off';
  } catch {
    return 'off';
  }
}

function recalled(): CommitSizing {
  try {
    const kept = localStorage.getItem(SIZING);
    return COMMIT_SIZINGS.find((one) => one === kept) ?? 'full';
  } catch {
    return 'full';
  }
}

function skipping(): boolean {
  try {
    return localStorage.getItem(SKIP_MERGES) !== 'false';
  } catch {
    return true;
  }
}

function dismissals(): Record<string, string> {
  try {
    return JSON.parse(localStorage.getItem(DISMISSED) ?? '{}') as Record<
      string,
      string
    >;
  } catch {
    return {};
  }
}

export default class CommitBoxService extends Service {
  @tracked sizing: CommitSizing = recalled();
  @tracked private dismissed: Record<string, string> = dismissals();
  @tracked skipMerges: boolean = skipping();
  @tracked autoRead: AutoRead = autoReading();

  chooseAutoRead(autoRead: AutoRead): void {
    this.autoRead = autoRead;
    try {
      localStorage.setItem(AUTO_READ, autoRead);
    } catch {
      return;
    }
  }

  chooseSkipMerges(skip: boolean): void {
    this.skipMerges = skip;
    try {
      localStorage.setItem(SKIP_MERGES, String(skip));
    } catch {
      return;
    }
  }

  choose(sizing: CommitSizing): void {
    this.sizing = sizing;
    try {
      localStorage.setItem(SIZING, sizing);
    } catch {
      return;
    }
  }

  noteDismissed(pr: string, head: string): boolean {
    return this.dismissed[pr] === head;
  }

  dismissNote(pr: string, head: string): void {
    this.dismissed = { ...this.dismissed, [pr]: head };
    try {
      localStorage.setItem(DISMISSED, JSON.stringify(this.dismissed));
    } catch {
      return;
    }
  }
}
