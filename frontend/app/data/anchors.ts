import type { DiffAnchors, DiffSide } from 'frontend/data/api';
import { markOf } from 'frontend/data/diff-rows';
import type { Inline, Inlined } from 'frontend/data/inline';
import type { Lines } from 'frontend/data/selection';

export const NOT_AT_HEAD = "This line doesn't exist in the latest commit";

export interface Placed extends Inlined {
  elsewhere: number;
}

interface End {
  side: DiffSide;
  line: number;
}

type Way = 'to head' | 'from head';

function moved(
  anchors: DiffAnchors,
  path: string,
  end: End,
  way: Way,
): End | null {
  const lines = anchors.files.find((one) => one.path === path)?.lines ?? [];
  const found = lines.find((one) => {
    const from = way === 'to head' ? one : one.onto;
    return from.side === end.side && from.line === end.line;
  });
  if (!found) return null;
  return way === 'to head' ? found.onto : found;
}

function carried(lines: Lines, anchors: DiffAnchors, way: Way): Lines | null {
  const last = moved(
    anchors,
    lines.path,
    { side: lines.side, line: lines.line },
    way,
  );
  if (!last) return null;
  if (lines.start_line === null) {
    return { ...lines, side: last.side, line: last.line };
  }
  const first = moved(
    anchors,
    lines.path,
    { side: lines.start_side ?? lines.side, line: lines.start_line },
    way,
  );
  if (!first) return null;
  return {
    path: lines.path,
    line: last.line,
    side: last.side,
    start_line: first.line,
    start_side: first.side,
  };
}

export function postedAt(
  lines: Lines,
  anchors: DiffAnchors | null,
): Lines | null {
  return anchors ? carried(lines, anchors, 'to head') : lines;
}

export function drawnOn(inlined: Inlined, anchors: DiffAnchors | null): Placed {
  if (!anchors) return { ...inlined, elsewhere: 0 };
  const drawn = new Set(anchors.files.map((one) => one.path));
  const shown: Inline[] = [];
  let elsewhere = 0;
  for (const one of inlined.shown) {
    const lines = carried(one.lines, anchors, 'from head');
    if (lines) shown.push({ ...one, lines });
    else if (drawn.has(one.lines.path)) elsewhere += 1;
  }
  return { shown, outdated: inlined.outdated, elsewhere };
}

function same(one: Lines, other: Lines): boolean {
  return (
    one.line === other.line &&
    one.side === other.side &&
    one.start_line === other.start_line &&
    (one.start_line === null || one.start_side === other.start_side)
  );
}

export function inLatestOf(shown: Lines, posted: Lines | null): string {
  if (!posted || same(shown, posted)) return '';
  const last = markOf({ side: posted.side, line: posted.line });
  const where =
    posted.start_line === null
      ? `line ${last}`
      : `lines ${markOf({ side: posted.start_side ?? posted.side, line: posted.start_line })} to ${last}`;
  return ` (${where} in the latest commit)`;
}

export function elsewhereOf(count: number, picked: boolean): string | null {
  if (!count) return null;
  const threads = count === 1 ? '1 thread is' : `${count} threads are`;
  return `${threads} on lines this ${picked ? 'range' : 'commit'} doesn't have`;
}
