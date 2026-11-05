import Route from '@ember/routing/route';
import { service } from '@ember/service';
import type PollService from 'frontend/services/poll';
import type StoreService from 'frontend/services/store';
import type ThemeService from 'frontend/services/theme';

export default class SetupRoute extends Route {
  @service declare poll: PollService;
  @service declare store: StoreService;
  @service declare theme: ThemeService;

  async model(): Promise<void> {
    this.theme.restore();
    this.poll.startHub();
    await Promise.all([this.store.readSetup(), this.poll.refreshHub()]);
  }
}
