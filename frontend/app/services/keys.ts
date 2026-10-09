import Service from '@ember/service';
import { tracked } from '@glimmer/tracking';

const TYPING = new Set(['INPUT', 'TEXTAREA', 'SELECT']);
const STAY_IN_HELP = new Set(['Tab', 'Shift']);
const ONCE_PER_PRESS = new Set(['Enter', 'o']);

type Layer = 'dialog' | 'screen' | 'tab' | 'board';

const LAYERS: Layer[] = ['dialog', 'screen', 'tab', 'board'];

export interface Keymap {
  take?(key: string): boolean;
  otherwise?(key: string): boolean;
}

interface Pushed {
  layer: Layer;
  keymap: Keymap;
}

export function stepped<T>(order: T[], at: number, by: number): T | undefined {
  if (at < 0) return order[0];
  return order[Math.max(0, Math.min(order.length - 1, at + by))];
}

export default class KeysService extends Service {
  private listening: ((event: KeyboardEvent) => void) | null = null;
  private pushed: Pushed[] = [];

  @tracked helping = false;

  listen(): void {
    if (this.listening) return;
    this.listening = (event: KeyboardEvent) => this.handle(event);
    document.addEventListener('keydown', this.listening);
    document.addEventListener('keyup', this.releaseSlash);
    window.addEventListener('blur', this.hideShortcuts);
  }

  willDestroy(): void {
    super.willDestroy();
    if (this.listening) document.removeEventListener('keydown', this.listening);
    document.removeEventListener('keyup', this.releaseSlash);
    window.removeEventListener('blur', this.hideShortcuts);
    this.hideShortcuts();
    this.listening = null;
  }

  private releaseSlash = (event: KeyboardEvent): void => {
    if (event.key === '/') this.hideShortcuts();
  };

  private hideShortcuts = (): void => {
    delete document.documentElement.dataset['shortcuts'];
  };

  push(layer: Layer, keymap: Keymap): void {
    if (this.pushed.some((one) => one.keymap === keymap)) return;
    this.pushed = [...this.pushed, { layer, keymap }];
  }

  drop(keymap: Keymap): void {
    this.pushed = this.pushed.filter((one) => one.keymap !== keymap);
  }

  private on(layer: Layer): Keymap[] {
    return this.pushed
      .filter((one) => one.layer === layer)
      .map((one) => one.keymap)
      .reverse();
  }

  private handle(event: KeyboardEvent): void {
    const dialogs = this.on('dialog');
    if (event.key === 'Escape' && dialogs[0]) {
      event.preventDefault();
      dialogs[0].take?.(event.key);
      return;
    }
    const target = event.target as HTMLElement | null;
    if (target && TYPING.has(target.tagName)) return;
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    if (event.repeat && ONCE_PER_PRESS.has(event.key)) return;
    if (event.key === '/') {
      event.preventDefault();
      document.documentElement.dataset['shortcuts'] = '';
      return;
    }
    if (this.helping) {
      if (STAY_IN_HELP.has(event.key)) return;
      event.preventDefault();
      this.helping = false;
      return;
    }
    if (event.key === '?' && !dialogs.length) {
      event.preventDefault();
      this.helping = true;
      return;
    }
    const offered = dialogs.length
      ? dialogs
      : LAYERS.flatMap((layer) => this.on(layer));
    const taken =
      offered.some((one) => one.take?.(event.key)) ||
      offered.some((one) => one.otherwise?.(event.key));
    if (taken) event.preventDefault();
  }
}
