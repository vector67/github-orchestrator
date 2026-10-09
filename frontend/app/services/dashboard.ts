import Service, { service } from '@ember/service';
import type HereService from 'frontend/services/here';
import type HubService from 'frontend/services/hub';
import type PollService from 'frontend/services/poll';
import type { Standing } from 'frontend/services/poll';
import type StoreService from 'frontend/services/store';
import type { HeardLine, ShownPr } from 'frontend/services/store';

export default class DashboardService extends Service {
  @service declare here: HereService;
  @service declare hub: HubService;
  @service declare poll: PollService;
  @service declare store: StoreService;

  get now(): number {
    return this.poll.now;
  }

  get isLive(): boolean {
    const { streams, heard, streamed } = this.poll.board;
    if (!streams) return heard;
    return streams.dashboard.state === 'open' && streamed;
  }

  get standing(): Standing {
    const { streams, polledStanding, streamed } = this.poll.board;
    if (!streams) return polledStanding;
    if (streams.dashboard.state !== 'open') return 'gone';
    return streamed ? 'answering' : 'starting';
  }

  get missed(): boolean {
    return this.poll.board.bar.missed || this.hub.missed;
  }

  get notesLive(): boolean {
    return this.poll.board.streams?.notes.state === 'open';
  }

  get outputLive(): boolean {
    return this.poll.board.streams?.output.state === 'open';
  }

  get onTheWall(): boolean {
    const pr = this.here.pr;
    return this.store.onHub && pr !== null && !!this.hub.find(pr);
  }

  get shown(): ShownPr | null {
    const at = this.here.pr;
    if (at === null || (!this.isLive && !this.onTheWall)) return null;
    const pr = this.store.pr(at.repo, at.number);
    return pr?.drawn ? (pr as ShownPr) : null;
  }

  get refreshedAt(): number {
    const { streams, readAt } = this.poll.board;
    if (!this.isLive) return this.poll.hubAt;
    if (streams) return this.poll.now;
    return readAt ?? this.poll.hubAt;
  }

  get notes(): string | null {
    const pr = this.here.pr;
    return pr === null ? null : this.store.manager(pr).notes;
  }

  get output(): HeardLine[] {
    const pr = this.here.pr;
    return pr === null ? [] : this.store.manager(pr).output;
  }
}
