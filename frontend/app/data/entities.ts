import type {
  Comment,
  CommentSummary,
  Conversation,
  OperationSummary,
  OutputLine,
  ThreadRow,
} from 'frontend/data/api';

export type StoredComment = CommentSummary & Partial<Comment>;

export type Thread = ThreadRow &
  Partial<Omit<Conversation, keyof ThreadRow | 'comments' | 'operations'>> & {
    comments?: StoredComment[];
    operations?: string[];
    read?: string;
    provisional?: boolean;
  };

export type Arriving = ThreadRow &
  Partial<Omit<Conversation, keyof ThreadRow>> & { provisional?: boolean };

export type StoredOperation = { id: string } & Partial<OperationSummary> & {
    conversation: string | null;
  };

export interface HeardLine extends OutputLine {
  n: number;
}

export interface Merged {
  thread: Thread;
  operations: StoredOperation[];
  under: boolean;
}

export function operationKey(one: {
  id: string;
  conversation: string | null;
}): string {
  return `${one.conversation ?? ''}/${one.id}`;
}

export function older(one: string | null, other: string | null): boolean {
  return one !== null && other !== null && one < other;
}

export function savedAfter(
  saved: string | null,
  listedAt: string | null,
): boolean {
  return saved !== null && listedAt !== null && saved >= listedAt;
}

export function merged<T extends object>(
  held: T | null | undefined,
  arrived: T,
  stamp: (one: T) => string | null,
): T {
  if (!held) return arrived;
  if (older(stamp(arrived), stamp(held))) return { ...arrived, ...held };
  return { ...held, ...arrived };
}

function sameComment(
  held: StoredComment[],
  one: StoredComment,
  at: number,
): StoredComment | undefined {
  if (one.id !== null) return held.find((other) => other.id === one.id);
  return held[at]?.id === null ? held[at] : undefined;
}

function commentsMerged(
  held: StoredComment[] | undefined,
  arrived: StoredComment[],
): StoredComment[] {
  if (!held) return arrived;
  return arrived.map((one, at) => {
    const was = sameComment(held, one, at);
    return was ? { ...was, ...one } : one;
  });
}

export function commentsRead(
  held: StoredComment[] | undefined,
  read: Comment[],
): StoredComment[] {
  if (!held) return read;
  const filled = held.map((one, at) => {
    const found = sameComment(read, one, at);
    return found ? { ...one, ...found } : one;
  });
  const unheld = read.filter(
    (one, at) => sameComment(held, one, at) === undefined,
  );
  return [...filled, ...unheld];
}

export function threadMerged(
  held: Thread | undefined,
  { operations, ...arrived }: Arriving,
): Merged {
  const ids = operations?.map((one) => one.id);
  const coming: Thread = ids ? { ...arrived, operations: ids } : arrived;
  const named = (operations ?? []).map((one) => ({
    ...one,
    conversation: arrived.key,
  }));
  if (!held) return { thread: coming, operations: named, under: false };
  if (older(arrived.updated_at, held.updated_at)) {
    return { thread: { ...coming, ...held }, operations: named, under: true };
  }
  const thread: Thread = { ...held, ...coming };
  if (arrived.comments) {
    thread.comments = commentsMerged(held.comments, arrived.comments);
  }
  return { thread, operations: named, under: false };
}

export function operationsMerged(
  held: Record<string, StoredOperation> | undefined,
  arrived: StoredOperation[],
  under: boolean,
): Record<string, StoredOperation> {
  return {
    ...held,
    ...Object.fromEntries(
      arrived.map((one) => {
        const key = operationKey(one);
        const was = held?.[key];
        return [key, under ? { ...one, ...was } : { ...was, ...one }];
      }),
    ),
  };
}

function trimmedFrom(was: OutputLine[], now: OutputLine[]): number {
  const same = (one: OutputLine, other: OutputLine | undefined) =>
    one.text === other?.text && one.run_boundary === other.run_boundary;
  for (let trimmed = 0; trimmed < was.length; trimmed += 1) {
    if (was.slice(trimmed).every((line, at) => same(line, now[at])))
      return trimmed;
  }
  return was.length;
}

export function carried(was: HeardLine[], now: OutputLine[]): HeardLine[] {
  const trimmed = trimmedFrom(was, now);
  const kept = was.slice(trimmed);
  let next = (was.at(-1)?.n ?? 0) + 1;
  return [
    ...kept,
    ...now.slice(kept.length).map((line) => ({ ...line, n: next++ })),
  ];
}
