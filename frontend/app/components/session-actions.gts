import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import { fn } from '@ember/helper';
import { waitForPromise } from '@ember/test-waiters';
import type RouterService from '@ember/routing/router-service';
import actionsMenu from 'frontend/modifiers/actions-menu';
import type { WatchedSession } from 'frontend/data/api';
import { copyBranch, copyDirectory } from 'frontend/data/address';
import type KeysService from 'frontend/services/keys';
import type StoreService from 'frontend/services/store';
import type ToastsService from 'frontend/services/toasts';

export interface SessionActionsSignature {
  Args: {
    one: WatchedSession;
    command: string;
    fullscreen: (one: WatchedSession) => void;
    close: (one: WatchedSession) => void;
  };
}

interface Action {
  id: string;
  label: string;
  offered: boolean;
  run: () => unknown;
}

export default class SessionActions extends Component<SessionActionsSignature> {
  @service declare router: RouterService;
  @service declare store: StoreService;
  @service declare keys: KeysService;
  @service declare toasts: ToastsService;

  @tracked acting = false;

  get actions(): Action[] {
    const { one } = this.args;
    const board = one.board_url;
    const thread = one.thread;
    const branch = one.branch;
    return [
      {
        id: 'open-pr',
        label: 'Open pull request',
        offered: true,
        run: () => this.go(board),
      },
      {
        id: 'open-diff',
        label: 'Open diff',
        offered: true,
        run: () => this.go(`${board}/diff`),
      },
      {
        id: 'open-tab',
        label: 'Open in Terminal tab',
        offered: true,
        run: () =>
          this.go(`${board}/terminal?session=${encodeURIComponent(one.id)}`),
      },
      {
        id: 'fullscreen',
        label: 'Fullscreen',
        offered: true,
        run: () => this.args.fullscreen(one),
      },
      {
        id: 'new-shell',
        label: 'New shell here',
        offered: true,
        run: () => this.newShell(),
      },
      {
        id: 'copy-path',
        label: 'Copy worktree path',
        offered: true,
        run: async () =>
          this.toasts.say(await copyDirectory(one.worktree), 'done'),
      },
      {
        id: 'copy-branch',
        label: 'Copy branch name',
        offered: branch !== null,
        run: async () =>
          branch && this.toasts.say(await copyBranch(branch), 'done'),
      },
      {
        id: 'open-thread',
        label: 'Open conversation',
        offered: thread !== null,
        run: () =>
          thread &&
          this.go(`${board}/conversations/${encodeURIComponent(thread)}`),
      },
      {
        id: 'close',
        label: 'Close',
        offered: true,
        run: () => this.args.close(one),
      },
    ];
  }

  toggle = (): void => {
    this.acting = !this.acting;
  };

  leave = (): void => {
    this.acting = false;
  };

  pick = (action: Action): void => {
    this.acting = false;
    void waitForPromise(Promise.resolve(action.run()));
  };

  private go(url: string): void {
    void this.router.transitionTo(url);
  }

  private async newShell(): Promise<void> {
    const answer = await this.store.openShellBeside(this.args.one);
    if (answer.done) {
      this.toasts.say(`Opened a shell beside ${this.args.command}`, 'done');
    } else {
      this.toasts.say(`No shell opened: ${answer.why}`, 'failed');
    }
  }

  <template>
    <button
      type="button"
      class="row-more watched-more"
      aria-label="Actions for this session"
      aria-haspopup="menu"
      aria-expanded={{if this.acting "true" "false"}}
      data-test-watched-more
      {{on "click" this.toggle}}
    >▾</button>
    {{#if this.acting}}
      <div
        class="row-actions"
        popover="manual"
        role="menu"
        data-test-watched-actions
        {{actionsMenu ".watched-more" this.keys this.leave}}
      >
        {{#each this.actions key="id" as |item|}}
          <button
            type="button"
            class="row-action"
            role="menuitem"
            disabled={{if item.offered false true}}
            data-test-watched-action={{item.id}}
            {{on "click" (fn this.pick item)}}
          >{{item.label}}</button>
        {{/each}}
      </div>
    {{/if}}
  </template>
}
