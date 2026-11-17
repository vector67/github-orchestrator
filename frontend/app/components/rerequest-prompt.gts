import Component from '@glimmer/component';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import modal from 'frontend/modifiers/modal';
import type StoreService from 'frontend/services/store';
import type {
  CommentStory,
  RerequestPrompt as Prompt,
} from 'frontend/services/store';

interface RerequestPromptSignature {
  Args: {
    prompt: Prompt;
    label: string;
    rerequest: () => void;
    only: () => void;
    cancel: () => void;
  };
}

const answering =
  (rerequest: () => void, only: () => void) =>
  (key: string): boolean => {
    if (key === 'r') rerequest();
    else if (key === 'o') only();
    else return false;
    return true;
  };

export default class RerequestPrompt extends Component<RerequestPromptSignature> {
  @service declare store: StoreService;

  storyOf = (key: string): CommentStory =>
    this.store.commentStory(
      this.args.prompt.repo,
      this.args.prompt.number,
      key,
    );

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
        {{modal @cancel (answering @rerequest @only)}}
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
        <div class="outstanding">
          <details class="outstanding-kind" data-test-rerequest-comments>
            <summary><span
                class="outstanding-count"
              >{{@prompt.comments.length}}</span>
              {{@prompt.listed}}</summary>
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
                    <span class="state-chips">
                      {{#each comment.outcomes key="@identity" as |outcome|}}
                        <span
                          class="state-chip tone-plain"
                          data-test-rerequest-chip
                        >{{outcome}}</span>
                      {{/each}}
                    </span>
                  </li>
                {{/let}}
              {{/each}}
            </ul>
          </details>
        </div>
        <div class="dialog-actions">
          <button
            type="button"
            class="primary"
            data-test-rerequest-and
            {{on "click" @rerequest}}
          >{{@label}} and re-request <kbd>r</kbd></button>
          <button
            type="button"
            data-test-rerequest-only
            {{on "click" @only}}
          >{{@label}} only <kbd>o</kbd></button>
        </div>
      </form>
    </div>
  </template>
}
