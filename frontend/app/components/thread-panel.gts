import Component from '@glimmer/component';
import { service } from '@ember/service';
import PanelView from 'frontend/components/panel';
import { panelOf, type Panel } from 'frontend/data/panel';
import didChange from 'frontend/modifiers/did-change';
import type ThreadsService from 'frontend/services/threads';

export const WAITING_FOR_FACTS =
  'Waiting for the first poll to say whose pull request this is.';

export interface ThreadPanelSignature {
  Args: { key: string };
}

function scrollToTop(panel: HTMLElement) {
  panel.closest('#panel')?.scrollTo(0, 0);
  panel.querySelector('#panel-thread')?.scrollTo(0, 0);
}

export default class ThreadPanel extends Component<ThreadPanelSignature> {
  @service declare threads: ThreadsService;

  private scrolledFor: unknown;

  get waiting(): boolean {
    return this.threads.role === null;
  }

  get panel(): Panel | null {
    const conversation = this.threads.thread(this.args.key);
    const role = this.threads.role;
    if (!conversation || !role) return null;
    return panelOf(
      conversation,
      this.threads.details(conversation.key),
      this.threads.contextFor(conversation.key, role),
      this.threads.fixOf(conversation.key),
    );
  }

  get unreadable(): boolean {
    return this.threads.unreadable.includes(this.args.key);
  }

  watch = (element: HTMLElement, key?: unknown) => {
    if (key !== this.scrolledFor) scrollToTop(element);
    this.scrolledFor = key;
    this.threads.watch(typeof key === 'string' ? key : null);
  };

  willDestroy(): void {
    super.willDestroy();
    this.threads.watch(null);
  }

  <template>
    {{#if this.panel}}
      <PanelView @panel={{this.panel}} {{didChange this.watch @key}} />
    {{else if this.waiting}}
      <p class="work-placeholder" data-test-board-waiting>
        {{WAITING_FOR_FACTS}}
      </p>
    {{else if this.unreadable}}
      <p class="work-placeholder" data-test-missing>
        This card's record could not be read.
      </p>
    {{else}}
      <p class="work-placeholder" data-test-missing>
        The board has no thread called
        {{@key}}.
      </p>
    {{/if}}
  </template>
}
