import type { DiffLine, FileChange, DiffSide } from 'frontend/data/api';
import { endOf, markOf, type DiffRow, type End } from 'frontend/data/diff-rows';

export interface Selection {
  path: string;
  hunk: number;
  from: number;
  to: number;
  first: End;
  last: End;
}

export interface Lines {
  path: string;
  line: number;
  side: DiffSide;
  start_line: number | null;
  start_side: DiffSide | null;
}

export const LINES_GONE =
  'These lines are no longer in the diff. Select new ones.';

export function selectable(row: DiffRow): boolean {
  return row.hunk !== undefined && row.at !== undefined;
}

export function spanOf(
  file: FileChange,
  hunk: number,
  one: number,
  other: number,
): Selection | null {
  const lines = file.hunks[hunk]?.lines ?? [];
  const from = Math.min(one, other);
  const to = Math.max(one, other);
  const first = lines[from];
  const last = lines[to];
  if (!first || !last) return null;
  return {
    path: file.path,
    hunk,
    from,
    to,
    first: endOf(first),
    last: endOf(last),
  };
}

export function holds(selection: Selection | null, row: DiffRow): boolean {
  if (!selection || row.file !== selection.path) return false;
  if (row.hunk !== selection.hunk || row.at === undefined) return false;
  return row.at >= selection.from && row.at <= selection.to;
}

export function endsAt(selection: Selection | null, row: DiffRow): boolean {
  return (
    selection !== null &&
    row.file === selection.path &&
    row.hunk === selection.hunk &&
    row.at === selection.to
  );
}

function single(selection: Selection): boolean {
  return selection.from === selection.to;
}

function spanned(selection: Selection): string {
  const last = markOf(selection.last);
  return single(selection) ? last : `${markOf(selection.first)} to ${last}`;
}

export function commentingOn(selection: Selection): string {
  const lines = single(selection) ? 'line' : 'lines';
  return `Commenting on ${lines} ${spanned(selection)}`;
}

export function anchoredAt(selection: Selection): string {
  const name = selection.path.split('/').at(-1) ?? selection.path;
  return `${name} ${spanned(selection)}`;
}

export function linesOf(selection: Selection): Lines {
  const one = single(selection);
  return {
    path: selection.path,
    line: selection.last.line,
    side: selection.last.side,
    start_line: one ? null : selection.first.line,
    start_side: one ? null : selection.first.side,
  };
}

function lands(line: DiffLine, end: End): boolean {
  if (end.side === 'LEFT') {
    return line.kind !== 'added' && line.old_line === end.line;
  }
  return line.kind !== 'removed' && line.new_line === end.line;
}

export function selectionOf(file: FileChange, lines: Lines): Selection | null {
  const last: End = { side: lines.side, line: lines.line };
  const first: End =
    lines.start_line === null
      ? last
      : { side: lines.start_side ?? lines.side, line: lines.start_line };
  const hunks = file.hunks;
  for (const [hunk, { lines: rows }] of hunks.entries()) {
    const to = rows.findIndex((line) => lands(line, last));
    const from = rows.findIndex((line) => lands(line, first));
    if (to >= 0 && from >= 0 && from <= to) {
      return spanOf(file, hunk, from, to);
    }
  }
  return null;
}

export function landsOn(row: DiffRow, lines: Lines): boolean {
  if (!row.numbered || row.file !== lines.path) return false;
  if (lines.side === 'LEFT') {
    return row.kind !== 'added' && row.old === String(lines.line);
  }
  return row.kind !== 'removed' && row.new === String(lines.line);
}
