import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import { fn } from '@ember/helper';
import showsSession from 'frontend/modifiers/shows-session';
import type { Session } from 'frontend/data/terminal';
import type DashboardService from 'frontend/services/dashboard';
import type TerminalService from 'frontend/services/terminal';

interface Launcher {
  keys: string;
  does: string;
  counts: boolean;
}

function launcher(keys: string, does: string, counts = false) {
  return { keys, does, counts };
}

const LAUNCHERS: Launcher[] = [
  launcher('new', 'Shell in the worktree'),
  launcher('a', 'git add -p'),
  launcher('c', 'git commit'),
  launcher('i', 'git rebase -i HEAD~N', true),
  launcher('r', 'rebase-on-main in an agent session, steered by you'),
];

const DEFAULT_COUNT = '3';
const COUNT = /^[1-9]\d*$/;

const ONLY_ONE_THING = 'The terminal runs in the manager’s board, which';

export default class TerminalTab extends Component {
  @service declare terminal: TerminalService;
  @service declare dashboard: DashboardService;

  @tracked askingCount = false;
  @tracked count = DEFAULT_COUNT;

  get launchers(): Launcher[] {
    return LAUNCHERS;
  }

  get sessions(): Session[] {
    return this.terminal.sessions;
  }

  get selected(): Session | null {
    return this.terminal.selected;
  }

  get standing(): string | null {
    if (this.terminal.reach === 'unreachable' && !this.sessions.length) {
      return this.dashboard.shown?.drawn.frozen
        ? `${ONLY_ONE_THING} is down while the worktree is frozen.`
        : `${ONLY_ONE_THING} is not answering.`;
    }
    if (!this.selected) {
      return 'No session yet. Start one from the list on the left.';
    }
    return null;
  }

  get lost(): boolean {
    return this.selected?.standing === 'lost';
  }

  get exited(): Session | null {
    const selected = this.selected;
    return selected?.standing === 'exited' ? selected : null;
  }

  isSelected = (one: Session): boolean => one === this.selected;

  launch = (one: Launcher) => {
    if (one.counts) this.askingCount = true;
    else void this.terminal.open(one.keys, one.does);
  };

  asksHere = (one: Launcher): boolean => one.counts && this.askingCount;

  noteCount = (event: Event) => {
    this.count = (event.target as HTMLInputElement).value;
  };

  leave = () => {
    document
      .querySelector<HTMLElement>('#terminal .sess[aria-current="true"]')
      ?.focus();
  };

  rebase = (event: Event) => {
    event.preventDefault();
    if (!COUNT.test(this.count)) return;
    this.askingCount = false;
    void this.terminal.open(
      `i${this.count}`,
      `git rebase -i HEAD~${this.count}`,
    );
  };

  <template>
    <main id="terminal" class="term" data-test-terminal>
      <aside class="term-side">
        <h2 class="h">Sessions</h2>
        {{#each this.sessions key="id" as |one|}}
          <button
            type="button"
            class="sess {{if (this.isSelected one) 'on'}}"
            aria-current={{if (this.isSelected one) "true"}}
            data-leaving={{if one.leaving "true"}}
            data-test-session={{one.id}}
            {{on "click" (fn this.terminal.select one.id)}}
          ><b data-test-session-command>{{one.command}}</b><span
              class="where"
              data-test-session-where
            >{{one.worktree}}</span>{{#if one.said}}<span
                class="said"
                data-test-session-standing
              >{{one.said}}</span>{{/if}}</button>
        {{/each}}
        <h2 class="h">Start</h2>
        {{#each this.launchers key="keys" as |one|}}
          {{#if (this.asksHere one)}}
            <form class="launch count" {{on "submit" this.rebase}}>
              <span><label>git rebase -i HEAD~<input
                    type="number"
                    min="1"
                    value={{this.count}}
                    data-test-rebase-count
                    {{on "input" this.noteCount}}
                  /></label>
                <button
                  type="submit"
                  class="btn"
                  data-test-rebase-open
                >Open</button></span>
            </form>
          {{else}}
            <button
              type="button"
              class="launch"
              data-test-launch={{one.keys}}
              {{on "click" (fn this.launch one)}}
            ><span class="does">{{one.does}}</span></button>
          {{/if}}
        {{/each}}
        <p class="note">A real pty in this PR’s worktree. The board’s “Open a
          session” starts its steered agent session here.</p>
        <p class="note" data-test-terminal-leave>Ctrl+Shift+← leaves the
          terminal for this list.</p>
      </aside>
      <section class="tty" data-test-screen>
        {{#if this.lost}}
          <p class="tty-lost" role="status" data-test-terminal-lost>
            Lost connection with the board, please wait. Your terminal session
            is not lost.
          </p>
        {{/if}}
        {{#if this.standing}}
          <p class="tty-standing" data-test-terminal-standing>
            {{this.standing}}
          </p>
        {{/if}}
        {{#if this.selected}}
          <div class="tty-host" {{showsSession this.selected this.leave}}></div>
        {{/if}}
        {{#if this.exited}}
          <div class="tty-exit" role="status" data-test-terminal-exit>
            <span>Exited with code {{this.exited.exitCode}}</span>
            <button
              type="button"
              class="btn"
              data-test-terminal-close
              {{on "click" (fn this.terminal.close this.exited)}}
            >Close</button>
          </div>
        {{/if}}
      </section>
    </main>
  </template>
}
