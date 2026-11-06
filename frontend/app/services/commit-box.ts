import Service from '@ember/service';
import { tracked } from '@glimmer/tracking';
import { keep, recall, recalledAs } from 'frontend/data/site-data';

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
  const kept = recall(AUTO_READ);
  return AUTO_READS.find((one) => one === kept) ?? 'off';
}

function recalled(): CommitSizing {
  const kept = recall(SIZING);
  return COMMIT_SIZINGS.find((one) => one === kept) ?? 'full';
}

function dismissals(): Record<string, string> {
  return recalledAs(DISMISSED, (kept) => kept as Record<string, string>, {});
}

export default class CommitBoxService extends Service {
  @tracked sizing: CommitSizing = recalled();
  @tracked private dismissed: Record<string, string> = dismissals();
  @tracked skipMerges: boolean = recall(SKIP_MERGES) !== 'false';
  @tracked autoRead: AutoRead = autoReading();

  chooseAutoRead(autoRead: AutoRead): void {
    this.autoRead = autoRead;
    keep(AUTO_READ, autoRead);
  }

  chooseSkipMerges(skip: boolean): void {
    this.skipMerges = skip;
    keep(SKIP_MERGES, String(skip));
  }

  choose(sizing: CommitSizing): void {
    this.sizing = sizing;
    keep(SIZING, sizing);
  }

  noteDismissed(pr: string, head: string): boolean {
    return this.dismissed[pr] === head;
  }

  dismissNote(pr: string, head: string): void {
    this.dismissed = { ...this.dismissed, [pr]: head };
    keep(DISMISSED, JSON.stringify(this.dismissed));
  }
}
