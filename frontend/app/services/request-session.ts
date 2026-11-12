import Service from '@ember/service';
import { tracked } from '@glimmer/tracking';
import { forget, keep, recall } from 'frontend/data/site-data';

export type RequestSession = 'ask' | 'visible' | 'invisible';

export const REQUEST_SESSIONS: RequestSession[] = [
  'ask',
  'visible',
  'invisible',
];

const KEPT = 'agent-session';

const KEPT_FOR_REQUESTS = 'request-change-session';

const KEPT_FOR_ANSWERS = 'answer-session';

function recalled(key: string): RequestSession | null {
  const kept = recall(key);
  return REQUEST_SESSIONS.find((one) => one === kept) ?? null;
}

function carriedOver(): RequestSession {
  const requests = recalled(KEPT_FOR_REQUESTS);
  const answers = recalled(KEPT_FOR_ANSWERS);
  const carried =
    [requests, answers].find((one) => one !== null && one !== 'ask') ??
    requests ??
    answers;
  forget(KEPT_FOR_REQUESTS);
  forget(KEPT_FOR_ANSWERS);
  if (carried === null) return 'ask';
  keep(KEPT, carried);
  return carried;
}

export default class RequestSessionService extends Service {
  @tracked chosen: RequestSession = recalled(KEPT) ?? carriedOver();

  choose(chosen: RequestSession): void {
    this.chosen = chosen;
    keep(KEPT, chosen);
  }

  remember(visible: boolean): void {
    this.choose(visible ? 'visible' : 'invisible');
  }
}
