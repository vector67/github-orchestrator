export function recall(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function recalledAs<T>(
  key: string,
  read: (kept: unknown) => T,
  fallback: T,
): T {
  const kept = recall(key);
  if (kept === null) return fallback;
  try {
    return read(JSON.parse(kept));
  } catch {
    return fallback;
  }
}

export function keep(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    return;
  }
}

export function forget(key: string): void {
  try {
    localStorage.removeItem(key);
  } catch {
    return;
  }
}
