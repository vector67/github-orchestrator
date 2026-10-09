const HOME = /^\/(?:Users|home)\/[^/]+\//;

export function tildeOf(path: string): string {
  return path.replace(HOME, '~/');
}

export function openOnGitHub(url: string | null): void {
  if (url) window.open(url, '_blank', 'noopener');
}

export function copyAddress(url: string | null): Promise<string> {
  if (!url) return Promise.resolve('This pull request has no address yet.');
  return copied(url, 'address');
}

async function copied(text: string, what: string): Promise<string> {
  try {
    await navigator.clipboard.writeText(text);
    return `Copied ${text}`;
  } catch {
    return `The browser would not let the page copy the ${what}.`;
  }
}

export function copyDirectory(path: string): Promise<string> {
  return copied(path, 'directory');
}

export function copyPath(path: string): Promise<string> {
  return copied(path, 'path');
}
