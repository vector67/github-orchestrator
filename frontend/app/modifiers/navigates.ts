import { modifier } from 'ember-modifier';

export function staysInThisTab(event: MouseEvent): boolean {
  return (
    event.button === 0 &&
    !event.metaKey &&
    !event.ctrlKey &&
    !event.shiftKey &&
    !event.altKey
  );
}

export default modifier((element: Element, [go]: [() => void]) => {
  const clicked = (event: MouseEvent) => {
    if (!staysInThisTab(event)) return;
    event.preventDefault();
    go();
  };
  element.addEventListener('click', clicked as EventListener);
  return () => element.removeEventListener('click', clicked as EventListener);
});
