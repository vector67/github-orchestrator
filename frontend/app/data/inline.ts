import type { Conversation } from 'frontend/data/api';
import { groupsFor, type Role } from 'frontend/data/groups';
import {
  draftLocked,
  draftOf,
  transcriptOf,
  type Context,
  type Details,
  type DraftView,
  type TranscriptEntry,
} from 'frontend/data/panel';
import type { Lines } from 'frontend/data/selection';
import { standingOf, type Standing } from 'frontend/data/thread';

export interface Fold {
  badge: string;
  chip: string;
}

export interface Inline {
  key: string;
  path: string;
  lines: Lines;
  fold: Fold | null;
  entries: TranscriptEntry[];
  draft: DraftView | null;
  locked: boolean;
  standing: Standing;
}

export interface Inlined {
  shown: Inline[];
  outdated: Record<string, string[]>;
}

export interface Seeing {
  details: (key: string) => Details | undefined;
  context: (key: string) => Context;
  reviewSending: boolean;
  role: Role;
}

function anchoredLines(conversation: Conversation, line: number): Lines {
  const { path, start_line, start_side, side } = conversation.anchor;
  return {
    path: path ?? '',
    line,
    side: side ?? 'RIGHT',
    start_line,
    start_side: start_line === null ? null : start_side,
  };
}

function inlined(conversation: Conversation, seeing: Seeing): Inline | null {
  const { path, line } = conversation.anchor;
  const details = seeing.details(conversation.key);
  if (!path || line === null || !details) return null;
  const context = seeing.context(conversation.key);
  if (conversation.kind === 'draft') {
    const draft = draftOf(conversation, details);
    if (!draft) return null;
    return {
      key: conversation.key,
      path,
      lines: anchoredLines(conversation, line),
      fold: null,
      entries: transcriptOf(conversation, details.comments, context),
      draft,
      locked: draftLocked(draft, seeing.reviewSending),
      standing: standingOf(conversation),
    };
  }
  return {
    key: conversation.key,
    path,
    lines: anchoredLines(conversation, line),
    fold: foldOf(conversation, seeing.role),
    entries: transcriptOf(conversation, details.comments, context),
    draft: null,
    locked: true,
    standing: standingOf(conversation),
  };
}

function foldOf(conversation: Conversation, role: Role): Fold | null {
  if (conversation.github_removed) {
    return { badge: 'Deleted', chip: 'Deleted on GitHub' };
  }
  if (conversation.github_resolved === true) {
    return { badge: 'Resolved', chip: 'Resolved on GitHub' };
  }
  if (conversation.state === 'waiting' || conversation.state === 'done') {
    const label = groupsFor(role).find(
      (one) => one.key === conversation.state,
    )!.label;
    return { badge: label, chip: label };
  }
  return null;
}

function outdated(conversation: Conversation): boolean {
  const { path, line, is_outdated } = conversation.anchor;
  return (
    conversation.kind === 'review' &&
    path !== null &&
    (is_outdated || line === null)
  );
}

export function inlineOf(
  conversations: Conversation[],
  seeing: Seeing,
): Inlined {
  const shown: Inline[] = [];
  const stale: Record<string, string[]> = {};
  for (const conversation of conversations) {
    if (outdated(conversation)) {
      if (conversation.github_removed) continue;
      const path = conversation.anchor.path ?? '';
      stale[path] = [...(stale[path] ?? []), conversation.key];
      continue;
    }
    if (conversation.kind !== 'review' && conversation.kind !== 'draft') {
      continue;
    }
    const one = inlined(conversation, seeing);
    if (one) shown.push(one);
  }
  return { shown, outdated: stale };
}
