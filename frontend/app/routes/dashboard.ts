import Route from '@ember/routing/route';
import { service } from '@ember/service';
import { reportError } from 'frontend/data/report';
import type PollService from 'frontend/services/poll';
import type ThemeService from 'frontend/services/theme';
import type ThreadsService from 'frontend/services/threads';

export default class DashboardRoute extends Route {
  @service declare threads: ThreadsService;
  @service declare theme: ThemeService;
  @service declare poll: PollService;

  async model() {
    this.theme.restore();
    this.poll.startDashboard();
    await Promise.all([
      this.poll
        .startRail()
        .catch((trouble: unknown) => reportError('header', trouble)),
      this.poll.follow(),
    ]);
    return this.threads;
  }

  deactivate(): void {
    this.poll.stopDashboard();
    this.poll.leave();
  }
}
