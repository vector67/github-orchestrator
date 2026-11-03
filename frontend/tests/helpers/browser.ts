import { click } from '@ember/test-helpers';

export async function leftToTheBrowser(target: string): Promise<boolean> {
  let left = false;
  const watch = (event: MouseEvent) => {
    left = !event.defaultPrevented;
    event.preventDefault();
  };
  window.addEventListener('click', watch);
  try {
    await click(target, { metaKey: true });
  } finally {
    window.removeEventListener('click', watch);
  }
  return left;
}

export interface GitHubCalls {
  opened: string[];
  copied: string[];
}

export function stubGitHub(hooks: NestedHooks): () => GitHubCalls {
  let calls: GitHubCalls = { opened: [], copied: [] };
  const real = { open: window.open.bind(window) };

  hooks.beforeEach(function () {
    calls = { opened: [], copied: [] };
    window.open = ((url: string) => {
      calls.opened.push(url);
      return null;
    }) as typeof window.open;
    Object.defineProperty(navigator.clipboard, 'writeText', {
      configurable: true,
      value: (text: string) => {
        calls.copied.push(text);
        return Promise.resolve();
      },
    });
  });

  hooks.afterEach(function () {
    window.open = real.open;
    Reflect.deleteProperty(navigator.clipboard, 'writeText');
  });

  return () => calls;
}
