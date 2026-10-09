import Route from '@ember/routing/route';
import { service } from '@ember/service';
import type RouterService from '@ember/routing/router-service';
import type Transition from '@ember/routing/transition';
import { numberIn, pageOf } from 'frontend/data/wall';
import type HubService from 'frontend/services/hub';
import type PollService from 'frontend/services/poll';
import type StoreService from 'frontend/services/store';
import type ThemeService from 'frontend/services/theme';
import type { PrEntity } from 'frontend/services/store';

export interface OldLink {
  number: number;
  under: string;
  prs: PrEntity[];
}

export default class OldLinkRoute extends Route {
  @service declare router: RouterService;
  @service declare hub: HubService;
  @service declare poll: PollService;
  @service declare store: StoreService;
  @service declare theme: ThemeService;

  async model(
    params: { number: string },
    transition: Transition,
  ): Promise<OldLink | null> {
    this.theme.restore();
    const number = numberIn(params.number);
    if (number === null) return null;
    const under = transition.to?.params?.['under'];
    return {
      number,
      under: typeof under === 'string' ? `/${under}` : '',
      prs: await this.holding(number),
    };
  }

  redirect(link: OldLink | null): void {
    if (!link) return;
    const { prs, under } = link;
    const [only, ...others] = prs;
    if (only && !others.length)
      void this.router.replaceWith(pageOf(only, under));
  }

  private async holding(number: number): Promise<PrEntity[]> {
    if (this.hub.onHub) {
      this.poll.startHub();
      await this.poll.held();
      return this.store.holding(number);
    }
    const home = await this.store.readHome();
    const pr = this.store.pr(home.repo, home.number);
    return pr && pr.number === number ? [pr] : [];
  }
}
