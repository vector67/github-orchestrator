import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { on } from '@ember/modifier';
import { service } from '@ember/service';
import { waitForPromise } from '@ember/test-waiters';
import CommentBody from 'frontend/components/comment-body';
import type { Comment } from 'frontend/data/api';
import modal from 'frontend/modifiers/modal';
import type HereService from 'frontend/services/here';
import type StoreService from 'frontend/services/store';

const SEEN = 'answer-replies-seen';

interface Reply {
  key: string;
  comment: number;
  author: string;
}

function seenOf(reply: Reply): string {
  return `${reply.key}:${reply.comment}`;
}

function remembered(): string[] {
  try {
    const kept: unknown = JSON.parse(localStorage.getItem(SEEN) ?? '[]');
    return Array.isArray(kept) ? kept.map(String) : [];
  } catch {
    return [];
  }
}

function remember(seen: string[]): void {
  try {
    localStorage.setItem(SEEN, JSON.stringify(seen));
  } catch {
    return;
  }
}

export default class AnswerReply extends Component {
  @service declare here: HereService;
  @service declare store: StoreService;

  @tracked seen: string[] = remembered();
  @tracked open: Reply | null = null;

  get reply(): Reply | null {
    const pr = this.here.pr;
    const answering = pr
      ? (this.store.summary(pr.repo, pr.number)?.answering ?? [])
      : [];
    return answering.find((one) => !this.seen.includes(seenOf(one))) ?? null;
  }

  get comments(): Comment[] {
    const pr = this.here.pr;
    const open = this.open;
    if (!pr || !open) return [];
    return this.store.details(pr.repo, pr.number, open.key)?.comments ?? [];
  }

  get newest(): Comment | undefined {
    return this.comments.find((one) => one.id === this.open?.comment);
  }

  marked = (comment: Comment): boolean => comment.id === this.open?.comment;

  private done(reply: Reply): void {
    this.seen = [...this.seen, seenOf(reply)];
    remember(this.seen);
  }

  see = () => {
    const reply = this.reply;
    const pr = this.here.pr;
    if (!reply || !pr) return;
    this.open = reply;
    this.done(reply);
    void waitForPromise(this.store.readThread(pr, reply.key));
  };

  dismiss = () => {
    if (this.reply) this.done(this.reply);
  };

  close = () => {
    this.open = null;
  };

  copy = () => {
    const body = this.newest?.body;
    if (body) void navigator.clipboard.writeText(body);
  };

  <template>
    {{#if this.reply}}
      <div class="answer-reply" role="status" data-test-answer-reply>
        <p class="answer-reply-text">
          <strong>{{this.reply.author}} replied</strong>
          to the thread you're answering
        </p>
        <button
          type="button"
          class="answer-reply-dismiss"
          aria-label="Dismiss"
          data-test-dismiss-reply
          {{on "click" this.dismiss}}
        >×</button>
        <button
          type="button"
          class="answer-reply-see"
          data-test-see-reply
          {{on "click" this.see}}
        >See their comment</button>
      </div>
    {{/if}}
    {{#if this.open}}
      <div class="reply-dialog-backdrop">
        <section
          class="reply-dialog"
          role="dialog"
          aria-modal="true"
          aria-label="{{this.open.author}} replied"
          tabindex="-1"
          data-test-reply-dialog
          {{modal this.close}}
        >
          <h2 class="reply-dialog-title">{{this.open.author}} replied</h2>
          {{#each this.comments key="id" as |said|}}
            <article
              class="transcript-entry"
              data-marked={{if (this.marked said) "1"}}
              data-test-entry
            >
              <div class="entry-head">
                <span class="entry-who">{{said.author}}</span>
              </div>
              <CommentBody @body={{said.body}} />
            </article>
          {{/each}}
          <footer class="dialog-actions">
            <button
              type="button"
              data-test-close-reply
              {{on "click" this.close}}
            >Close</button>
            <button
              type="button"
              class="primary"
              data-test-copy-reply
              {{on "click" this.copy}}
            >Copy {{this.open.author}}'s reply</button>
          </footer>
        </section>
      </div>
    {{/if}}
  </template>
}
