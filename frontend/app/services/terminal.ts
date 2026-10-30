import Service, { service } from '@ember/service';
import { tracked } from '@glimmer/tracking';
import { waitForPromise } from '@ember/test-waiters';
import type { TerminalSession } from 'frontend/data/api';
import { reportError } from 'frontend/data/report';
import { Session } from 'frontend/data/terminal';
import {
  DARK_THEMES,
  LIGHT_THEMES,
  schemeOf,
  type NamedTheme,
} from 'frontend/data/terminal-themes';
import type { Tried } from 'frontend/data/tried';
import { keyOf, type Numbered } from 'frontend/data/wall';
import type HereService from 'frontend/services/here';
import type StoreService from 'frontend/services/store';
import type { Summaries } from 'frontend/services/store';
import type { Pressed, Pressings } from 'frontend/data/decisions';
import type ToastsService from 'frontend/services/toasts';
import { after, durationOf } from 'frontend/motion';

export type Reach = 'unknown' | 'answering' | 'unreachable';

const LOOK_EVERY_MS = 500;
const RETRY_EVERY_MS = 1000;

export type TerminalTheme = 'system' | 'light' | 'dark';

export const TERMINAL_THEMES: TerminalTheme[] = ['system', 'light', 'dark'];

const REMEMBERED_THEME = 'terminal-theme';
const REMEMBERED_LIGHT = 'terminal-light-theme';
const REMEMBERED_DARK = 'terminal-dark-theme';

const LIGHT_SYSTEM = window.matchMedia('(prefers-color-scheme: light)');

function recalled<T extends string>(key: string, among: T[], fallback: T): T {
  try {
    const kept = localStorage.getItem(key);
    return among.find((one) => one === kept) ?? fallback;
  } catch {
    return fallback;
  }
}

function keep(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    return;
  }
}

const keysOf = (themes: NamedTheme[]) => themes.map((one) => one.key);

export default class TerminalService extends Service {
  @service declare here: HereService;
  @service declare store: StoreService;
  @service declare toasts: ToastsService;

  @tracked private held: Record<string, Session[]> = {};
  @tracked private chosen: Record<string, string> = {};
  @tracked reach: Reach = 'unknown';
  @tracked theme: TerminalTheme = recalled(
    REMEMBERED_THEME,
    TERMINAL_THEMES,
    'system',
  );
  @tracked lightTheme = recalled(
    REMEMBERED_LIGHT,
    keysOf(LIGHT_THEMES),
    'default-light',
  );
  @tracked darkTheme = recalled(
    REMEMBERED_DARK,
    keysOf(DARK_THEMES),
    'default-dark',
  );
  @tracked private systemLight = LIGHT_SYSTEM.matches;

  private looking: number | null = null;
  private retrying: number | null = null;

  constructor(...args: ConstructorParameters<typeof Service>) {
    super(...args);
    LIGHT_SYSTEM.addEventListener('change', this.followSystem);
  }

  get light(): boolean {
    return this.theme === 'system' ? this.systemLight : this.theme === 'light';
  }

  get scheme(): string {
    return this.light ? this.lightTheme : this.darkTheme;
  }

  chooseTheme(theme: TerminalTheme): void {
    this.theme = theme;
    this.repaint();
    keep(REMEMBERED_THEME, theme);
  }

  chooseLightTheme(key: string): void {
    this.lightTheme = key;
    this.repaint();
    keep(REMEMBERED_LIGHT, key);
  }

  chooseDarkTheme(key: string): void {
    this.darkTheme = key;
    this.repaint();
    keep(REMEMBERED_DARK, key);
  }

  private followSystem = (event: MediaQueryListEvent): void => {
    this.systemLight = event.matches;
    this.repaint();
  };

  private repaint(): void {
    for (const sessions of Object.values(this.held)) {
      for (const one of sessions) one.paint(schemeOf(this.scheme));
    }
  }

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

  selectIn = (worktree: string): boolean => {
    const found = this.sessions.find((one) => one.listed.worktree === worktree);
    if (found) this.select(found.id);
    return found !== undefined;
  };

  goTo(key: string, worktree: string | null): Promise<void> {
    return waitForPromise(this.going(key, worktree));
  }

  private async going(key: string, worktree: string | null): Promise<void> {
    const pr = this.here.pr;
    await this.refresh();
    if (pr === null || worktree === null || this.selectIn(worktree)) return;
    this.toasts.say(
      'The session this comment expected is not in the Terminal tab; checking what happened',
      'failed',
    );
    const checked = await this.store.checkSession(pr, key);
    if (!checked.done) {
      this.toasts.say(checked.why, 'failed');
    } else if (checked.body === null) {
      this.toasts.say(
        'No session was running, so the comment is back where it was before the session opened',
        'done',
      );
    } else {
      await this.refresh();
      this.select(checked.body);
    }
  }

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

  private get summary(): Summaries | null {
    const pr = this.here.pr;
    return pr === null ? null : this.store.summary(pr.repo, pr.number);
  }

  get pressing(): Pressings | null {
    return this.summary?.pressing ?? null;
  }

  get opening(): Pressed | null {
    return this.summary?.opening ?? null;
  }

  open(keys: string, line: string): Promise<boolean> {
    return waitForPromise(
      this.opened((pr) => this.store.openSession(pr, keys), line),
    );
  }

  ask(prompt: string, about: string | null): Promise<boolean> {
    return waitForPromise(
      this.opened(
        (pr) => this.store.askTheAgent(pr, prompt, about),
        'The question for the agent',
      ),
    );
  }

  private async opened(
    start: (pr: Numbered) => Promise<Tried<unknown>>,
    line: string,
  ): Promise<boolean> {
    const pr = this.here.pr;
    if (pr === null) return false;
    const answer = await start(pr);
    if (!answer.done) return false;
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
    this.looking = setInterval(() => {
      const now = this.here.pr === null ? null : keyOf(this.here.pr);
      if (now !== key || !this.opening?.pending) this.stopLooking();
      else void this.refresh();
    }, LOOK_EVERY_MS);
  }

  willDestroy(): void {
    super.willDestroy();
    LIGHT_SYSTEM.removeEventListener('change', this.followSystem);
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
    return fresh.map((one) => one.id);
  }

  private connect(listed: TerminalSession): Session {
    return new Session(
      listed,
      this.addressOf(listed.id),
      schemeOf(this.scheme),
      this.lost,
    );
  }

  private addressOf(id: string): string {
    const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
    const path = this.here.api(
      `/api/terminal/sessions/${encodeURIComponent(id)}`,
    );
    return `${scheme}://${location.host}${path}`;
  }
}
