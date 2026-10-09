import Route from '@ember/routing/route';
import { service } from '@ember/service';
import type RouterService from '@ember/routing/router-service';
import { numberIn, type Numbered } from 'frontend/data/wall';
import type HereService from 'frontend/services/here';
import type HubService from 'frontend/services/hub';
import type PollService from 'frontend/services/poll';
import { waitForPromise } from '@ember/test-waiters';

type Params = {
  owner: string;
  name: string;
  number: string;
};

export default class PrRoute extends Route {
  @service declare router: RouterService;
  @service declare here: HereService;
  @service declare hub: HubService;
  @service declare poll: PollService;

  beforeModel(): void {
    const { owner, name, number } = this.paramsFor('pr') as Params;
    if (numberIn(number) === null) {
      void this.router.replaceWith(
        'old-link.under',
        owner,
        `${name}/${number}`,
      );
    }
  }

  model(params: Params): Numbered {
    const pr = {
      repo: `${params.owner}/${params.name}`,
      number: Number(params.number),
    };
    this.here.enter(pr);
    this.poll.startList();
    void waitForPromise(this.poll.startRail().catch(() => undefined));
    if (this.hub.onHub) {
      this.poll.startHub();
      void waitForPromise(this.opened(pr));
    } else {
      this.poll.startBar();
      void waitForPromise(this.poll.read());
    }
    return pr;
  }

  deactivate(): void {
    this.poll.stopBar();
    this.poll.stopList();
  }

  private async opened(pr: Numbered): Promise<void> {
    await this.poll.held();
    this.hub.select(pr);
  }
}
