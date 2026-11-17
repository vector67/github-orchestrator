import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import { waitForPromise } from '@ember/test-waiters';
import modal from 'frontend/modifiers/modal';
import type StoreService from 'frontend/services/store';
import type {
  CommentStory,
  RerequestPrompt as Prompt,
} from 'frontend/services/store';

interface RerequestPromptSignature {
  Args: {
    prompt: Prompt;
    label: string | null;
    rerequest: () => void;
    only: () => void;
    cancel: () => void;
  };
}

const answering =
  (rerequest: () => void, only: () => void, onlyKey: string) =>
  (key: string): boolean => {
    if (key === 'r') rerequest();
    else if (key === onlyKey) only();
    else return false;
    return true;
  };

export default class RerequestPrompt extends Component<RerequestPromptSignature> {
  @service declare store: StoreService;

  get rerequestLabel(): string {
    const label = this.args.label;
    return label === null ? 'Re-request review' : `${label} and re-request`;
  }

  get onlyLabel(): string {
    const label = this.args.label;
    return label === null ? 'Not yet' : `${label} only`;
  }

  get onlyKey(): string {
    return this.args.label === null ? 'n' : 'o';
  }

  storyOf = (key: string): CommentStory =>
    this.store.commentStory(
      this.args.prompt.repo,
      this.args.prompt.number,
      key,
    );

  @tracked listing = false;

  @tracked private opened: string[] = [];

  toggleListing = () => {
    this.listing = !this.listing;
  };

  isOpen = (key: string): boolean => this.opened.includes(key);

  toggle = (key: string) => () => {
    if (this.isOpen(key)) {
      this.opened = this.opened.filter((one) => one !== key);
      return;
    }
    this.opened = [...this.opened, key];
    void waitForPromise(this.store.readThread(this.args.prompt, key));
  };

  <template>
    <div class="decide-dialog">
      <form
        class="hold-warning rerequest-prompt"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="rerequest-prompt-question"
        aria-describedby="rerequest-prompt-note"
        tabindex="-1"
        data-test-rerequest-prompt
        {{modal @cancel (answering @rerequest @only this.onlyKey)}}
      >
        <header class="dialog-head">
          <p class="dialog-kicker" data-test-rerequest-kicker>Last comment from
            {{@prompt.reviewer}}</p>
          <button
            type="button"
            class="dialog-close"
            aria-label="cancel"
            data-test-rerequest-cancel
            {{on "click" @cancel}}
          >×</button>
        </header>
        <p
          class="question"
          id="rerequest-prompt-question"
          data-test-rerequest-question
        >Re-request {{@prompt.reviewer}}'s review of #{{@prompt.number}}?</p>
        <p class="rerequest-standing"><span
            class="state-chip
              {{if @prompt.badge.alarm 'tone-alarm' 'tone-plain'}}"
            data-test-rerequest-badge
          >{{@prompt.badge.text}}</span></p>
        <p
          class="note"
          id="rerequest-prompt-note"
          data-test-rerequest-summary
        >{{@prompt.summary}}</p>
        {{#if @prompt.flag}}
          <p class="note" data-test-rerequest-flag><strong
            >{{@prompt.flag}}</strong></p>
        {{/if}}
        {{#if @prompt.comments.length}}
          <div class="outstanding">
            <section class="outstanding-kind">
              <button
                type="button"
                class="outstanding-head rerequest-listing"
                aria-expanded={{if this.listing "true" "false"}}
                data-test-rerequest-comments
                {{on "click" this.toggleListing}}
              ><span aria-hidden="true">{{if this.listing "▼" "▶"}}</span><span
                  class="outstanding-count"
                >{{@prompt.comments.length}}</span>
                {{@prompt.listed}}</button>
              {{#if this.listing}}
                <ul class="outstanding-items">
                  {{#each @prompt.comments key="key" as |comment|}}
                    {{#let (this.storyOf comment.key) as |story|}}
                      <li
                        class="outstanding-item"
                        data-test-rerequest-comment={{comment.key}}
                      >
                        <span
                          class="outstanding-where"
                          data-test-rerequest-where
                        >{{comment.where}}</span>
                        {{#if story.what}}
                          <span
                            class="outstanding-what"
                            data-test-rerequest-what
                          >{{story.what}}</span>
                        {{/if}}
                        <span class="rerequest-chips">
                          {{#each
                            comment.outcomes key="@identity"
                            as |outcome|
                          }}
                            <span
                              class="state-chip tone-plain"
                              data-test-rerequest-chip
                            >{{outcome}}</span>
                          {{/each}}
                        </span>
                        <button
                          type="button"
                          class="rerequest-history"
                          aria-expanded={{if
                            (this.isOpen comment.key)
                            "true"
                            "false"
                          }}
                          data-test-history
                          {{on "click" (this.toggle comment.key)}}
                        ><span aria-hidden="true">{{if
                              (this.isOpen comment.key)
                              "▼"
                              "▶"
                            }}</span>
                          History</button>
                        {{#if (this.isOpen comment.key)}}
                          <ol class="rerequest-history-entries">
                            {{#each story.history key="@index" as |entry|}}
                              <li
                                class="rerequest-history-entry"
                                data-test-history-entry
                              >
                                <time
                                  class="outstanding-where"
                                  datetime={{entry.at}}
                                >{{entry.when}}</time>
                                <span
                                  data-test-history-what
                                >{{entry.what}}</span>
                              </li>
                            {{/each}}
                          </ol>
                        {{/if}}
                      </li>
                    {{/let}}
                  {{/each}}
                </ul>
              {{/if}}
            </section>
          </div>
        {{/if}}
        <div class="dialog-actions">
          <button
            type="button"
            class="primary"
            data-test-rerequest-and
            {{on "click" @rerequest}}
          >{{this.rerequestLabel}} <kbd>r</kbd></button>
          <button
            type="button"
            data-test-rerequest-only
            {{on "click" @only}}
          >{{this.onlyLabel}} <kbd>{{this.onlyKey}}</kbd></button>
        </div>
      </form>
    </div>
  </template>
}
