import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { hash } from '@ember/helper';
import { on } from '@ember/modifier';
import { LinkTo } from '@ember/routing';
import type { AssignReviewersRequest } from 'frontend/data/api';
import type { Outstanding, ReviewerGroup } from 'frontend/services/store';
import modal from 'frontend/modifiers/modal';
import AssignReviewers from 'frontend/components/assign-reviewers';

interface ReadyConfirmSignature {
  Args: {
    repo: string;
    number: number;
    outstanding: Outstanding | null;
    groups: ReviewerGroup[] | null;
    mark: (pick: AssignReviewersRequest) => void;
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
  @tracked pick: AssignReviewersRequest = { reviewers: [], detailed: null };
  @tracked picking = false;

  get unreviewed(): boolean {
    return (
      this.args.outstanding?.groups.some(
        (group) => group.kind === 'reviewers',
      ) ?? false
    );
  }

  get asking(): number {
    return this.pick.reviewers.length;
  }

  get outstanding(): Outstanding | null {
    const outstanding = this.args.outstanding;
    if (!outstanding || !this.asking) return outstanding;
    const groups = outstanding.groups.filter(
      (group) => group.kind !== 'reviewers',
    );
    return {
      groups,
      total: groups.reduce((sum, group) => sum + group.count, 0),
    };
  }

  get option(): string {
    if (this.asking) return `Mark ready and assign ${this.asking}`;
    return anything(this.outstanding) ? 'Mark ready anyway' : 'Mark it ready';
  }

  openPicker = () => {
    this.picking = true;
  };

  closePicker = () => {
    this.picking = false;
  };

  chosen = (pick: AssignReviewersRequest) => {
    this.pick = pick;
    this.picking = false;
  };

  mark = () => {
    this.args.mark(this.pick);
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
        {{#if (anything this.outstanding)}}
          <p class="note">{{sentenceOf this.outstanding}}</p>
          <div class="outstanding">
            {{#each this.outstanding.groups key="kind" as |group index|}}
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
                    data-test-ready-assign
                    {{on "click" this.openPicker}}
                  >Assign reviewers <kbd>⇧R</kbd></button>
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
          @pick={{this.pick}}
          @action="Assign them once ready"
          @assign={{this.chosen}}
          @cancel={{this.closePicker}}
        />
      {{/if}}
    </div>
  </template>
}
