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

const ANSWER_KEPT = 'answer-session';

function recalled(key: string): RequestSession {
  const kept = recall(key);
  return REQUEST_SESSIONS.find((one) => one === kept) ?? 'ask';
}

export default class RequestSessionService extends Service {
  @tracked chosen: RequestSession = recalled(KEPT);
  @tracked answering: RequestSession = recalled(ANSWER_KEPT);

  choose(chosen: RequestSession): void {
    this.chosen = chosen;
    keep(KEPT, chosen);
  }

  remember(visible: boolean): void {
    this.choose(visible ? 'visible' : 'invisible');
  }

  chooseAnswering(chosen: RequestSession): void {
    this.answering = chosen;
    keep(ANSWER_KEPT, chosen);
  }

  rememberAnswering(visible: boolean): void {
    this.chooseAnswering(visible ? 'visible' : 'invisible');
  }
}
