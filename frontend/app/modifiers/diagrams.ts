import { modifier } from 'ember-modifier';
import { waitForPromise } from '@ember/test-waiters';

let drawnCount = 0;

async function drawInto(figures: HTMLElement[], dark: boolean): Promise<void> {
  const { default: mermaid } = await import('mermaid');
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: 'strict',
    suppressErrorRendering: true,
    theme: dark ? 'dark' : 'default',
  });
  for (const figure of figures) {
    const source = figure.dataset['source'] ?? figure.textContent;
    figure.dataset['source'] = source;
    drawnCount += 1;
    try {
      const { svg } = await mermaid.render(`diagram-${drawnCount}`, source);
      figure.innerHTML = svg;
    } catch {
      figure.replaceChildren(sourceOf(source));
    }
  }
}

function sourceOf(source: string): HTMLElement {
  const pre = document.createElement('pre');
  const code = document.createElement('code');
  code.textContent = source;
  pre.append(code);
  return pre;
}

export default modifier((element: HTMLElement, [, dark]: [string, boolean]) => {
  const figures = [...element.querySelectorAll<HTMLElement>('figure')];
  if (figures.length === 0) return;
  void waitForPromise(drawInto(figures, dark));
});
