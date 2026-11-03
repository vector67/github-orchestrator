import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { fn } from '@ember/helper';
import { on } from '@ember/modifier';
import type Owner from '@ember/owner';
import type { AssignReviewersRequest } from 'frontend/data/api';
import type { Reviewer, ReviewerGroup } from 'frontend/services/store';
import didChange from 'frontend/modifiers/did-change';
import modal from 'frontend/modifiers/modal';

interface AssignReviewersSignature {
  Args: {
    number: number;
    groups: ReviewerGroup[] | null;
    draft: boolean;
    pick: AssignReviewersRequest | null;
    assign: (pick: AssignReviewersRequest) => void;
    assignWhenReady: (pick: AssignReviewersRequest) => void;
    cancel: () => void;
  };
}

const NOBODY: AssignReviewersRequest = { reviewers: [], detailed: null };

const wordsOf = (person: Reviewer): string[] =>
  [person.login, person.name ?? ''].map((word) => word.toLowerCase());

const matching = (groups: ReviewerGroup[], typed: string): ReviewerGroup[] => {
  const query = typed.trim().toLowerCase();
  return groups
    .map((group) => ({
      ...group,
      people: group.people.filter((one) =>
        wordsOf(one).some((word) => word.includes(query)),
      ),
    }))
    .filter((group) => group.people.length > 0);
};

const inOrder = (people: Reviewer[], logins: Set<string>): string[] =>
  people.map((one) => one.login).filter((login) => logins.has(login));

const toggled = (
  people: Reviewer[],
  pick: AssignReviewersRequest,
  login: string,
): AssignReviewersRequest => {
  const logins = new Set(pick.reviewers);
  if (logins.delete(login)) {
    return {
      reviewers: inOrder(people, logins),
      detailed: pick.detailed === login ? null : pick.detailed,
    };
  }
  return {
    reviewers: inOrder(people, logins.add(login)),
    detailed: pick.detailed,
  };
};

const starred = (
  people: Reviewer[],
  pick: AssignReviewersRequest,
  login: string,
): AssignReviewersRequest => {
  if (pick.detailed === login) return { ...pick, detailed: null };
  return {
    reviewers: inOrder(people, new Set(pick.reviewers).add(login)),
    detailed: login,
  };
};

const revealed = (element: HTMLElement, current?: unknown): void => {
  if (current) element.scrollIntoView({ block: 'nearest' });
};

export default class AssignReviewers extends Component<AssignReviewersSignature> {
  @tracked pick: AssignReviewersRequest;
  @tracked typed = '';
  @tracked at = 0;
  private search: HTMLElement | null = null;

  constructor(owner: Owner, args: AssignReviewersSignature['Args']) {
    super(owner, args);
    this.pick = args.pick ?? NOBODY;
  }

  get everyone(): Reviewer[] {
    return (this.args.groups ?? []).flatMap((group) => group.people);
  }

  get shown(): ReviewerGroup[] {
    return matching(this.args.groups ?? [], this.typed);
  }

  get listed(): Reviewer[] {
    return this.shown.flatMap((group) => group.people);
  }

  get highlighted(): Reviewer | undefined {
    return this.listed[this.at];
  }

  get asking(): boolean {
    return this.args.groups === null;
  }

  get nobodyToAsk(): boolean {
    return !this.asking && this.everyone.length === 0;
  }

  get nobody(): boolean {
    return this.pick.reviewers.length === 0;
  }

  isAt = (person: Reviewer): boolean => this.highlighted === person;

  picked = (login: string): boolean => this.pick.reviewers.includes(login);

  isDetailed = (login: string): string => String(this.pick.detailed === login);

  remember = (element: HTMLElement) => {
    this.search = element;
  };

  toggle = (login: string) => {
    this.pick = toggled(this.everyone, this.pick, login);
    this.search?.focus();
  };

  star = (login: string) => {
    this.pick = starred(this.everyone, this.pick, login);
    this.search?.focus();
  };

  typing = (event: Event) => {
    this.typed = (event.target as HTMLInputElement).value;
    this.at = 0;
  };

  keyed = (event: KeyboardEvent) => {
    const one = this.highlighted;
    if (event.key === 'ArrowDown') this.step(1);
    else if (event.key === 'ArrowUp') this.step(-1);
    else if (event.key === ' ') {
      if (one) this.toggle(one.login);
    } else if (event.key === '*') {
      if (one) this.star(one.login);
    } else if (event.key === 'Enter') this.assign();
    else return;
    event.preventDefault();
  };

