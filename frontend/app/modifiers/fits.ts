import { modifier } from 'ember-modifier';

export default modifier(
  (element: HTMLElement, [fit]: [(across: number) => void]) => {
    let frame = 0;
    const watching = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => fit(element.clientWidth));
    });
    watching.observe(element);
    return () => {
      cancelAnimationFrame(frame);
      watching.disconnect();
    };
  },
);
