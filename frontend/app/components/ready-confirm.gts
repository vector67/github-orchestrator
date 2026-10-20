import type { TOC } from '@ember/component/template-only';
import { hash } from '@ember/helper';
import { on } from '@ember/modifier';
import { LinkTo } from '@ember/routing';
import type { Outstanding } from 'frontend/services/store';
import modal from 'frontend/modifiers/modal';

interface ReadyConfirmSignature {
  Args: {
    repo: string;
    number: number;
    outstanding: Outstanding | null;
    mark: () => void;
    cancel: () => void;
  };
}

const answering =
  (mark: () => void) =>
  (key: string): boolean => {
    if (key !== 'y') return false;
    mark();
    return true;
  };

const submitted = (mark: () => void) => (event: Event) => {
  event.preventDefault();
  mark();
};

const anything = (outstanding: Outstanding | null): boolean =>
  (outstanding?.total ?? 0) > 0;

const sentenceOf = (outstanding: Outstanding | null): string => {
  const total = outstanding?.total ?? 0;
  return total === 1
    ? 'You have 1 outstanding item.'
    : `You have ${total} outstanding items.`;
};

const isFirst = (index: number): boolean => index === 0;

const threadAt = (repo: string, number: number, key: string): string[] => [
  ...repo.split('/'),
  String(number),
  key,
];

const inATab = (event: MouseEvent): void => {
  event.preventDefault();
  const link = event.currentTarget as HTMLAnchorElement;
  window.open(link.getAttribute('href') ?? link.href, '_blank');
};

const ReadyConfirm: TOC<ReadyConfirmSignature> = <template>
  <div class="decide-dialog">
    <form
      class="ready"
      role="dialog"
      aria-modal="true"
      aria-labelledby="ready-confirm-question"
      tabindex="-1"
      data-test-ready-confirm
      {{modal @cancel (answering @mark)}}
      {{on "submit" (submitted @mark)}}
    >
      <header class="dialog-head">
        <p class="question" id="ready-confirm-question">Mark #{{@number}}
          ready for review?</p>
        <button
          type="button"
          class="dialog-close"
          aria-label="cancel"
          {{on "click" @cancel}}
        >×</button>
      </header>
      {{#if (anything @outstanding)}}
        <p class="note">{{sentenceOf @outstanding}}</p>
        <div class="outstanding">
          {{#each @outstanding.groups key="kind" as |group index|}}
            <details
              class="outstanding-kind"
              open={{isFirst index}}
              data-test-outstanding={{group.kind}}
            >
              <summary><span class="outstanding-count">{{group.count}}</span>
                {{group.label}}</summary>
              <ul class="outstanding-items">
                {{#each group.items key="key" as |item|}}
                  <li
                    class="outstanding-item"
                    data-test-outstanding-item={{item.key}}
                  >
                    {{#if item.thread}}
                      <LinkTo
                        @route="conversations.detail"
                        @models={{threadAt @repo @number item.thread}}
                        @query={{hash back="close"}}
                        class="outstanding-where outstanding-link"
                        target="_blank"
                        title="open the thread in a new tab; Back there closes it"
                        {{on "click" inATab}}
                      >{{item.where}}<span
                          class="outstanding-opens"
                          aria-hidden="true"
                          data-test-opens-a-tab
                        >↗</span></LinkTo>
                    {{else}}
                      <span class="outstanding-where">{{item.where}}</span>
                    {{/if}}
                    <span class="outstanding-what">{{item.what}}</span>
                  </li>
                {{/each}}
              </ul>
            </details>
          {{/each}}
        </div>
      {{else}}
        <p class="note">Nothing outstanding.</p>
      {{/if}}
      <div class="dialog-actions">
        <button type="submit" class="primary" data-test-ready-option>{{if
            (anything @outstanding)
            "Mark ready anyway"
            "Mark it ready"
          }}
          <kbd>y</kbd></button>
        <button
          type="button"
          class="ghost"
          data-test-ready-cancel
          {{on "click" @cancel}}
        >Cancel <kbd>Esc</kbd></button>
      </div>
    </form>
  </div>
</template>;

export default ReadyConfirm;
