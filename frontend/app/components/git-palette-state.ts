import { tracked } from '@glimmer/tracking';
import type { GitRun } from 'frontend/data/api';
import {
  FORCE_PUSH,
  isValidPrefix,
  lineOf,
  resolve,
  type GitCommand,
} from 'frontend/data/git';
import type { Tried } from 'frontend/data/tried';
import type { Keymap } from 'frontend/services/keys';

interface Ran {
  command: string;
  answer: GitRun | null;
  failed: string | null;
}

interface PaletteHands {
  run(keys: string): Promise<Tried<GitRun>>;
  openInTerminal(keys: string, line: string): Promise<void>;
  say(text: string, tone: 'done' | 'failed'): void;
  opened(keymap: Keymap): void;
  closed(keymap: Keymap): void;
}

export default class GitPaletteState {
  @tracked buffer: string | null = null;
  @tracked forceAsked = false;
  @tracked running = false;
  @tracked ran: Ran | null = null;

  readonly keymap: Keymap = {
    take: (key) => {
      if (key !== 'Escape') return this.takes(key);
      this.close();
      return true;
    },
  };

  constructor(private readonly hands: PaletteHands) {}

  get isOpen(): boolean {
    return this.buffer !== null || this.ran !== null;
  }

  get typed(): string {
    return this.buffer ?? '';
  }

  get chosen(): GitCommand | null {
    return this.buffer === null ? null : resolve(this.buffer);
  }

  get footer(): string {
    const chosen = this.chosen;
    if (this.running && chosen)
      return `running: ${lineOf(chosen, this.typed)} …`;
    if (!chosen) return 'Esc cancel';
    const line = lineOf(chosen, this.typed);
    if (chosen.where === 'terminal') {
      return `will open: ${line} in the Terminal tab · Enter open · Esc cancel`;
    }
    if (this.forceAsked) {
      return 'Force-push with lease replaces the branch on GitHub with this worktree’s. Enter again to force-push · Esc cancel';
    }
    return `will run: ${line} · Enter run · Esc cancel`;
  }

  get runLabel(): string | null {
    const chosen = this.chosen;
    if (!chosen) return null;
    if (chosen.where === 'terminal') return 'Open';
    if (this.forceAsked) return 'Force-push';
    return chosen.where === 'shown' ? 'Show' : 'Run';
  }

  open = (keys = ''): void => {
    this.ran = null;
    this.forceAsked = false;
    this.buffer = keys;
    this.hands.opened(this.keymap);
  };

  close = (): void => {
    this.buffer = null;
    this.ran = null;
    this.forceAsked = false;
    this.hands.closed(this.keymap);
  };

  choose = (keys: string): void => {
    this.buffer = keys;
    this.forceAsked = false;
  };

  run = (): void => {
    const chosen = this.chosen;
    if (!chosen || this.running) return;
    const keys = this.typed;
    const line = lineOf(chosen, keys);
    if (chosen.where === 'terminal') {
      this.close();
      void this.hands.openInTerminal(keys, line);
      return;
    }
    if (chosen.keys === FORCE_PUSH && !this.forceAsked) {
      this.forceAsked = true;
      return;
    }
    void this.runGit(chosen, line);
  };

  private takes(key: string): boolean {
    if (this.running) return true;
    if (this.ran) {
      this.close();
      return true;
    }
    if (key === 'Enter') this.run();
    else if (key === 'Backspace') this.choose(this.typed.slice(0, -1));
    else if (key.length === 1) {
      const next = this.typed + key;
      if (isValidPrefix(next)) this.choose(next);
      else this.close();
    }
    return true;
  }

  private async runGit(chosen: GitCommand, line: string): Promise<void> {
    this.running = true;
    const run = await this.hands.run(chosen.keys);
    const ran: Ran = run.done
      ? { command: line, answer: run.body, failed: null }
      : {
          command: line,
          answer: null,
          failed: `${line} did not run: ${run.why}`,
        };
    this.running = false;
    this.forceAsked = false;
    if (this.buffer === null) {
      this.hands.say(
        ran.answer
          ? `${line}: exit ${ran.answer.exit_code}`
          : (ran.failed ?? line),
        ran.answer?.exit_code === 0 ? 'done' : 'failed',
      );
      return;
    }
    this.buffer = null;
    this.ran = ran;
  }
}
