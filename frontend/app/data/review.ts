import type { Conversation } from 'frontend/data/api';
import type { Details } from 'frontend/data/panel';

export interface Outgoing {
  key: string;
  where: string;
  body: string;
}

export interface Review {
  enrolled: Outgoing[];
  pendingOnGitHub: Outgoing[];
  unanswered: number;
  unadded: Outgoing[];
}

function whereOf(conversation: Conversation): string {
  const { path, line } = conversation.anchor;
  return line === null ? (path ?? '') : `${path ?? ''}:${line}`;
}

function outgoing(
  conversations: Conversation[],
  details: (key: string) => Details | null,
): Outgoing[] {
  return conversations.map((one) => ({
    key: one.key,
    where: whereOf(one),
    body: details(one.key)?.comments[0]?.body ?? '',
  }));
}

function pendingOnGitHub(conversation: Conversation): boolean {
  return conversation.comments[0]?.review_state === 'PENDING';
}

export function reviewOf(
  conversations: Conversation[],
  details: (key: string) => Details | null,
  viewer: string,
): Review {
  const inState = (state: string) =>
    conversations.filter((one) => one.state === state);
  return {
    enrolled: outgoing(inState('enrolled'), details),
    pendingOnGitHub: outgoing(conversations.filter(pendingOnGitHub), details),
    unanswered: inState('waiting').filter(
      (one) => one.comments[0]?.author === viewer && !pendingOnGitHub(one),
    ).length,
    unadded: outgoing(inState('draft'), details),
  };
}
