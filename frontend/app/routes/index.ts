import Route from '@ember/routing/route';
import { service } from '@ember/service';
import type RouterService from '@ember/routing/router-service';
import { pageOf } from 'frontend/data/wall';
import type HubService from 'frontend/services/hub';
import type PollService from 'frontend/services/poll';
import type StoreService from 'frontend/services/store';
import type ThemeService from 'frontend/services/theme';

export default class IndexRoute extends Route {
  @service declare router: RouterService;
  @service declare hub: HubService;
  @service declare poll: PollService;
  @service declare store: StoreService;
  @service declare theme: ThemeService;

  async beforeModel(): Promise<void> {
    if (this.hub.onHub) return;
    const pr = await this.store.readHome();
    void this.router.replaceWith(pageOf(pr));
  }

  async model(): Promise<HubService> {
    this.theme.restore();
    this.poll.startHub();
    await Promise.all([this.poll.refreshHub(), this.store.readTour()]);
    return this.hub;
  }
}
