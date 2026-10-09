import { modifier } from 'ember-modifier';

type Build = (source: string) => DocumentFragment;

const DRAWN_FROM = new WeakMap<Element, { build: Build; source: string }>();

export default modifier(
  (element: HTMLElement, [build, source]: [Build, string]) => {
    const last = DRAWN_FROM.get(element);
    if (last?.build === build && last.source === source) return;
    DRAWN_FROM.set(element, { build, source });
    element.replaceChildren(build(source));
  },
);
