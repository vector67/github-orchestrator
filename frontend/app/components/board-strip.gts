import Component from '@glimmer/component';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import { LinkTo } from '@ember/routing';
import ReviewDialog from 'frontend/components/review-dialog';
import type RouterService from '@ember/routing/router-service';
import type ReviewService from 'frontend/services/review';
import type { Header } from 'frontend/services/threads';

export interface BoardStripSignature {
  Element: HTMLElement;
  Args: { header: Header | null };
}

export default class BoardStrip extends Component<BoardStripSignature> {
  @service declare review: ReviewService;
  @service declare router: RouterService;

  get onQueue(): boolean {
    return this.router.isActive('conversations');
  }

  get onColumns(): boolean {
    return this.router.isActive('board');
  }

  get sendLabel(): string {
    const count = this.review.review.enrolled.length;
    return count ? `Send review · ${count}` : 'Send review';
  }

  <template>
    <div id="board-strip" data-test-board-strip ...attributes>
      <span class="views seg">
        <LinkTo
          @route="conversations"
          class="view"
          aria-current={{if this.onQueue "page"}}
          data-test-view="queue"
        >Queue</LinkTo>
        <LinkTo
          @route="board"
          class="view"
          aria-current={{if this.onColumns "page"}}
          data-test-view="board"
        >Columns</LinkTo>
      </span>
      <span class="counts">
        {{#each @header.counts key="key" as |count|}}
          <span class="count" data-test-count={{count.key}}>
            <span class="count-number">{{count.count}}</span>
            <span class="count-label">{{count.label}}</span>
          </span>
        {{/each}}
      </span>
      <LinkTo
        @route="conversations.new-draft"
        class="new-draft btn"
        data-test-new-draft
      >New draft</LinkTo>
      <button
        type="button"
        class="send-review btn fill"
        data-test-send-review
        title="send one review carrying every draft you have added (S)"
        {{on "click" this.review.show}}
      >{{this.sendLabel}}</button>
    </div>
    {{#if this.review.open}}
      <ReviewDialog />
    {{/if}}
  </template>
}
