import Route from '@ember/routing/route';
import { service } from '@ember/service';
import { unreachable } from 'frontend/data/refusal';
import type BoardKeysService from 'frontend/services/board-keys';
import type KeysService from 'frontend/services/keys';
import type PollService from 'frontend/services/poll';
import type ThemeService from 'frontend/services/theme';
import type ThreadsService from 'frontend/services/threads';

export default class BoardRoute extends Route {
  @service declare threads: ThreadsService;
  @service declare poll: PollService;
  @service declare keys: KeysService;
  @service('board-keys') declare boardKeys: BoardKeysService;
  @service declare theme: ThemeService;

  async model() {
    this.theme.restore();
    try {
      await this.poll.startRail();
    } catch (trouble) {
      if (!unreachable(trouble)) throw trouble;
    }
    return this.threads;
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
