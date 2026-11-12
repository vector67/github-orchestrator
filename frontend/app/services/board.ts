import Service, { service } from '@ember/service';
import { tracked } from '@glimmer/tracking';
import { waitForPromise } from '@ember/test-waiters';
import type { ChangeRequest, DraftRequest } from 'frontend/services/drafts';
import { MOVED } from 'frontend/data/tried';
import { after, durationOf, flip } from 'frontend/motion';
import {
  carriedOut,
  undoOf,
  type Carried,
  type Decision,
  type Gathered,
  type Undo,
} from 'frontend/data/decisions';
import { busy } from 'frontend/data/thread';
import type { Conversation } from 'frontend/data/api';
import type RouterService from '@ember/routing/router-service';
import type DialogDraftsService from 'frontend/services/dialog-drafts';
import type PollService from 'frontend/services/poll';
import type StoreService from 'frontend/services/store';
import type TerminalService from 'frontend/services/terminal';
import type ThreadsService from 'frontend/services/threads';
import type HereService from 'frontend/services/here';
import type ToastsService from 'frontend/services/toasts';
import type { ToastUndo } from 'frontend/services/toasts';

const SETTLING_MS = 500;

const SETTLING_TRIES = 40;

const NOT_MOVED_YET = 'Not undone: the card has not moved yet.';

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

  private async queued(
    text: string,
    square: string,
    undo: ToastUndo | null,
  ): Promise<void> {
    await after(durationOf('rest'));
    this.toasts.say(text, square, undo);
  }

  private undoing(from: Conversation | undefined, undo: Undo | null) {
    if (!from || !undo) return null;
    return {
      label: undo.label,
      run: () => void this.undone(from, undo.decision),
    };
  }

  private async undone(from: Conversation, decision: Decision): Promise<void> {
    if (await this.movedOn(from)) {
      await this.decide(from.key, decision);
      return;
    }
    this.toasts.say(NOT_MOVED_YET, 'failed');
  }

  private async movedOn(from: Conversation): Promise<boolean> {
    for (let tries = 0; tries < SETTLING_TRIES; tries += 1) {
      const now = this.threads.thread(from.key);
      if (!now) return false;
      if (!busy(now) && now.state !== from.state) return true;
      await after(SETTLING_MS);
      await this.loader.refreshList();
    }
    return false;
  }

  async decide(
    key: string,
    decision: Parameters<typeof carriedOut>[0],
    gathered: Gathered = {},
    answered?: Answered,
  ): Promise<boolean> {
    const { request, toast, opensTerminal } = carriedOut(decision, gathered);
    const before = this.threads.thread(key);
    const undo = this.undoing(
      before,
      before ? undoOf(decision, before, gathered) : null,
    );
    const acted = this.acted(key, decision, request, answered);
    if (!(await waitForPromise(acted))) return false;
    if (opensTerminal) {
      this.terminal.expect();
      void this.router.transitionTo('terminal');
    }
    if (toast) void this.queued(toast.text, toast.square, undo);
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

  async requestChange(request: ChangeRequest): Promise<boolean> {
    const made = await waitForPromise(
      this.store.requestChange(this.here.at, request),
    );
    if (!made) return false;
    if (request.visible) {
      this.terminal.expect();
      void this.router.transitionTo('terminal');
    }
    await waitForPromise(this.loader.refreshList());
    return true;
  }
}
