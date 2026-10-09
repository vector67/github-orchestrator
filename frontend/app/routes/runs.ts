import Route from '@ember/routing/route';
import { service } from '@ember/service';
import type HubService from 'frontend/services/hub';
import type PollService from 'frontend/services/poll';
import type ThemeService from 'frontend/services/theme';

export default class RunsRoute extends Route {
  @service declare hub: HubService;
  @service declare poll: PollService;
  @service declare theme: ThemeService;

  async model(): Promise<HubService> {
    this.theme.restore();
    this.poll.startHub();
    await this.poll.refreshHub();
    return this.hub;
  }
}
