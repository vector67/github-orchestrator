import { modifier } from 'ember-modifier';
import type KeysService from 'frontend/services/keys';
import type { Keymap } from 'frontend/services/keys';

const EDGE = 8;
const GAP = 4;

export default modifier(
  (
    element: HTMLElement,
    [arrowSelector, keys, close]: [string, KeysService, () => void],
  ) => {
    const arrow = element.parentElement!.querySelector(arrowSelector)!;
    const by = arrow.getBoundingClientRect();
    element.showPopover();
    const below = by.bottom + GAP;
    const fitsBelow = below + element.offsetHeight <= window.innerHeight - EDGE;
    const top = fitsBelow ? below : by.top - GAP - element.offsetHeight;
    element.style.top = `${Math.max(EDGE, top)}px`;
    const room = window.innerWidth - element.offsetWidth - EDGE;
    element.style.left = `${Math.max(EDGE, Math.min(by.right - element.offsetWidth, room))}px`;
    const moved = (scrolled: Event) => {
      if (!element.contains(scrolled.target as Node)) close();
    };
    const outside = (pressed: Event) => {
      const target = pressed.target as Node;
      if (!element.contains(target) && !arrow.contains(target)) close();
    };
    const escaping: Keymap = {
      take: (key) => {
        if (key !== 'Escape') return false;
        close();
        return true;
      },
    };
    document.addEventListener('scroll', moved, true);
    window.addEventListener('resize', close);
    document.addEventListener('mousedown', outside, true);
    keys.push('dialog', escaping);
    return () => {
      document.removeEventListener('scroll', moved, true);
      window.removeEventListener('resize', close);
      document.removeEventListener('mousedown', outside, true);
      keys.drop(escaping);
    };
  },
);
