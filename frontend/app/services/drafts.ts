import Service, { service } from '@ember/service';
import { tracked } from '@glimmer/tracking';
import type { DiffSide } from 'frontend/data/api';
import type { Lines } from 'frontend/data/selection';
import type BoardService from 'frontend/services/board';

export interface Saved {
  body: string;
  path: string;
  line: number | null;
  start_line: number | null;
  start_side: DiffSide | null;
  side: DiffSide;
}

export interface Copy {
  body: string;
  path: string;
  line: string;
  start_line: string;
  start_side: DiffSide;
  side: DiffSide;
}

export interface DraftRequest {
  body: string;
  path: string;
  line: number;
  start_line: number | null;
  start_side: DiffSide | null;
  side: DiffSide;
}

export const NEW_DRAFT = '';

export const BLANK: Saved = {
  body: '',
  path: '',
  line: null,
  start_line: null,
  start_side: null,
  side: 'RIGHT',
};

function counted(typed: string): number | null {
  const value = Number(typed.trim());
  return typed.trim() && Number.isInteger(value) && value >= 1 ? value : null;
}

function copied(saved: Saved): Copy {
  return {
    body: saved.body,
    path: saved.path,
    line: saved.line === null ? '' : String(saved.line),
    start_line: saved.start_line === null ? '' : String(saved.start_line),
    start_side: saved.start_side ?? saved.side,
    side: saved.side,
  };
}

export function linesIn(copy: Copy): Lines | null {
  const line = counted(copy.line);
  const start = counted(copy.start_line);
  const path = copy.path.trim();
  if (!path || line === null) return null;
  return {
    path,
    line,
    start_line: start,
    start_side: start === null ? null : copy.start_side,
    side: copy.side,
  };
}

function requestOf(copy: Copy): DraftRequest | null {
  const lines = linesIn(copy);
  if (!copy.body.trim() || !lines) return null;
  return { body: copy.body, ...lines };
}

function sameAs(copy: Copy, saved: Saved): boolean {
  const was = copied(saved);
  return (
    copy.body === was.body &&
    copy.path.trim() === was.path &&
    copy.line.trim() === was.line &&
    copy.start_line.trim() === was.start_line &&
    (copy.start_line.trim() === '' || copy.start_side === was.start_side) &&
    copy.side === was.side
  );
}

export default class DraftsService extends Service {
  @service declare board: BoardService;

  @tracked private copies: Record<string, Copy> = {};
  @tracked private saving: string[] = [];

  async save(key: string, saved: Saved): Promise<string | null> {
    const asked = requestOf(this.copyOf(key, saved));
    if (!asked || !this.saveable(key, saved)) return null;
    this.saving = [...this.saving, key];
    try {
      if (key !== NEW_DRAFT) {
        return (await this.board.decide(key, 'edit-draft', { draft: asked }))
          ? key
          : null;
      }
      const made = await this.board.createDraft(asked);
      if (made) this.forget(NEW_DRAFT);
      return made;
    } finally {
      this.saving = this.saving.filter((one) => one !== key);
    }
  }

  copyOf(key: string, saved: Saved): Copy {
    return this.copies[key] ?? copied(saved);
  }

  change(key: string, saved: Saved, field: keyof Copy, value: string): void {
    this.copies = {
      ...this.copies,
      [key]: { ...this.copyOf(key, saved), [field]: value },
    };
  }

  place(key: string, saved: Saved, lines: Lines): void {
    this.copies = {
      ...this.copies,
      [key]: {
        ...this.copyOf(key, saved),
        path: lines.path,
        line: String(lines.line),
        start_line: lines.start_line === null ? '' : String(lines.start_line),
        start_side: lines.start_side ?? lines.side,
        side: lines.side,
      },
    };
  }

  saveable(key: string, saved: Saved): boolean {
    if (this.saving.includes(key)) return false;
    if (requestOf(this.copyOf(key, saved)) === null) return false;
    return key === NEW_DRAFT || this.unsaved(key, saved);
  }

  unsaved(key: string, saved: Saved): boolean {
    const copy = this.copies[key];
    return copy !== undefined && !sameAs(copy, saved);
  }

  forget(key: string): void {
    this.copies = Object.fromEntries(
      Object.entries(this.copies).filter(([held]) => held !== key),
    );
  }
}
