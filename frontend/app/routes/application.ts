import Route from '@ember/routing/route';
import { service } from '@ember/service';
import type RouterService from '@ember/routing/router-service';
import type Transition from '@ember/routing/transition';
import type PollService from 'frontend/services/poll';
import type KeysService from 'frontend/services/keys';
import type StoreService from 'frontend/services/store';

export default class ApplicationRoute extends Route {
  @service declare poll: PollService;
  @service declare keys: KeysService;
  @service declare router: RouterService;
  @service declare store: StoreService;

  async beforeModel(transition: Transition): Promise<void> {
    this.keys.listen();
    await this.poll.locate();
    const state = this.store.health?.state;
    const settingUp = state === 'setup' || state === 'broken';
    if (settingUp && transition.to?.name !== 'setup') {
      void this.router.replaceWith('setup');
    }
  }
}
