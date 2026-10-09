import Service, { service } from '@ember/service';
import { tracked } from '@glimmer/tracking';
import { waitForPromise } from '@ember/test-waiters';
import type { DraftRequest } from 'frontend/services/drafts';
import { MOVED, tried } from 'frontend/data/tried';
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

const REFUSED = 'failed';

export default class BoardService extends Service {
  @service declare dialogDrafts: DialogDraftsService;
  @service('poll') declare loader: PollService;
  @service declare store: StoreService;
  @service declare threads: ThreadsService;
  @service declare toasts: ToastsService;
  @service declare here: HereService;
  @service declare terminal: TerminalService;
  @service declare router: RouterService;

  @tracked private acting: Record<string, string> = {};
  @tracked private decided: string | null = null;

  isActing(key: string): boolean {
    return key in this.acting;
  }

  doing(key: string): string | undefined {
    return this.acting[key];
  }

  isDecided = (key: string): boolean => this.decided === key;

  private async acted(
    key: string,
    decision: string,
    { verb, body }: Carried['request'],
    answered?: Answered,
  ): Promise<boolean> {
    const conversation = this.threads.thread(key);
    if (!conversation) return false;
    this.acting = { ...this.acting, [key]: decision };
    try {
      const done = await this.wrote(
        key,
        verb,
        conversation.etag,
        body,
        answered,
      );
      if (done) this.dialogDrafts.forget(key);
      return done;
    } finally {
      const rest = { ...this.acting };
      delete rest[key];
      this.acting = rest;
    }
  }

  private async wrote(
    key: string,
    verb: string,
    etag: string,
    body: Record<string, unknown>,
    answered?: Answered,
  ): Promise<boolean> {
    const pr = this.here.at;
    const written = await tried(
      'write',
      this.store.decide(pr, key, verb, etag, body),
    );
    if (!written.done) {
      this.toasts.say(written.why, REFUSED);
      if (written.code === MOVED) await this.loader.refreshList();
      return false;
    }
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
    const made = await tried(
      'write',
      this.store.createDraft(this.here.at, draft),
    );
    if (!made.done) {
      this.toasts.say(made.why, REFUSED);
      return null;
    }
    await this.loader.refreshList();
    return made.body;
  }
}
