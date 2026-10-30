import type { Conversation, Operation } from 'frontend/data/api';
import { writtenOn } from 'frontend/data/decisions';
import type { Details } from 'frontend/data/panel';
import { unsettled } from 'frontend/data/thread';

export interface Outgoing {
  key: string;
  where: string;
  body: string;
  pending: string | null;
  refused: string | null;
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
  sending: boolean,
): Outgoing[] {
  return conversations.map((one) => {
    const { pending, refused } = writtenOn(one, sending);
    return {
      key: one.key,
      where: whereOf(one),
      body: details(one.key)?.comments[0]?.body ?? '',
      pending,
      refused,
    };
  });
}

export function reviewGoing(inFlight: Operation[]): Operation | undefined {
  return inFlight.findLast((one) => one.kind === 'send-review');
}

export function reviewSending(inFlight: Operation[]): boolean {
  const going = reviewGoing(inFlight);
  return going !== undefined && unsettled(going);
}

function pendingOnGitHub(conversation: Conversation): boolean {
  return conversation.comments[0]?.review_state === 'PENDING';
}

export function reviewOf(
  conversations: Conversation[],
  details: (key: string) => Details | null,
  viewer: string,
  sending: boolean,
): Review {
  const inState = (state: string) =>
    conversations.filter((one) => one.state === state);
  return {
    enrolled: outgoing(inState('enrolled'), details, sending),
    pendingOnGitHub: outgoing(
      conversations.filter(pendingOnGitHub),
      details,
      sending,
    ),
    unanswered: inState('waiting').filter(
      (one) => one.comments[0]?.author === viewer && !pendingOnGitHub(one),
    ).length,
    unadded: outgoing(inState('draft'), details, sending),
  };
}
