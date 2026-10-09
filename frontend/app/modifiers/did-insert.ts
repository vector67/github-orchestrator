import { modifier } from 'ember-modifier';

export default modifier((_element: Element, [run]: [() => void]) => {
  run();
});
