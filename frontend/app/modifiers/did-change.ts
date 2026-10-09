import { modifier } from 'ember-modifier';

type Draw = (element: HTMLElement, key?: unknown) => (() => void) | void;

export default modifier((element: HTMLElement, [draw, key]: [Draw, unknown?]) =>
  draw(element, key),
);
