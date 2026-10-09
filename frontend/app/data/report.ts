import { Abandoned, Refusal } from 'frontend/data/refusal';

const MAX_MESSAGE = 4000;
const MAX_STACK = 20000;

export async function reportError(
  where: string,
  trouble: unknown,
): Promise<void> {
  if (trouble instanceof Refusal || trouble instanceof Abandoned) return;
  const error = trouble instanceof Error ? trouble : new Error(String(trouble));
  try {
    await fetch('/api/client-errors', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        where,
        message: error.message.slice(0, MAX_MESSAGE),
        stack: error.stack?.slice(0, MAX_STACK) ?? null,
      }),
    });
  } catch {
    return;
  }
}

export function reportUncaught(page: EventTarget): void {
  page.addEventListener('error', (event) => {
    const failed = event as ErrorEvent;
    void reportError('window', (failed.error as unknown) ?? failed.message);
  });
  page.addEventListener('unhandledrejection', (event) => {
    void reportError('window', (event as PromiseRejectionEvent).reason);
  });
}
