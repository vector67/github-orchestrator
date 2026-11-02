import Component from '@glimmer/component';
import { service } from '@ember/service';
import { waitForPromise } from '@ember/test-waiters';
import didInsert from 'frontend/modifiers/did-insert';
import type HereService from 'frontend/services/here';
import type StoreService from 'frontend/services/store';

export interface QuestionMovedSignature {
  Element: HTMLSpanElement;
  Args: { moved: string };
}

export default class QuestionMoved extends Component<QuestionMovedSignature> {
  @service declare here: HereService;
  @service declare store: StoreService;

  count = () => {
    const pr = this.here.pr;
    if (pr) void waitForPromise(this.store.readPrCommits(pr, 'origin'));
  };

  <template>
    <span
      class="question-moved"
      data-test-question-moved
      {{didInsert this.count}}
      ...attributes
    >{{@moved}}</span>
  </template>
}