  private step(by: number): void {
    this.at = Math.max(0, Math.min(this.listed.length - 1, this.at + by));
  }

  get primary(): string {
    return this.args.draft ? 'Assign when ready for review' : 'Assign now';
  }

  assign = () => {
    if (this.nobody) return;
    if (this.args.draft) this.args.assignWhenReady(this.pick);
    else this.args.assign(this.pick);
  };

  assignNow = () => {
    if (!this.nobody) this.args.assign(this.pick);
  };

  answering = (key: string): boolean => {
    if (key !== 'y') return false;
    this.assign();
    return true;
  };

  submitted = (event: Event) => {
    event.preventDefault();
    this.assign();
  };

  <template>
    <div class="decide-dialog">
      <form
        class="assign"
        role="dialog"
        aria-modal="true"
        aria-labelledby="assign-reviewers-question"
        tabindex="-1"
        data-test-assign-reviewers
        {{modal @cancel this.answering}}
        {{on "submit" this.submitted}}
      >
        <header class="dialog-head">
          <p class="question" id="assign-reviewers-question">Assign reviewers to
            #{{@number}}</p>
          <button
            type="button"
            class="dialog-close"
            aria-label="cancel"
            {{on "click" @cancel}}
          >×</button>
        </header>
        <input
          type="search"
          class="reviewer-search"
          placeholder="Type a login or a name"
          aria-label="find someone to ask"
          autocomplete="off"
          value={{this.typed}}
          data-test-reviewer-search
          {{didChange this.remember}}
          {{on "input" this.typing}}
          {{on "keydown" this.keyed}}
        />
        {{#if this.asking}}
          <p class="note" data-test-reviewers-asking>Asking GitHub who can
            review…</p>
        {{else if this.nobodyToAsk}}
          <p class="note">Nobody to ask yet: GitHub has not said who can review.</p>
        {{else if this.listed.length}}
          <div class="reviewer-groups">
            {{#each this.shown key="@index" as |group|}}
              {{#if group.label}}
                <h3
                  class="reviewer-group"
                  data-test-reviewer-group
                >{{group.label}}</h3>
              {{/if}}
              <ul class="reviewer-list">
                {{#each group.people key="login" as |person|}}
                  <li
                    class="reviewer-row"
                    aria-current={{if (this.isAt person) "true"}}
                    data-test-reviewer={{person.login}}
                    {{didChange revealed (this.isAt person)}}
                  >
                    <label class="reviewer-name">
                      <input
                        type="checkbox"
                        tabindex="-1"
                        checked={{this.picked person.login}}
                        {{on "change" (fn this.toggle person.login)}}
                      />
                      <span
                        class="reviewer-login"
                        data-test-login
                      >{{person.login}}</span>
                      {{#if person.name}}
                        <span class="reviewer-fullname">{{person.name}}</span>
                      {{/if}}
                    </label>
                    {{#if person.asked}}
                      <span
                        class="reviewer-asked"
                        title="asked on {{person.asked}} of the repository’s recent pull requests"
                        data-test-asked
                      >{{person.asked}}</span>
                    {{/if}}
                    <button
                      type="button"
                      class="btn"
                      tabindex="-1"
                      aria-pressed={{this.isDetailed person.login}}
                      title="Detailed reviewer: named on the description’s Detailed reviewer line"
                      data-test-detailed={{person.login}}
                      {{on "click" (fn this.star person.login)}}
                    >★ detailed</button>
                  </li>
                {{/each}}
              </ul>
            {{/each}}
          </div>
        {{else}}
          <p class="note" data-test-reviewers-none>Nobody matches
            {{this.typed}}.</p>
        {{/if}}
        <p class="note reviewer-keys"><kbd>↑</kbd>
          <kbd>↓</kbd>
          move ·
          <kbd>Space</kbd>
          picks ·
          <kbd>*</kbd>
          stars the detailed reviewer ·
          <kbd>↵</kbd>
          {{this.primary}}</p>
        <div class="dialog-actions">
          <button
            type="submit"
            class="primary"
            disabled={{this.nobody}}
            data-test-assign-option
          >{{this.primary}} <kbd>↵</kbd></button>
          {{#if @draft}}
            <button
              type="button"
              class="btn"
              disabled={{this.nobody}}
              data-test-assign-now
              {{on "click" this.assignNow}}
            >Assign now</button>
          {{/if}}
          <button
            type="button"
            class="ghost"
            data-test-assign-cancel
            {{on "click" @cancel}}
          >Cancel <kbd>Esc</kbd></button>
        </div>
      </form>
    </div>
  </template>
}
