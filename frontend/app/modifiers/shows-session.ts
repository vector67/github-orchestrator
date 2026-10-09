import { modifier } from 'ember-modifier';
import type { Session } from 'frontend/data/terminal';

export default modifier(
  (element: HTMLElement, [session, leave]: [Session, () => void]) => {
    session.mount(element, leave);
    const watching = new ResizeObserver(() => session.refit());
    watching.observe(element);
    return () => {
      watching.disconnect();
      session.element.remove();
    };
  },
);
