import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import type Owner from '@ember/owner';
import { service } from '@ember/service';
import { hash } from '@ember/helper';
import { on } from '@ember/modifier';
import { LinkTo } from '@ember/routing';
import type { AssignReviewersRequest } from 'frontend/data/api';
import type StoreService from 'frontend/services/store';
import type { Outstanding, ReviewerGroup } from 'frontend/services/store';
import modal from 'frontend/modifiers/modal';
import AssignReviewers from 'frontend/components/assign-reviewers';
import Glyphs from 'frontend/components/glyphs';

interface ReadyConfirmSignature {
  Args: {
    repo: string;
    number: number;
    outstanding: Outstanding | null;
    groups: ReviewerGroup[] | null;
    mark: () => void;
    assign: (pick: AssignReviewersRequest) => void;
    assignWhenReady: (pick: AssignReviewersRequest) => void;
    cancel: () => void;
  };
}

const anything = (outstanding: Outstanding | null): boolean =>
  (outstanding?.total ?? 0) > 0;

const sentenceOf = (outstanding: Outstanding | null): string => {
  const total = outstanding?.total ?? 0;
  return total === 1
    ? 'You have 1 outstanding item.'
    : `You have ${total} outstanding items.`;
};

const isFirst = (index: number): boolean => index === 0;

const isReviewers = (kind: string): boolean => kind === 'reviewers';

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

export default class ReadyConfirm extends Component<ReadyConfirmSignature> {
  @service declare store: StoreService;

  @tracked picking = false;

  constructor(owner: Owner, args: ReadyConfirmSignature['Args']) {
    super(owner, args);
    this.store.readMentionable({ repo: args.repo, number: args.number });
  }

  get unreviewed(): boolean {
    return (
      this.args.outstanding?.groups.some(
        (group) => group.kind === 'reviewers',
      ) ?? false
    );
  }

  get option(): string {
    return anything(this.args.outstanding)
      ? 'Mark ready anyway'
      : 'Mark it ready';
  }

  openPicker = () => {
    this.picking = true;
  };

  closePicker = () => {
    this.picking = false;
  };

  assign = (pick: AssignReviewersRequest) => {
    this.picking = false;
    this.args.assign(pick);
  };

  assignWhenReady = (pick: AssignReviewersRequest) => {
    this.picking = false;
    this.args.assignWhenReady(pick);
  };

  mark = () => {
    this.args.mark();
  };

  answering = (key: string): boolean => {
    if (key === 'R' && this.unreviewed) {
      this.openPicker();
      return true;
    }
    if (key !== 'y') return false;
    this.mark();
    return true;
  };

  submitted = (event: Event) => {
    event.preventDefault();
    this.mark();
  };

  <template>
    <div class="decide-dialog">
      <form
        class="ready"
        role="dialog"
        aria-modal="true"
        aria-labelledby="ready-confirm-question"
        tabindex="-1"
        data-test-ready-confirm
        {{modal @cancel this.answering}}
        {{on "submit" this.submitted}}
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
              {{#if (isReviewers group.kind)}}
                <section
                  class="outstanding-kind outstanding-open"
                  data-test-outstanding={{group.kind}}
                >
                  <p class="outstanding-head"><span
                      aria-hidden="true"
                    >▼</span><span
                      class="outstanding-count"
                    >{{group.count}}</span>
                    {{group.label}}</p>
                  <ul class="outstanding-items">
                    {{#each group.items key="key" as |item|}}
                      <li
                        class="outstanding-item"
                        data-test-outstanding-item={{item.key}}
                      >
                        <span class="outstanding-where">{{item.where}}</span>
                        <span class="outstanding-what">{{item.what}}</span>
                      </li>
                    {{/each}}
                  </ul>
                  <button
                    type="button"
                    class="btn outstanding-assign"
                    data-opens-dialog="true"
                    data-test-ready-assign
                    {{on "click" this.openPicker}}
                  >Assign reviewers<Glyphs @opensDialog={{true}} />
                    <kbd>⇧R</kbd></button>
                </section>
              {{else}}
                <details
                  class="outstanding-kind"
                  open={{isFirst index}}
                  data-test-outstanding={{group.kind}}
                >
                  <summary><span
                      class="outstanding-count"
                    >{{group.count}}</span>
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
              {{/if}}
            {{/each}}
          </div>
        {{else}}
          <p class="note">Nothing outstanding.</p>
        {{/if}}
        <div class="dialog-actions">
          <button
            type="submit"
            class="primary"
            data-test-ready-option
          >{{this.option}}
            <kbd>y</kbd></button>
          <button
            type="button"
            class="ghost"
            data-test-ready-cancel
            {{on "click" @cancel}}
          >Cancel <kbd>Esc</kbd></button>
        </div>
      </form>
      {{#if this.picking}}
        <AssignReviewers
          @number={{@number}}
          @groups={{@groups}}
          @draft={{true}}
          @pick={{null}}
          @assign={{this.assign}}
          @assignWhenReady={{this.assignWhenReady}}
          @cancel={{this.closePicker}}
        />
      {{/if}}
    </div>
  </template>
}
