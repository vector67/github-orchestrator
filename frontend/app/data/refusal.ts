import type { ErrorDetail } from 'frontend/data/api';

export type Refused = Omit<ErrorDetail, 'code'> & {
  code: ErrorDetail['code'] | 'unexpected';
  field?: string;
};

export class Refusal extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail: string;
  readonly fields: Record<string, string>;

  constructor({ status, code, detail }: Refused, all: Refused[] = []) {
    super(detail);
    this.status = status;
    this.code = code;
    this.detail = detail;
    this.fields = Object.fromEntries(
      all.flatMap((one) => (one.field ? [[one.field, one.detail]] : [])),
    );
  }
}

export class Abandoned extends Error {}

const UNREACHABLE = 'board-unreachable';

const UNHELD = ['watcher-starting', 'watcher-failing', 'not-watching'] as const;

export type Unheld = (typeof UNHELD)[number];

export function unheldBy(trouble: unknown): Unheld | null {
  if (!(trouble instanceof Refusal)) return null;
  return UNHELD.find((code) => code === trouble.code) ?? null;
}

export function unreachable(trouble: unknown): boolean {
  return trouble instanceof Refusal && trouble.code === UNREACHABLE;
}
