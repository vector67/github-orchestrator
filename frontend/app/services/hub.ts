import Service, { service } from '@ember/service';
import { tracked } from '@glimmer/tracking';
import { keyOf, type Numbered } from 'frontend/data/wall';
import { pollOf, type Said } from 'frontend/data/runs';
import type PollService from 'frontend/services/poll';
import type ReachabilityService from 'frontend/services/reachability';
import type StoreService from 'frontend/services/store';
import type { PrEntity, WallSection } from 'frontend/services/store';
import type { NewestRelease } from 'frontend/data/api';

export default class HubService extends Service {
  @service('poll') declare loader: PollService;
  @service declare reachability: ReachabilityService;
  @service declare store: StoreService;

  @tracked selected: string | null = null;

  get onHub(): boolean {
    return this.store.onHub;
  }

  get now(): number {
    return this.loader.hubAt;
  }

  get missed(): boolean {
    return this.loader.wall.missed || this.loader.runs.missed;
  }

  get poll(): Said | null {
    if (this.loader.wall.down || this.loader.runs.down) {
      return { text: this.reachability.outage, alarm: true };
    }
    const watcher = this.store.watcher;
    return watcher
      ? pollOf(watcher, this.store.health?.state ?? null, this.now)
      : null;
  }

  get sections(): WallSection[] {
    return this.store.wall;
  }

  get stale(): boolean {
    return this.poll?.alarm ?? false;
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
