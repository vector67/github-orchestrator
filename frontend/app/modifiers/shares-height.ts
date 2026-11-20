import { modifier } from 'ember-modifier';

export default modifier((element: HTMLElement, [name]: [string]) => {
  const parent = element.parentElement!;
  const share = (): void => {
    parent.style.setProperty(name, `${element.offsetHeight}px`);
  };
  share();
  const watching = new ResizeObserver(share);
  watching.observe(element);
  return () => {
    watching.disconnect();
    parent.style.removeProperty(name);
  };
});
