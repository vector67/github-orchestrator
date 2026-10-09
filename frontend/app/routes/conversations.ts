import Route from '@ember/routing/route';
import { service } from '@ember/service';
import type RouterService from '@ember/routing/router-service';
import type Transition from '@ember/routing/transition';
import { unreachable } from 'frontend/data/refusal';
import type BoardKeysService from 'frontend/services/board-keys';
import type HubService from 'frontend/services/hub';
import type KeysService from 'frontend/services/keys';
import type PollService from 'frontend/services/poll';
import type ThemeService from 'frontend/services/theme';
import type ThreadsService from 'frontend/services/threads';

export default class ConversationsRoute extends Route {
  @service declare threads: ThreadsService;
  @service declare hub: HubService;
  @service declare poll: PollService;
  @service declare keys: KeysService;
  @service('board-keys') declare boardKeys: BoardKeysService;
  @service declare theme: ThemeService;
  @service declare router: RouterService;

  async model() {
    this.theme.restore();
    try {
      await Promise.all([
        this.poll.startRail(),
        this.hub.onHub ? this.poll.held() : this.poll.read(),
      ]);
    } catch (trouble) {
      if (!this.threads.loaded && !unreachable(trouble)) throw trouble;
    }
    return this.threads;
  }

  redirect(threads: ThreadsService, transition: Transition): void {
    if (transition.to?.name !== 'conversations.index') return;
    const first = threads.railOrder[0];
    if (first) void this.router.replaceWith('conversations.detail', first);
  }

  activate(): void {
    this.poll.start();
    this.keys.push('board', this.boardKeys);
  }

  deactivate(): void {
    this.poll.stop();
    this.keys.drop(this.boardKeys);
  }
}
