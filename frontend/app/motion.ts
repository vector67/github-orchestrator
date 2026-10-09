import { renderSettled } from '@ember/renderer';
import { modifier } from 'ember-modifier';

export type Motion =
  | 'slide'
  | 'slide-far'
  | 'flash'
  | 'in'
  | 'out'
  | 'collapse'
  | 'select'
  | 'rest';

type Slide = 'slide' | 'slide-far';

interface Place {
  rect: DOMRect;
  group: string | null;
  scroller: Element | null;
}

const lists = new Map<HTMLElement, Slide>();

function token(name: string): string {
  return getComputedStyle(document.documentElement)
    .getPropertyValue(`--motion-${name}`)
    .trim();
}

export function durationOf(motion: Motion): number {
  const value = token(motion);
  return value.endsWith('ms') ? parseFloat(value) : parseFloat(value) * 1000;
}

export function after(ms: number): Promise<void> {
  return new Promise((resolve) => {
    if (ms <= 0) {
      resolve();
      return;
    }
    const timer = setInterval(() => {
      clearInterval(timer);
      resolve();
    }, ms);
  });
}

export const moves = modifier(
  (list: HTMLElement, [slide = 'slide']: [Slide?]) => {
    lists.set(list, slide);
    return () => lists.delete(list);
  },
);

const PULSES_FOR_MS = 5000;

const pulsed = new WeakMap<HTMLElement, { state: unknown }>();

export const pulses = modifier((dot: HTMLElement, [state]: [unknown]) => {
  if (pulsed.has(dot) && pulsed.get(dot)!.state === state) return;
  const pulse = { state };
  pulsed.set(dot, pulse);
  dot.setAttribute('data-pulsing', '');
  void after(PULSES_FOR_MS).then(() => {
    if (pulsed.get(dot) === pulse) dot.removeAttribute('data-pulsing');
  });
});

const chosen = new WeakMap<HTMLElement, { key: string; row: HTMLElement }>();

export const selects = modifier(
  (list: HTMLElement, [key]: [string | null | undefined]) => {
    const was = chosen.get(list);
    if (!key || was?.key === key) return;
    const row = list.querySelector<HTMLElement>(
      `[data-flip-key="${CSS.escape(key)}"]`,
    );
    if (!row) return;
    chosen.set(list, { key, row });
    if (was?.row.isConnected) highlight(row, was.row.getBoundingClientRect());
    row.scrollIntoView({ block: 'nearest' });
  },
);

function highlight(row: HTMLElement, from: DOMRect): void {
  const duration = durationOf('select');
  if (!duration || document.hidden) return;
  const to = row.getBoundingClientRect();
  const move = `translate(${from.left - to.left}px, ${from.top - to.top}px)`;
  const size = `scale(${from.width / to.width}, ${from.height / to.height})`;
  row.animate(
    [
      { transformOrigin: '0 0', transform: `${move} ${size}` },
      { transformOrigin: '0 0', transform: 'none' },
    ],
    { duration, easing: token('ease'), pseudoElement: '::before' },
  );
}

function itemsOf(list: HTMLElement): HTMLElement[] {
  return Array.from(list.querySelectorAll<HTMLElement>('[data-flip-key]'));
}

function scrollerOf(item: HTMLElement, list: HTMLElement): Element | null {
  for (let at = item.parentElement; at && at !== list; at = at.parentElement) {
    if (getComputedStyle(at).overflowY !== 'visible') return at;
  }
  return null;
}

function flashing(item: HTMLElement): boolean {
  return item.getAnimations().some((one) => one instanceof CSSAnimation);
}

function placesOf(list: HTMLElement): Map<string, Place> {
  const items = itemsOf(list);
  items
    .filter((item) => !flashing(item))
    .forEach((item) => item.removeAttribute('data-moved'));
  return new Map(
    items.map((item) => [
      item.dataset['flipKey']!,
      {
        rect: item.getBoundingClientRect(),
        group: item.dataset['flipGroup'] ?? null,
        scroller: scrollerOf(item, list),
      },
    ]),
  );
}

async function land(
  list: HTMLElement,
  was: Map<string, Place>,
  slide: Slide,
): Promise<void> {
  const duration = durationOf(slide);
  const slides = itemsOf(list).flatMap((item) => {
    const then = was.get(item.dataset['flipKey']!);
    if (!then) return [];
    if (then.group !== null && then.group !== item.dataset['flipGroup'])
      item.setAttribute('data-moved', '');
    const now = item.getBoundingClientRect();
    const dx = then.rect.left - now.left;
    const dy = then.rect.top - now.top;
    if (!duration || document.hidden || (!dx && !dy)) return [];
    const scroller = scrollerOf(item, list);
    const from = { transform: `translate(${dx}px, ${dy}px)` };
    const to = { transform: 'none' };
    const flier = then.scroller === scroller ? item : standIn(item, now);
    const frames =
      flier === item
        ? [from, to]
        : [
            { ...from, clipPath: 'inset(0px)' },
            { ...to, clipPath: insetInto(scroller, now) },
          ];
    flier.setAttribute('data-flying', '');
    return [
      flier
        .animate(frames, { duration, easing: token('ease') })
        .finished.catch(() => undefined)
        .then(() => {
          flier.removeAttribute('data-flying');
          if (flier === item) return;
          flier.remove();
          item.style.visibility = '';
        }),
    ];
  });
  await Promise.all(slides);
}

function insetInto(scroller: Element | null, now: DOMRect): string {
  if (!scroller) return 'inset(0px)';
  const box = scroller.getBoundingClientRect();
  const sides = [
    box.top - now.top,
    now.right - box.right,
    now.bottom - box.bottom,
    box.left - now.left,
  ];
  return `inset(${sides.map((side) => `${Math.max(0, side)}px`).join(' ')})`;
}

function standIn(item: HTMLElement, now: DOMRect): HTMLElement {
  const stand = item.cloneNode(true) as HTMLElement;
  stand.removeAttribute('data-flip-key');
  stand.removeAttribute('id');
  stand.setAttribute('aria-hidden', 'true');
  Object.assign(stand.style, {
    position: 'fixed',
    left: `${now.left}px`,
    top: `${now.top}px`,
    width: `${now.width}px`,
    height: `${now.height}px`,
    margin: '0',
    pointerEvents: 'none',
  });
  document.body.append(stand);
  item.style.visibility = 'hidden';
  return stand;
}

export async function flip(change: () => void): Promise<void> {
  const before = Array.from(
    lists,
    ([list, slide]) => [list, placesOf(list), slide] as const,
  );
  change();
  await renderSettled();
  await Promise.all(
    before
      .filter(([list]) => lists.has(list))
      .map(([list, was, slide]) => land(list, was, slide)),
  );
}

export async function collapse(element: HTMLElement): Promise<void> {
  const duration = durationOf('collapse');
  if (!duration) return;
  const box = getComputedStyle(element);
  const edges = [
    'marginTop',
    'marginBottom',
    'borderTopWidth',
    'borderBottomWidth',
    'paddingTop',
    'paddingBottom',
  ] as const;
  const shut = { boxSizing: 'border-box', overflow: 'hidden' };
  await element.animate(
    [
      {
        ...shut,
        ...Object.fromEntries(edges.map((edge) => [edge, box[edge]])),
        height: `${element.offsetHeight}px`,
        opacity: 1,
      },
      {
        ...shut,
        ...Object.fromEntries(edges.map((edge) => [edge, '0px'])),
        height: '0px',
        opacity: 0,
      },
    ],
    { duration, easing: token('ease'), fill: 'forwards' },
  ).finished;
}
