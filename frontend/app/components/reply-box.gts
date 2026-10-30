import Component from '@glimmer/component';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import type { ReplyBox } from 'frontend/data/panel';
import didInsert from 'frontend/modifiers/did-insert';
import type BoardService from 'frontend/services/board';
import type ComposerService from 'frontend/services/composer';
import autocomplete from 'frontend/modifiers/autocomplete';

export interface ReplyBoxSignature {
  Element: HTMLElement;
  Args: {
    conversationId: string;
    reply: ReplyBox;
    reviewerName: string;
  };
}

const COMPOSER = 'reply-box';

const PARKS =
  'No code change; comment moves to "Waiting on reviewer" and the ' +
  'proposal is parked.';

export default class ReplyBoxComponent extends Component<ReplyBoxSignature> {
  @service declare board: BoardService;
  @service declare composer: ComposerService;

  get open(): boolean {
    return this.composer.isOpen(this.args.conversationId);
  }

  get label(): string {
    const first = (this.args.reviewerName ?? '').split(' ')[0];
    return first ? `Reply to ${first}` : 'Reply';
  }

  get where(): string {
    return this.args.reply.threaded ? 'the GitHub thread' : 'the PR';
  }

  get placeholder(): string {
    return `${this.label}… posts to ${this.where}`;
  }

  get note(): string {
    const reply = this.args.reply;
    if (reply.note) return reply.note;
    if (reply.parks) return PARKS;
    return `Posted to ${this.where}.`;
  }

  get blocked(): boolean {
    return !this.composer.words.trim();
  }

  expand = () => {
    this.composer.open(this.args.conversationId);
  };

  focus = () => {
    document.getElementById(COMPOSER)?.focus();
  };

  fold = () => {
    this.composer.close();
  };

  type = (event: Event) => {
    this.composer.words = (event.target as HTMLTextAreaElement).value;
  };

  again = () => {
    this.composer.open(this.args.conversationId);
    this.composer.words = this.args.reply.refused?.body ?? '';
  };

  send = (event: Event) => {
    event.preventDefault();
    const words = this.composer.words.trim();
    if (!words) return;
    this.composer.close();
    void this.board.decide(this.args.conversationId, 'reply', { body: words });
  };

  <template>
    {{#if this.open}}
      <form class="reply" {{on "submit" this.send}} ...attributes>
        <textarea
          id={{COMPOSER}}
          data-test-reply
          rows="2"
          placeholder={{this.placeholder}}
          value={{this.composer.words}}
          {{on "input" this.type}}
          {{didInsert this.focus}}
          {{autocomplete}}
        ></textarea>
        <div class="reply-foot">
          <button
            type="submit"
            class="reply-send"
            data-test-reply-send
            disabled={{this.blocked}}
          >Post reply</button>
          <p class="composer-note" data-test-composer-note>{{this.note}}</p>
          <button
            type="button"
            class="reply-close"
            data-test-reply-close
            aria-label="Close reply"
            {{on "click" this.fold}}
          >&times;</button>
        </div>
      </form>
    {{else}}
      {{#if @reply.refused}}
        <p class="refusal" data-refused="true" data-test-reply-refused>
          {{@reply.refused.reason}}
          <button
            type="button"
            class="card-edit"
            data-test-edit-again
            {{on "click" this.again}}
          >Edit again</button>
        </p>
      {{/if}}
      <button
        type="button"
        class="reply-open"
        data-test-reply-open
        {{on "click" this.expand}}
        ...attributes
      >{{this.label}}</button>
    {{/if}}
  </template>
}
