import { modifier } from 'ember-modifier';

const NEAR_END = 40;

interface Place {
  atEnd: boolean;
  anchor: HTMLElement | null;
  anchorTop: number;
}

const PLACES = new WeakMap<Element, Place>();

function atEnd(element: HTMLElement): boolean {
  return (
    element.scrollHeight - element.scrollTop - element.clientHeight < NEAR_END
  );
}

function firstInView(element: HTMLElement): HTMLElement | null {
  const top = element.getBoundingClientRect().top;
  return (
    Array.from(element.children as HTMLCollectionOf<HTMLElement>).find(
      (child) => child.getBoundingClientRect().bottom > top,
    ) ?? null
  );
}

function placeOf(element: HTMLElement): Place {
  const anchor = firstInView(element);
  return { atEnd: atEnd(element), anchor, anchorTop: anchor?.offsetTop ?? 0 };
}

export default modifier(
  (
    element: HTMLElement,
    [content, noted]: [
      unknown,
      ((atEnd: boolean, element: HTMLElement) => void)?,
    ],
  ) => {
    void content;
    const was = PLACES.get(element);
    if (!was || was.atEnd) element.scrollTop = element.scrollHeight;
    else if (was.anchor?.isConnected)
      element.scrollTop += was.anchor.offsetTop - was.anchorTop;
    PLACES.set(element, placeOf(element));
    const note = () => {
      const place = placeOf(element);
      PLACES.set(element, place);
      noted?.(place.atEnd, element);
    };
    element.addEventListener('scroll', note, { passive: true });
    return () => element.removeEventListener('scroll', note);
  },
);
