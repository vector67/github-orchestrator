import { Abandoned, Refusal, type Refused } from 'frontend/data/refusal';

const JSON_TYPE = 'application/json';

export type Read<T> =
  { changed: true; body: T; tag: string | null } | { changed: false };

async function refusalOf(answer: Response): Promise<Refusal> {
  const unexplained: Refused = {
    status: answer.status,
    code: 'unexpected',
    detail: `the board answered ${answer.status}`,
  };
  try {
    const { errors } = (await answer.json()) as { errors: Refused[] };
    return new Refusal(errors[0] ?? unexplained, errors);
  } catch {
    return new Refusal(unexplained);
  }
}

interface Asking {
  path: string;
  stop: AbortController;
}

const asking = new Set<Asking>();

export function pending(): string[] {
  return [...asking].map((one) => one.path);
}

export function abandonUnder(prefix: string): void {
  asking.forEach((one) => {
    if (one.path.startsWith(`${prefix}/`)) one.stop.abort();
  });
}

export async function read<T>(
  path: string,
  tag?: string | null,
): Promise<Read<T>> {
  const headers: Record<string, string> = { Accept: JSON_TYPE };
  if (tag) headers['If-None-Match'] = tag;
  const asked: Asking = { path, stop: new AbortController() };
  asking.add(asked);
  try {
    const answer = await fetch(path, {
      headers,
      cache: 'no-store',
      signal: asked.stop.signal,
    });
    if (answer.status === 304) return { changed: false };
    if (!answer.ok) throw await refusalOf(answer);
    return {
      changed: true,
      body: (await answer.json()) as T,
      tag: answer.headers.get('ETag'),
    };
  } catch (trouble) {
    if (asked.stop.signal.aborted) throw new Abandoned(`${path} was left`);
    throw trouble;
  } finally {
    asking.delete(asked);
  }
}

export async function fetched<T>(path: string): Promise<T> {
  const answer = await read<T>(path);
  if (!answer.changed) throw new Error(`${path} answered 304 unasked`);
  return answer.body;
}

export interface Written<T> {
  body: T;
  location: string | null;
}

export function posted<T>(
  path: string,
  ifMatch: string | null,
  body: unknown,
): Promise<Written<T>> {
  return sent<T>('POST', path, ifMatch, body);
}

export function put<T>(
  path: string,
  ifMatch: string,
  body: unknown,
): Promise<Written<T>> {
  return sent<T>('PUT', path, ifMatch, body);
}

async function sent<T>(
  method: string,
  path: string,
  ifMatch: string | null,
  body: unknown,
): Promise<Written<T>> {
  const headers: Record<string, string> = {
    Accept: JSON_TYPE,
    'Content-Type': JSON_TYPE,
  };
  if (ifMatch) headers['If-Match'] = ifMatch;
  const answer = await fetch(path, {
    method,
    headers,
    body: JSON.stringify(body),
  });
  if (!answer.ok) throw await refusalOf(answer);
  return {
    body: (await answer.json()) as T,
    location: answer.headers.get('Location'),
  };
}

export async function handed(path: string, body?: unknown): Promise<void> {
  const init: RequestInit = { method: 'POST', headers: { Accept: JSON_TYPE } };
  if (body !== undefined) {
    init.headers = { Accept: JSON_TYPE, 'Content-Type': JSON_TYPE };
    init.body = JSON.stringify(body);
  }
  const answer = await fetch(path, init);
  if (!answer.ok) throw await refusalOf(answer);
}

export async function write<T>(
  path: string,
  ifMatch: string | null,
  body: unknown,
): Promise<T> {
  return (await posted<T>(path, ifMatch, body)).body;
}
