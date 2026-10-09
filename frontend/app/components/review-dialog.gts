import Component from '@glimmer/component';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import { fn } from '@ember/helper';
import type { ReviewVerdict } from 'frontend/data/api';
import modal from 'frontend/modifiers/modal';
import type ReviewService from 'frontend/services/review';

const VERDICTS: { value: ReviewVerdict; label: string }[] = [
  { value: 'COMMENT', label: 'Comment' },
  { value: 'REQUEST_CHANGES', label: 'Request changes' },
  { value: 'APPROVE', label: 'Approve' },
];

function counted(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? '' : 's'}`;
}

function is(one: unknown, other: unknown): boolean {
  return one === other;
}

export default class ReviewDialog extends Component {
  @service declare review: ReviewService;

  readonly verdicts = VERDICTS;

  get leftOpen(): string {
    const { unanswered, unadded } = this.review.review;
    const parts = [
      unanswered
        ? `${counted(unanswered, 'thread')} of yours the author has not answered`
        : '',
      unadded.length
        ? `${counted(unadded.length, 'draft')} you have not added`
        : '',
    ].filter(Boolean);
    return parts.length ? `Left open: ${parts.join(', and ')}.` : '';
  }

  get summaryNote(): string {
    return this.review.needsSummary
      ? 'GitHub takes no comment or change request without a summary.'
      : 'Optional on an approval.';
  }

  get goesOut(): boolean {
    const { enrolled, pendingOnGitHub } = this.review.review;
    return enrolled.length + pendingOnGitHub.length > 0;
  }

  pick = (verdict: ReviewVerdict) => {
    this.review.verdict = verdict;
  };

  type = (event: Event) => {
    this.review.body = (event.target as HTMLTextAreaElement).value;
  };

  send = (event: Event) => {
    event.preventDefault();
    void this.review.send();
  };

  <template>
    <div class="decide-dialog review-dialog" data-test-review>
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby="review-dialog-question"
        tabindex="-1"
        {{modal this.review.close}}
        {{on "submit" this.send}}
      >
        <header class="dialog-head">
          <p class="question" id="review-dialog-question">Send your review</p>
          <button
            type="button"
            class="dialog-close"
            aria-label="close"
            data-test-review-close
            {{on "click" this.review.close}}
          >×</button>
        </header>
        <fieldset class="verdicts">
          <legend class="dialog-kicker">Decision</legend>
          {{#each this.verdicts key="value" as |verdict|}}
            <label class="dialog-tick">
              <input
                type="radio"
                name="verdict"
                value={{verdict.value}}
                checked={{is this.review.verdict verdict.value}}
                data-test-verdict={{verdict.value}}
                {{on "change" (fn this.pick verdict.value)}}
              />
              {{verdict.label}}
            </label>
          {{/each}}
        </fieldset>
        <textarea
          aria-label="the review's summary"
          data-test-review-body
          rows="4"
          placeholder="What the author should know first…"
          value={{this.review.body}}
          {{on "input" this.type}}
        ></textarea>
        <p class="note">{{this.summaryNote}}</p>
        {{#if this.goesOut}}
          <p class="dialog-kicker">Going out with it</p>
          <ul class="review-drafts">
            {{#each this.review.review.enrolled key="key" as |one|}}
              <li class="review-draft" data-test-review-draft={{one.key}}>
                <span class="review-where">{{one.where}}</span>
                <span class="review-words">{{one.body}}</span>
                <span class="review-draft-tools">
                  <button
                    type="button"
                    class="ghost"
                    data-test-edit
                    {{on "click" (fn this.review.edit one.key)}}
                  >Edit</button>
                  <button
                    type="button"
                    class="ghost"
                    data-test-leave-out
                    {{on "click" (fn this.review.leaveOut one.key)}}
                  >Leave out</button>
                </span>
              </li>
            {{/each}}
            {{#each this.review.review.pendingOnGitHub key="key" as |one|}}
              <li
                class="review-draft"
                data-test-review-github-draft={{one.key}}
              >
                <span class="review-where">{{one.where}}</span>
                <span class="review-words">{{one.body}}</span>
                <span class="review-draft-tools note">from GitHub</span>
              </li>
            {{/each}}
          </ul>
        {{else}}
          <p class="note" data-test-review-empty>No drafts go out with it; the
            summary is the whole review.</p>
        {{/if}}
        {{#if this.review.review.unadded}}
          <p class="dialog-kicker">Local drafts, not in the review</p>
          <ul class="review-drafts">
            {{#each this.review.review.unadded key="key" as |one|}}
              <li class="review-draft" data-test-review-unadded={{one.key}}>
                <span class="review-where">{{one.where}}</span>
                <span class="review-words">{{one.body}}</span>
                <span class="review-draft-tools">
                  <button
                    type="button"
                    class="ghost"
                    data-test-add
                    {{on "click" (fn this.review.add one.key)}}
                  >Add to review</button>
                </span>
              </li>
            {{/each}}
          </ul>
        {{/if}}
        {{#if this.leftOpen}}
          <p class="note" data-test-left-open>{{this.leftOpen}}</p>
        {{/if}}
        <p class="note" data-test-review-public>Sending posts the review to
          GitHub now; the board cannot take it back.</p>
        {{#if this.review.inFlight}}
          <p class="note" data-test-review-state>Sending your review…</p>
        {{/if}}
        {{#if this.review.trouble}}
          <p class="land-error" data-test-review-trouble>
            {{this.review.trouble}}
          </p>
        {{/if}}
        <div class="dialog-actions">
          <button
            type="submit"
            class="primary"
            data-test-review-send
            disabled={{this.review.unsendable}}
          >Send review</button>
          <button
            type="button"
            class="ghost"
            data-test-review-cancel
            {{on "click" this.review.close}}
          >Cancel</button>
        </div>
      </form>
    </div>
  </template>
}
