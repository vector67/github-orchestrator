import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import { fn } from '@ember/helper';
import type RouterService from '@ember/routing/router-service';
import { pageOf } from 'frontend/data/wall';
import navigates from 'frontend/modifiers/navigates';
import type KeysService from 'frontend/services/keys';
import type { Keymap } from 'frontend/services/keys';
import type StoreService from 'frontend/services/store';
import type { MentionRow } from 'frontend/services/store';

export default class MentionsCounter extends Component {
  @service declare router: RouterService;
  @service declare store: StoreService;
  @service declare keys: KeysService;

  @tracked listing = false;

  private readonly keymap: Keymap = {
    take: (key) => {
      if (key !== 'Escape') return false;
      this.close();
      return true;
    },
  };

  willDestroy(): void {
    super.willDestroy();
    this.keys.drop(this.keymap);
  }

  get mentions(): MentionRow[] {
    return this.store.mentionRows;
  }

  open = () => {
    this.listing = true;
    this.keys.push('dialog', this.keymap);
  };

  close = () => {
    this.listing = false;
    this.keys.drop(this.keymap);
  };

  hrefOf = (mention: MentionRow): string =>
    pageOf(
      { repo: mention.repo, number: mention.number },
      `/conversations/${encodeURIComponent(mention.thread ?? '')}`,
    );

  go = async (mention: MentionRow): Promise<void> => {
    this.close();
    await this.router.transitionTo(this.hrefOf(mention));
  };

  <template>
    <span class="mentions">
      <button
        type="button"
        class="mentions-count {{if this.mentions.length 'outstanding'}}"
        aria-haspopup="true"
        aria-expanded={{if this.listing "true" "false"}}
        title="comments naming you that the board has not closed"
        data-test-mentions-count
        {{on "click" this.open}}
      >{{this.mentions.length}}</button>
      {{#if this.listing}}
        <button
          type="button"
          class="mentions-scrim"
          tabindex="-1"
          aria-label="close the mentions"
          {{on "click" this.close}}
        ></button>
        <div class="mentions-menu" data-test-mentions-menu>
          {{#each this.mentions key="url" as |mention|}}
            <div class="mention" data-test-mention={{mention.thread}}>
              <span class="mention-head">{{mention.author}}
                on
                {{mention.repo}}#{{mention.number}}</span>
              <span class="mention-body">{{mention.body}}</span>
              {{#if mention.opensOnTheBoard}}
                <a
                  href={{this.hrefOf mention}}
                  class="linkish"
                  data-test-mention-open
                  {{navigates (fn this.go mention)}}
                >Open on the board</a>
              {{else}}
                <span class="mention-off">{{if
                    mention.building
                    "card being built"
                    "not on the board"
                  }}
                  ·
                  <a
                    class="linkish"
                    href={{mention.url}}
                    target="_blank"
                    rel="noopener noreferrer"
                    data-test-mention-github
                  >open on GitHub</a></span>
              {{/if}}
            </div>
          {{else}}
            <span class="mention-none">No mentions waiting on you.</span>
          {{/each}}
        </div>
      {{/if}}
    </span>
  </template>
}
