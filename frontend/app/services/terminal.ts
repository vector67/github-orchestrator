import Service, { service } from '@ember/service';
import { tracked } from '@glimmer/tracking';
import { waitForPromise } from '@ember/test-waiters';
import type { TerminalSession } from 'frontend/data/api';
import { reportError } from 'frontend/data/report';
import { Session, type Colours } from 'frontend/data/terminal';
import { tried } from 'frontend/data/tried';
import { keyOf, type Numbered } from 'frontend/data/wall';
import type HereService from 'frontend/services/here';
import type StoreService from 'frontend/services/store';
import type ToastsService from 'frontend/services/toasts';
import { after, durationOf } from 'frontend/motion';

export type Reach = 'unknown' | 'answering' | 'unreachable';

const LOOK_EVERY_MS = 500;
const LOOK_FOR_MS = 15_000;
const RETRY_EVERY_MS = 1000;

function colours(): Colours {
  const style = getComputedStyle(document.documentElement);
  return {
    ground: style.getPropertyValue('--tty-ground').trim(),
    text: style.getPropertyValue('--tty-text').trim(),
  };
}

export default class TerminalService extends Service {
  @service declare here: HereService;
  @service declare store: StoreService;
  @service declare toasts: ToastsService;

  @tracked private held: Record<string, Session[]> = {};
  @tracked private chosen: Record<string, string> = {};
  @tracked reach: Reach = 'unknown';

  private looking: number | null = null;
  private retrying: number | null = null;
  private awaiting: string | null = null;

  get sessions(): Session[] {
    const pr = this.here.pr;
    return pr === null ? [] : (this.held[keyOf(pr)] ?? []);
  }

  get selected(): Session | null {
    const pr = this.here.pr;
    const id = pr === null ? undefined : this.chosen[keyOf(pr)];
    return this.sessions.find((one) => one.id === id && !one.leaving) ?? null;
  }

  select = (id: string): void => {
    const pr = this.here.pr;
    if (pr !== null) this.chosen = { ...this.chosen, [keyOf(pr)]: id };
  };

  selectIn = (worktree: string): void => {
    const found = this.sessions.find((one) => one.listed.worktree === worktree);
    if (found) this.select(found.id);
  };

  refresh(): Promise<string[]> {
    return waitForPromise(this.refreshed());
  }

  private async refreshed(): Promise<string[]> {
    const pr = this.here.pr;
    if (pr === null) return [];
    try {
      await this.store.readSessions(pr);
      this.reach = 'answering';
      return this.adopt(pr);
    } catch (trouble) {
      this.reach = 'unreachable';
      void reportError('terminal', trouble);
      return [];
    }
  }

  open(keys: string, line: string): Promise<boolean> {
    return waitForPromise(this.opened(keys, line));
  }

  private async opened(keys: string, line: string): Promise<boolean> {
    const pr = this.here.pr;
    if (pr === null) return false;
    const answer = await tried('terminal', this.store.openSession(pr, keys));
    if (!answer.done) {
      this.toasts.say(`${line} did not open: ${answer.why}`, 'failed');
      return false;
    }
    this.reach = 'answering';
    const fresh = this.adopt(pr);
    if (fresh.length === 0) {
      this.toasts.say(
        `${line} opened outside this page, where this pull request’s terminal is`,
        'done',
      );
      return false;
    }
    return true;
  }

  expect(): void {
    const pr = this.here.pr;
    const key = pr === null ? null : keyOf(pr);
    this.stopLooking();
    this.awaiting = key;
    const until = Date.now() + LOOK_FOR_MS;
    this.looking = setInterval(() => {
      const now = this.here.pr === null ? null : keyOf(this.here.pr);
      if (now !== key || Date.now() > until) this.stopLooking();
      else void this.refresh();
    }, LOOK_EVERY_MS);
  }

  willDestroy(): void {
    super.willDestroy();
    this.stopLooking();
    this.stopRetrying();
  }

  private lost = (): void => {
    if (this.retrying !== null) return;
    this.retrying = setInterval(() => {
      if (this.sessions.some((one) => one.standing === 'lost')) {
        void this.refresh();
      } else {
        this.stopRetrying();
      }
    }, RETRY_EVERY_MS);
  };

  close = (session: Session): Promise<void> =>
    waitForPromise(this.closing(session));

  private async closing(session: Session): Promise<void> {
    session.close();
    for (const [key, sessions] of Object.entries(this.held)) {
      if (!sessions.includes(session)) continue;
      const left = sessions.filter((one) => one !== session);
      if (this.chosen[key] === session.id && left.length) {
        this.chosen = { ...this.chosen, [key]: left.at(-1)!.id };
      }
    }
    await after(durationOf('in'));
    for (const [key, sessions] of Object.entries(this.held)) {
      if (!sessions.includes(session)) continue;
      this.held = {
        ...this.held,
        [key]: sessions.filter((one) => one !== session),
      };
    }
  }

  private stopRetrying(): void {
    if (this.retrying !== null) clearInterval(this.retrying);
    this.retrying = null;
  }

  private stopLooking(): void {
    if (this.looking !== null) clearInterval(this.looking);
    this.looking = null;
    this.awaiting = null;
  }

  private adopt(pr: Numbered): string[] {
    const key = keyOf(pr);
    const { sessions } = this.store.manager(pr);
    const known = this.held[key] ?? [];
    for (const one of known.filter((held) => held.standing === 'lost')) {
      if (sessions.some((listed) => listed.id === one.id)) one.resume();
      else one.gone();
    }
    const fresh = sessions
      .filter((listed) => !known.some((one) => one.id === listed.id))
      .map((listed) => this.connect(listed));
    if (!fresh.length) return [];
    this.held = { ...this.held, [key]: [...known, ...fresh] };
    this.select(fresh.at(-1)!.id);
    if (this.awaiting === key) this.stopLooking();
    return fresh.map((one) => one.id);
  }

  private connect(listed: TerminalSession): Session {
    return new Session(listed, this.addressOf(listed.id), colours(), this.lost);
  }

  private addressOf(id: string): string {
    const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
    const path = this.here.api(
      `/api/terminal/sessions/${encodeURIComponent(id)}`,
    );
    return `${scheme}://${location.host}${path}`;
  }
}
