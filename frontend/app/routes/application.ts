import Route from '@ember/routing/route';
import { service } from '@ember/service';
import type RouterService from '@ember/routing/router-service';
import type Transition from '@ember/routing/transition';
import type PollService from 'frontend/services/poll';
import type KeysService from 'frontend/services/keys';
import type StoreService from 'frontend/services/store';
import config from 'frontend/config/environment';

interface Marked {
  closesTab?: boolean;
}

function closedByBack(): void {
  const marked = { ...(history.state as object | null), closesTab: true };
  history.replaceState(marked, '');
  history.pushState({ ...marked, closesTab: false }, '', location.href);
  window.addEventListener('popstate', (event: PopStateEvent) => {
    if ((event.state as Marked | null)?.closesTab) window.close();
  });
}

export default class ApplicationRoute extends Route {
  @service declare poll: PollService;
  @service declare keys: KeysService;
  @service declare router: RouterService;
  @service declare store: StoreService;

  async beforeModel(transition: Transition): Promise<void> {
    this.keys.listen();
    void this.store.readEmojis();
    await this.poll.locate();
    const state = this.store.health?.state;
    const settingUp = state === 'setup' || state === 'broken';
    if (settingUp && transition.to?.name !== 'setup') {
      void this.router.replaceWith('setup');
    }
    if (
      transition.to?.queryParams['back'] === 'close' &&
      config.locationType === 'history'
    ) {
      this.router.one('routeDidChange', () => {
        closedByBack();
        void this.router.replaceWith({ queryParams: { back: null } });
      });
    }
  }
}
