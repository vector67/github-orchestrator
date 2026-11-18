import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import { fn } from '@ember/helper';
import AreYouSure from 'frontend/components/are-you-sure';
import HubBar from 'frontend/components/hub-bar';
import showsSession from 'frontend/modifiers/shows-session';
import type { WatchedSession } from 'frontend/data/api';
import { elapsedOf } from 'frontend/data/dashboard';
import type { AreYouSure as Asking } from 'frontend/data/decisions';
import type { Session } from 'frontend/data/terminal';
import type HubService from 'frontend/services/hub';
import type StoreService from 'frontend/services/store';
import type TerminalService from 'frontend/services/terminal';
import type ToastsService from 'frontend/services/toasts';

const SAID: Record<WatchedSession['activity'], string> = {
  waiting: 'waiting for you',
  working: 'working',
  idle: 'idle',
};

const TONES: Record<WatchedSession['activity'], string> = {
  waiting: 'tone-strong',
  working: 'tone-plain',
  idle: 'tone-quiet',
};

const CLOSING: Asking = {
  label: 'Close',
  question: 'Close this terminal session?',
  consequence:
    'Its command is hung up, as when its pull request closes, and whatever it has not saved is lost.',
};

interface Row {
  one: WatchedSession;
  key: string;
  pr: string;
  command: string;
  open: string;
  said: string;
  tone: string;
}

function keyOf(one: WatchedSession): string {
  return `${one.board_url} ${one.id}`;
}

export default class TerminalsPage extends Component {
  @service declare hub: HubService;
  @service declare store: StoreService;
  @service declare terminal: TerminalService;
  @service declare toasts: ToastsService;

  @tracked shown: { key: string; session: Session } | null = null;
  @tracked closing: WatchedSession | null = null;

  get rows(): Row[] {
    return (this.store.watchedSessions ?? []).map((one) => ({
      one,
      key: keyOf(one),
      pr: `${one.repo}#${one.number}`,
      command: one.argv.join(' '),
      open: `open ${elapsedOf(one.started_at, this.hub.now)}`,
      said: SAID[one.activity],
      tone: TONES[one.activity],
    }));
  }

  get selected(): Session | null {
    const shown = this.shown;
    if (!shown) return null;
    return this.rows.some((row) => row.key === shown.key)
      ? shown.session
      : null;
  }

  isSelected = (row: Row): boolean => row.key === this.shown?.key;

  open = (row: Row) => {
    this.shown = { key: row.key, session: this.terminal.watch(row.one) };
  };

  leave = () => {
    document
      .querySelector<HTMLElement>('#terminals .sess[aria-current="true"]')
      ?.focus();
  };

  askToClose = (one: WatchedSession) => {
    this.closing = one;
  };

  cancel = () => {
    this.closing = null;
  };

  get asking(): Asking {
    return CLOSING;
  }

  confirm = async () => {
    const one = this.closing;
    this.closing = null;
    if (!one) return;
    const answer = await this.store.closeTerminalSession(one);
    if (!answer.done) {
      this.toasts.say(`The session did not close: ${answer.why}`, 'failed');
      return;
    }
    const shown = this.shown;
    if (shown?.key === keyOf(one)) {
      this.shown = null;
      void this.terminal.close(shown.session);
    }
  };

  <template>
    <div id="terminals" data-test-terminals>
      <HubBar @on="terminals" />
      <main class="terminals-split">
        <aside class="term-side">
          {{#each this.rows key="key" as |row|}}
            <div
              class="watched"
              data-test-watched={{row.one.id}}
              data-test-activity={{row.one.activity}}
            >
              <button
                type="button"
                class="sess {{if (this.isSelected row) 'on'}}"
                aria-current={{if (this.isSelected row) "true"}}
                {{on "click" (fn this.open row)}}
              ><span class="watched-head"><span
                    class="state-chip {{row.tone}}"
                    data-test-watched-activity
                  >{{row.said}}</span><span
                    class="where"
                    data-test-watched-pr
                  >{{row.pr}}</span></span><b
                  data-test-watched-command
                >{{row.command}}</b><span
                  class="where"
                  data-test-watched-open
                >{{row.open}}</span></button>
              <button
                type="button"
                class="btn watched-close"
                data-test-watched-close={{row.one.id}}
                {{on "click" (fn this.askToClose row.one)}}
              >Close</button>
            </div>
          {{else}}
            <p class="note" data-test-terminals-empty>No terminal session is
              open.</p>
          {{/each}}
        </aside>
        <section
          class="tty"
          data-tty-theme={{if this.terminal.light "light" "dark"}}
          data-tty-scheme={{this.terminal.scheme}}
          data-test-screen
        >
          {{#if this.selected}}
            <div
              class="tty-host"
              {{showsSession this.selected this.leave}}
            ></div>
          {{else}}
            <p class="tty-standing" data-test-terminal-standing>
              Choose a session from the list on the left.
            </p>
          {{/if}}
        </section>
      </main>
      {{#if this.closing}}
        <AreYouSure
          @asking={{this.asking}}
          @confirm={{this.confirm}}
          @cancel={{this.cancel}}
        />
      {{/if}}
    </div>
  </template>
}
