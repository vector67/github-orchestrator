import type Owner from '@ember/owner';
import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { fn } from '@ember/helper';
import { on } from '@ember/modifier';
import { LinkTo } from '@ember/routing';
import type RouterService from '@ember/routing/router-service';
import { service } from '@ember/service';
import { waitForPromise } from '@ember/test-waiters';
import { modifier } from 'ember-modifier';
import CommentBody from 'frontend/components/comment-body';
import Waiting from 'frontend/components/waiting';
import { collapse } from 'frontend/motion';
import type { Inline } from 'frontend/data/inline';
import { questionAbout } from 'frontend/data/selection';
import { STANDING_LABELS } from 'frontend/data/thread';
import type BoardService from 'frontend/services/board';
import type TerminalService from 'frontend/services/terminal';

export interface InlineCardSignature {
  Args: {
    item: Inline;
    edit?: (item: Inline) => void;
  };
}

export default class InlineCard extends Component<InlineCardSignature> {
  @service declare board: BoardService;
  @service declare terminal: TerminalService;
  @service declare router: RouterService;

  @tracked opened: boolean;
  @tracked private resolutionSeen: boolean;
  @tracked asking = false;
  @tracked question = '';
  @tracked private sending = false;

  constructor(owner: Owner, args: InlineCardSignature['Args']) {
    super(owner, args);
    this.resolutionSeen = args.item.fold !== null;
    this.opened = args.item.fold === null;
  }

  get folded(): boolean {
    return this.args.item.fold !== null && !this.opened;
  }

  get arrived(): boolean {
    return this.args.item.fold !== null && !this.resolutionSeen;
  }

  get editable(): boolean {
    return this.args.edit !== undefined && !this.args.item.locked;
  }

  get retypable(): boolean {
    return this.editable && this.args.item.retype;
  }

  get draftingLocally(): boolean {
    return this.editable && this.args.item.standing === 'local';
  }

  get standing(): string {
    return STANDING_LABELS[this.args.item.standing];
  }

  get where(): string {
    const { line, side, start_line, start_side } = this.args.item.lines;
    const end = `${side[0]}${line}`;
    if (start_line === null) return `Comment on line ${end}`;
    return `Comment on lines ${(start_side ?? side)[0]}${start_line} to ${end}`;
  }

  open = () => {
    this.opened = true;
  };

  fold = () => {
    void waitForPromise(
      collapse(this.body).then(() => {
        this.opened = false;
        this.resolutionSeen = true;
      }),
    );
  };

  <template>
    <article
      class="inline-card"
      data-standing={{@item.standing}}
      data-pending={{if @item.pending "true"}}
      data-refused={{if @item.refused "true"}}
      data-decided={{if (this.board.isDecided @item.key) "true"}}
      data-test-card={{@item.key}}
      {{this.holds}}
    >
      {{#if this.folded}}
        <button
          type="button"
          class="show-resolved"
          aria-expanded="false"
          data-test-show-resolved
          {{on "click" this.open}}
        >
          <span class="folded-where">{{this.where}}</span>
          <span class="card-tag">{{@item.fold.badge}}</span>
        </button>
      {{else}}
        <div class="card-head">
          {{#if @item.fold}}
            <button
              type="button"
              class="hide-resolved"
              aria-expanded="true"
              aria-label="Fold"
              data-test-hide-resolved
              {{on "click" this.fold}}
            ></button>
          {{/if}}
          <span class="card-where">{{this.where}}</span>
          <span
            class="standing"
            data-standing={{@item.standing}}
            data-test-standing
          >{{if @item.pending @item.pending this.standing}}</span>
          {{#if @item.fold}}
            <span
              class="card-tag"
              data-arrived={{if this.arrived "true"}}
              data-test-resolved-chip
            >{{@item.fold.chip}}</span>
          {{/if}}
          <span class="grow"></span>
          {{#if this.editable}}
            <button
              type="button"
              class="card-edit"
              data-test-card-edit
              {{on "click" (fn this.edit @item)}}
            >Edit</button>
            <button
              type="button"
              class="card-edit"
              data-test-card-ask
              {{on "click" this.startAsking}}
            >Ask the agent</button>
          {{/if}}
          {{#if this.draftingLocally}}
            <button
              type="button"
              class="card-edit"
              data-test-card-decide="enrol"
              {{on "click" this.enrol}}
            >Add to review</button>
            <button
              type="button"
              class="card-edit"
              data-test-card-decide="discard"
              {{on "click" this.discard}}
            >Discard</button>
          {{/if}}
          <LinkTo
            @route="conversations.detail"
            @model={{@item.key}}
            class="card-link"
            data-test-card-link
          >On the board</LinkTo>
        </div>
        <div class="card-body" {{this.holdsBody}}>
          {{#if @item.refused}}
            <p class="refusal" data-test-refusal>
              {{@item.refused}}
              {{#if this.retypable}}
                <button
                  type="button"
                  class="card-edit"
                  data-test-edit-again
                  {{on "click" (fn this.edit @item)}}
                >Edit again</button>
              {{/if}}
            </p>
          {{/if}}
          {{#each @item.entries key="@index" as |entry|}}
            <div class="inline-comment">
              <div class="comment-head">
                <span class="who">{{entry.author}}</span>
                <span class="meta">{{entry.meta}}</span>
              </div>
              <CommentBody @body={{entry.body}} />
            </div>
          {{/each}}
          {{#if @item.pending}}
            <Waiting @on="/api/conversations/{{@item.key}}/operations:" />
          {{/if}}
          {{#if this.asking}}
            <form class="comment-box" data-test-ask {{on "submit" this.ask}}>
              <textarea
                aria-label="the question"
                rows="3"
                placeholder="Ask the agent about this comment"
                value={{this.question}}
                {{this.focuses}}
                {{on "input" this.type}}
              ></textarea>
              <div class="box-foot">
                <button
                  type="button"
                  class="box-cancel"
                  data-test-ask-cancel
                  {{on "click" this.stopAsking}}
                >Cancel</button>
                <button
                  type="submit"
                  class="reply-send"
                  data-test-ask-send
                  disabled={{this.unaskable}}
                >Ask</button>
              </div>
            </form>
          {{/if}}
        </div>
      {{/if}}
    </article>
  </template>

  edit = (item: Inline) => {
    this.args.edit?.(item);
  };

  private card!: HTMLElement;
  private body!: HTMLElement;

  holds = modifier((element: HTMLElement) => {
    this.card = element;
  });

  holdsBody = modifier((element: HTMLElement) => {
    this.body = element;
  });

  focuses = modifier((element: HTMLElement) => {
    element.focus();
  });

  enrol = () => {
    void this.board.decide(this.args.item.key, 'enrol');
  };

  discard = () => {
    void this.board.decide(this.args.item.key, 'discard', {}, () =>
      collapse(this.card),
    );
  };

  get unaskable(): boolean {
    return this.sending || this.question.trim() === '';
  }

  startAsking = () => {
    this.asking = true;
  };

  stopAsking = () => {
    this.asking = false;
    this.question = '';
  };

  type = (event: Event) => {
    this.question = (event.target as HTMLTextAreaElement).value;
  };

  ask = async (event: Event) => {
    event.preventDefault();
    const { lines, entries } = this.args.item;
    const draft = entries.map((entry) => entry.body).join('\n\n');
    this.sending = true;
    try {
      if (await this.terminal.ask(questionAbout(lines, this.question, draft))) {
        this.stopAsking();
        void this.router.transitionTo('terminal');
      }
    } finally {
      this.sending = false;
    }
  };
}
