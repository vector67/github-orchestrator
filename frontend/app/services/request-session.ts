import Service from '@ember/service';
import { tracked } from '@glimmer/tracking';
import { keep, recall } from 'frontend/data/site-data';

export type RequestSession = 'ask' | 'visible' | 'invisible';

export const REQUEST_SESSIONS: RequestSession[] = [
  'ask',
  'visible',
  'invisible',
];

const KEPT = 'request-change-session';

function recalled(): RequestSession {
  const kept = recall(KEPT);
  return REQUEST_SESSIONS.find((one) => one === kept) ?? 'ask';
}

export default class RequestSessionService extends Service {
  @tracked chosen: RequestSession = recalled();

  choose(chosen: RequestSession): void {
    this.chosen = chosen;
    keep(KEPT, chosen);
  }

  remember(visible: boolean): void {
    this.choose(visible ? 'visible' : 'invisible');
  }
}
