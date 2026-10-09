import Modifier from 'ember-modifier';
import { registerDestructor } from '@ember/destroyable';
import { service } from '@ember/service';
import type KeysService from 'frontend/services/keys';
import type { Keymap } from 'frontend/services/keys';

const CONTROLS =
  'a[href], button, textarea, input, select, [tabindex]:not([tabindex="-1"])';
const FIELDS = 'textarea, input, select';

type Answer = (key: string) => boolean;

interface ModalSignature {
  Element: HTMLElement;
  Args: { Positional: [close: () => void, answer?: Answer] };
}

function controlsIn(element: HTMLElement): HTMLElement[] {
  return [...element.querySelectorAll<HTMLElement>(CONTROLS)].filter(
    (one) => !one.matches(':disabled'),
  );
}

export function focusFirstField(element: HTMLElement): void {
  const field = controlsIn(element).find((one) => one.matches(FIELDS));
  (field ?? element).focus();
}

function wrap(element: HTMLElement, event: KeyboardEvent): void {
  if (event.key !== 'Tab') return;
  const controls = controlsIn(element);
  const first = controls[0];
  const last = controls[controls.length - 1];
  if (!first || !last) return;
  const at = controls.indexOf(document.activeElement as HTMLElement);
  if (event.shiftKey && at <= 0) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && (at < 0 || at === controls.length - 1)) {
    event.preventDefault();
    first.focus();
  }
}

export default class Modal extends Modifier<ModalSignature> {
  @service declare keys: KeysService;

  private holding: HTMLElement | null = null;
  private close: () => void = () => undefined;
  private answer: Answer | undefined;

  private readonly keymap: Keymap = {
    take: (key) => {
      if (key !== 'Escape') return this.answer?.(key) ?? false;
      this.close();
      return true;
    },
  };

  modify(element: HTMLElement, [close, answer]: [() => void, Answer?]): void {
    this.close = close;
    this.answer = answer;
    this.keys.push('dialog', this.keymap);
    if (this.holding) return;
    this.holding = element;
    const before = document.activeElement;
    const trap = (event: KeyboardEvent) => wrap(element, event);
    element.addEventListener('keydown', trap);
    focusFirstField(element);
    registerDestructor(this, () => {
      element.removeEventListener('keydown', trap);
      this.keys.drop(this.keymap);
      if (before instanceof HTMLElement && before.isConnected) before.focus();
    });
  }
}
