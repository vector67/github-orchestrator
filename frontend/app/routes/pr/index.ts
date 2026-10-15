import Route from '@ember/routing/route';
import { service } from '@ember/service';
import type RouterService from '@ember/routing/router-service';
import type { Numbered } from 'frontend/data/wall';
import type PollService from 'frontend/services/poll';
import type StoreService from 'frontend/services/store';

export default class PrIndexRoute extends Route {
  @service declare router: RouterService;
  @service declare poll: PollService;
  @service declare store: StoreService;

  async afterModel(): Promise<void> {
    const { repo, number } = this.modelFor('pr') as Numbered;
    await this.poll.held();
    const role = this.store.summary(repo, number)?.role;
    void this.router.replaceWith(
      role === 'reviewer' ? 'summary' : 'conversations',
    );
  }
}
