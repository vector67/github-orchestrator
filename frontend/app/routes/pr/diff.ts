import Route from '@ember/routing/route';
import { service } from '@ember/service';
import type PollService from 'frontend/services/poll';
import type ThemeService from 'frontend/services/theme';
import type ThreadsService from 'frontend/services/threads';

export default class PrDiffRoute extends Route {
  @service declare threads: ThreadsService;
  @service declare poll: PollService;
  @service declare theme: ThemeService;

  queryParams = { file: { replace: true } };

  async model() {
    this.theme.restore();
    await this.poll.startRail().catch(() => undefined);
    return this.threads;
  }

  activate(): void {
    this.poll.start();
  }

  deactivate(): void {
    this.poll.stop();
  }
}
