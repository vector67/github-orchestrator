import Service from '@ember/service';
import { tracked } from '@glimmer/tracking';

export type CommitSizing = 'full' | 'minimal' | 'hidden';

export const COMMIT_SIZINGS: CommitSizing[] = ['full', 'minimal', 'hidden'];

const SIZING = 'commit-box-sizing';
const DISMISSED = 'commit-notes-dismissed';

function recalled(): CommitSizing {
  try {
    const kept = localStorage.getItem(SIZING);
    return COMMIT_SIZINGS.find((one) => one === kept) ?? 'full';
  } catch {
    return 'full';
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
