import Component from '@glimmer/component';
import { service } from '@ember/service';
import PanelView from 'frontend/components/panel';
import { panelOf, type Panel } from 'frontend/data/panel';
import didChange from 'frontend/modifiers/did-change';
import type HereService from 'frontend/services/here';
import type StoreService from 'frontend/services/store';
import type { ThreadCard } from 'frontend/services/store';
import type ThreadsService from 'frontend/services/threads';

export const WAITING_FOR_FACTS =
  'Waiting for the first poll to say whose pull request this is.';

export interface ThreadPanelSignature {
  Args: { key: string };
}

function scrollToWhereItOpens(panel: HTMLElement) {
  panel.closest('#panel')?.scrollTo(0, 0);
  panel.querySelector('#panel-thread')?.scrollTo(0, 0);
  panel.querySelector('[data-mention]')?.scrollIntoView({ block: 'center' });
}

export default class ThreadPanel extends Component<ThreadPanelSignature> {
  @service declare threads: ThreadsService;
  @service declare here: HereService;
  @service declare store: StoreService;

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

  get card(): ThreadCard | null {
    const pr = this.here.pr;
    return pr && this.store.threadCard(pr.repo, pr.number, this.args.key);
  }

  get building(): boolean {
    return this.card?.card === 'building';
  }

  get missing(): ThreadCard | null {
    const card = this.card;
    return card?.card === 'missing' ? card : null;
  }

  watch = (element: HTMLElement, key?: unknown) => {
    if (key !== this.scrolledFor) scrollToWhereItOpens(element);
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
    {{else if this.building}}
      <p class="work-placeholder" data-test-card-building>
        Building the card for this mention. The watcher makes it on its next
        poll, and it opens here once it is ready.
      </p>
    {{else if this.missing}}
      <p class="work-placeholder" data-test-card-missing>
        No card could be made for this mention: the watcher polled the pull
        request after it was asked for and none appeared.
        <a
          href={{this.missing.url}}
          target="_blank"
          rel="noopener noreferrer"
        >See it on GitHub</a>.
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
