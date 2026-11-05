import Service, { service } from '@ember/service';
import { tracked } from '@glimmer/tracking';
import { keyOf, type Numbered } from 'frontend/data/wall';
import {
  pollOf,
  pollStatusOf,
  type PollStatus,
  type Said,
} from 'frontend/data/runs';
import type PollService from 'frontend/services/poll';
import type ReachabilityService from 'frontend/services/reachability';
import type StoreService from 'frontend/services/store';
import type { PrEntity, WallRow, WallSection } from 'frontend/services/store';
import type { NewestRelease } from 'frontend/data/api';

const FOLDABLE = 'parked';
const PARKED_FOLDED = 'wall-parked-folded';

function foldedBefore(): boolean {
  try {
    return localStorage.getItem(PARKED_FOLDED) === 'true';
  } catch {
    return false;
  }
}

export default class HubService extends Service {
  @service('poll') declare loader: PollService;
  @service declare reachability: ReachabilityService;
  @service declare store: StoreService;

  @tracked selected: string | null = null;
  @tracked parkedFolded = foldedBefore();

  get now(): number {
    return Math.max(this.loader.now, this.loader.hubAt);
  }

  get missed(): boolean {
    return this.loader.wall.missed || this.loader.runs.missed;
  }

  get ticking(): number {
    return Math.max(this.loader.second, this.loader.hubAt);
  }

  get poll(): Said | null {
    if (this.loader.wall.down || this.loader.runs.down) {
      return { text: this.reachability.outage, alarm: true };
    }
    const watcher = this.store.watcher;
    return watcher
      ? pollOf(watcher, this.store.health?.state ?? null, this.ticking)
      : null;
  }

  get pollStatus(): PollStatus | null {
    const poll = this.poll;
    return poll
      ? pollStatusOf(poll, this.store.watcher?.polled_at ?? null, this.ticking)
      : null;
  }

  get sections(): WallSection[] {
    return this.store.wall;
  }

  foldable(section: WallSection): boolean {
    return section.group === FOLDABLE;
  }

  isFolded(section: WallSection): boolean {
    return this.foldable(section) && this.parkedFolded;
  }

  shownOf(section: WallSection): WallRow[] {
    return this.isFolded(section) ? [] : section.prs;
  }

  get walked(): WallRow[] {
    return this.sections.flatMap((section) => this.shownOf(section));
  }

  toggleParked(): void {
    this.parkedFolded = !this.parkedFolded;
    try {
      localStorage.setItem(PARKED_FOLDED, String(this.parkedFolded));
    } catch {
      return;
    }
  }

  get stale(): boolean {
    return (this.poll?.alarm ?? false) || this.store.unheld !== null;
  }

  find(pr: Numbered): PrEntity | undefined {
    const found = this.store.pr(pr.repo, pr.number);
    return found?.place ? found : undefined;
  }

  select(at: Numbered): void {
    const pr = this.find(at);
    if (!pr) return;
    this.selected = keyOf(pr);
    this.store.opened(pr.repo, pr.number);
  }

  followRestart(): void {
    this.loader.followRestart();
  }

  get url(): string | null {
    return this.store.health?.hub_url ?? null;
  }

  get fontProblem(): string | null {
    return this.store.health?.font_problem ?? null;
  }

  get update(): NewestRelease | null {
    const newest = this.store.health?.newest_release ?? null;
    return newest?.newer ? newest : null;
  }
}
