import Route from '@ember/routing/route';
import { service } from '@ember/service';
import type PollService from 'frontend/services/poll';
import type ThemeService from 'frontend/services/theme';

export default class SummaryRoute extends Route {
  @service declare poll: PollService;
  @service declare theme: ThemeService;

  async model(): Promise<void> {
    this.theme.restore();
    await Promise.all([
      this.poll.startRail().catch(() => undefined),
      this.poll.startSummary().catch(() => undefined),
    ]);
  }

  deactivate(): void {
    this.poll.stopSummary();
  }
}
