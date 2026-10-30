import Service, { service } from '@ember/service';
import { tracked } from '@glimmer/tracking';
import { waitForPromise } from '@ember/test-waiters';
import type { DraftRequest } from 'frontend/services/drafts';
import { MOVED } from 'frontend/data/tried';
import { after, durationOf, flip } from 'frontend/motion';
import {
  carriedOut,
  type Carried,
  type Gathered,
} from 'frontend/data/decisions';
import type RouterService from '@ember/routing/router-service';
import type DialogDraftsService from 'frontend/services/dialog-drafts';
import type PollService from 'frontend/services/poll';
import type StoreService from 'frontend/services/store';
import type TerminalService from 'frontend/services/terminal';
import type ThreadsService from 'frontend/services/threads';
import type HereService from 'frontend/services/here';
import type ToastsService from 'frontend/services/toasts';

type Answered = () => Promise<void>;

export default class BoardService extends Service {
  @service declare dialogDrafts: DialogDraftsService;
  @service('poll') declare loader: PollService;
  @service declare store: StoreService;
  @service declare threads: ThreadsService;
  @service declare toasts: ToastsService;
  @service declare here: HereService;
  @service declare terminal: TerminalService;
  @service declare router: RouterService;

  @tracked private decided: string | null = null;

  isDecided = (key: string): boolean => this.decided === key;

  private async acted(
    key: string,
    decision: string,
    { verb, body }: Carried['request'],
    answered?: Answered,
  ): Promise<boolean> {
    const conversation = this.threads.thread(key);
    if (!conversation) return false;
    const written = await this.store.decide(
      this.here.at,
      key,
      decision,
      verb,
      conversation.etag,
      body,
    );
    if (!written.done) {
      if (written.code === MOVED) await this.loader.refreshList();
      return false;
    }
    this.dialogDrafts.forget(key);
    await answered?.();
    await flip(() => {
      written.body();
      this.decided = key;
    });
    await this.loader.refreshList();
    void after(durationOf('flash')).then(() => {
      if (this.decided === key) this.decided = null;
    });
    return true;
  }

  private async queued(text: string, square: string): Promise<void> {
    await after(durationOf('rest'));
    this.toasts.say(text, square);
  }

  async decide(
    key: string,
    decision: Parameters<typeof carriedOut>[0],
    gathered: Gathered = {},
    answered?: Answered,
  ): Promise<boolean> {
    const { request, toast, opensTerminal } = carriedOut(decision, gathered);
    const acted = this.acted(key, decision, request, answered);
    if (!(await waitForPromise(acted))) return false;
    if (opensTerminal) {
      this.terminal.expect();
      void this.router.transitionTo('terminal');
    }
    if (toast) void this.queued(toast.text, toast.square);
    return true;
  }

  createDraft(draft: DraftRequest): Promise<string | null> {
    return waitForPromise(this.created(draft));
  }

  private async created(draft: DraftRequest): Promise<string | null> {
    const made = await this.store.createDraft(this.here.at, draft);
    if (made) await this.loader.refreshList();
    return made;
  }
}
