import type {
  Diff,
  DiffHunk,
  DiffLine,
  FileChange,
  DiffSide,
} from 'frontend/data/api';
import {
  highlightedLines,
  highlighterOf,
  languageOf,
  type Highlighter,
} from 'frontend/data/highlight';

export interface End {
  side: DiffSide;
  line: number;
}

export const DIFF_LOADING = 'Loading the diff…';

export const DIFF_FAILED = 'the pull request’s diff will not render';

const EXPAND_STEP = 16;

export interface Expand {
  direction: 'up' | 'down' | 'all';
  label: string;
  from: number;
  to: number;
}

export interface DiffRow {
  kind: string;
  file?: string;
  line?: number;
  old: string;
  new: string;
  code: string;
  numbered: boolean;
  draw: Highlighter;
  expands?: Expand[];
  hunk?: number;
  at?: number;
  end?: End;
  mark?: string;
}

export const isHeader = (row: DiffRow): boolean => row.expands !== undefined;

export interface DiffFile {
  path: string;
  rows: DiffRow[];
}

export type Revealed = Record<number, string>;

interface Gap {
  from: number;
  to: number;
  offset: number;
  edge: 'top' | 'middle' | 'bottom';
}

function firstNew(hunk: DiffHunk): number {
  return hunk.new_lines === 0 ? hunk.new_start + 1 : hunk.new_start;
}

function firstOld(hunk: DiffHunk): number {
  return hunk.old_lines === 0 ? hunk.old_start + 1 : hunk.old_start;
}

function after(hunk: DiffHunk): { old: number; new: number } {
  return {
    old: firstOld(hunk) + hunk.old_lines,
    new: firstNew(hunk) + hunk.new_lines,
  };
}

function gapBefore(hunks: DiffHunk[], at: number): Gap {
  const hunk = hunks[at]!;
  const previous = hunks[at - 1];
  if (!previous) {
    return {
      from: 1,
      to: firstNew(hunk) - 1,
      offset: firstOld(hunk) - firstNew(hunk),
      edge: 'top',
    };
  }
  const next = after(previous);
  return {
    from: next.new,
    to: firstNew(hunk) - 1,
    offset: next.old - next.new,
    edge: 'middle',
  };
}

function gapAfter(hunks: DiffHunk[], lineCount: number | null): Gap | null {
  const last = hunks.at(-1);
  if (!last || lineCount === null) return null;
  const next = after(last);
  return {
    from: next.new,
    to: lineCount,
    offset: next.old - next.new,
    edge: 'bottom',
  };
}

function expanding(
  direction: Expand['direction'],
  from: number,
  to: number,
): Expand {
  const count = to - from + 1;
  const label =
    direction === 'all'
      ? `Show ${count} hidden lines`
      : `Show ${count} more lines`;
  return { direction, label, from, to };
}

function expandsOver(gap: Gap, from: number, to: number): Expand[] {
  const up = expanding('up', Math.max(from, to - EXPAND_STEP + 1), to);
  const down = expanding('down', from, Math.min(to, from + EXPAND_STEP - 1));
  if (gap.edge === 'top') return [up];
  if (gap.edge === 'bottom') return [down];
  if (to - from + 1 <= EXPAND_STEP) return [expanding('all', from, to)];
  return [down, up];
}

function headerRow(code: string, expands: Expand[]): DiffRow {
  return {
    kind: 'hunk',
    old: '',
    new: '',
    code,
    numbered: false,
    draw: highlighterOf(null),
    expands,
  };
}

function headerOf(hunk: DiffHunk): string {
  return (
    `@@ -${hunk.old_start},${hunk.old_lines} ` +
    `+${hunk.new_start},${hunk.new_lines} @@ ${hunk.section ?? ''}`
  ).trimEnd();
}

function gapRows(
  file: FileChange,
  gap: Gap,
  revealed: Revealed,
  header = '',
): DiffRow[] {
  const rows: DiffRow[] = [];
  let line = gap.from;
  while (line <= gap.to) {
    const text = revealed[line];
    if (text !== undefined) {
      rows.push({
        kind: 'context',
        file: file.path,
        line,
        old: String(line + gap.offset),
        new: String(line),
        code: text,
        numbered: true,
        draw: highlighterOf(languageOf(file.path)),
      });
      line += 1;
      continue;
    }
    let end = line;
    while (end < gap.to && revealed[end + 1] === undefined) end += 1;
    rows.push(headerRow('', expandsOver(gap, line, end)));
    line = end + 1;
  }
  const last = rows.findLast((row) => row.kind === 'hunk');
  if (last) last.code = header;
  else if (header && (gap.edge === 'top' || gap.from > gap.to)) {
    rows.push(headerRow(header, []));
  }
  return rows;
}

export function endOf(line: DiffLine): End {
  return line.kind === 'removed'
    ? { side: 'LEFT', line: line.old_line ?? 0 }
    : { side: 'RIGHT', line: line.new_line ?? 0 };
}

export function markOf(end: End): string {
  return `${end.side === 'LEFT' ? '−' : '+'}${end.line}`;
}

function drawnBySide(
  hunk: DiffHunk,
  language: string | null,
): Map<DiffLine, Highlighter> {
  const drawn = new Map<DiffLine, Highlighter>();
  const drawSide = (side: DiffLine[]) => {
    const lines = highlightedLines(
      side.map((line) => line.text),
      language,
    );
    side.forEach((line, at) => drawn.set(line, lines[at]!));
  };
  drawSide(hunk.lines.filter((line) => line.kind !== 'added'));
  drawSide(hunk.lines.filter((line) => line.kind !== 'removed'));
  return drawn;
}

function hunkRows(file: FileChange, hunk: DiffHunk, which: number): DiffRow[] {
  const drawn = drawnBySide(hunk, languageOf(file.path));
  return hunk.lines.map((line, at) => ({
    kind: line.kind,
    file: file.path,
    line: line.new_line ?? line.old_line ?? undefined,
    old: String(line.old_line ?? ''),
    new: String(line.new_line ?? ''),
    code: line.text,
    numbered: true,
    draw: drawn.get(line)!,
    hunk: which,
    at,
    end: endOf(line),
    mark: markOf(endOf(line)),
  }));
}

export function fileOf(file: FileChange, revealed: Revealed): DiffFile {
  const hunks = file.hunks;
  const trailing = gapAfter(hunks, file.line_count ?? null);
  return {
    path: file.path,
    rows: [
      ...(file.is_binary
        ? [
            {
              kind: 'note',
              old: '',
              new: '',
              code: 'a binary file',
              numbered: false,
              draw: highlighterOf(null),
            },
          ]
        : []),
      ...hunks.flatMap((hunk, at) => [
        ...gapRows(file, gapBefore(hunks, at), revealed, headerOf(hunk)),
        ...hunkRows(file, hunk, at),
      ]),
      ...(trailing ? gapRows(file, trailing, revealed) : []),
    ],
  };
}

export function filesOf(
  diff: Diff,
  revealedOf: (path: string) => Revealed,
): DiffFile[] {
  return diff.files.map((file) => fileOf(file, revealedOf(file.path)));
}
