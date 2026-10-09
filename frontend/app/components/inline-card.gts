import type Owner from '@ember/owner';
import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { fn } from '@ember/helper';
import { on } from '@ember/modifier';
import { LinkTo } from '@ember/routing';
import { service } from '@ember/service';
import { waitForPromise } from '@ember/test-waiters';
import { modifier } from 'ember-modifier';
import CommentBody from 'frontend/components/comment-body';
import { collapse } from 'frontend/motion';
import type { Inline } from 'frontend/data/inline';
import { STANDING_LABELS } from 'frontend/data/thread';
import type BoardService from 'frontend/services/board';

export interface InlineCardSignature {
  Args: {
    item: Inline;
    edit?: (item: Inline) => void;
  };
}

export default class InlineCard extends Component<InlineCardSignature> {
  @service declare board: BoardService;

  @tracked opened: boolean;
  @tracked private resolutionSeen: boolean;

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
          >{{this.standing}}</span>
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
          {{#each @item.entries key="@index" as |entry|}}
            <div class="inline-comment">
              <div class="comment-head">
                <span class="who">{{entry.author}}</span>
                <span class="meta">{{entry.meta}}</span>
              </div>
              <CommentBody @body={{entry.body}} />
            </div>
          {{/each}}
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

  enrol = () => {
    void this.board.decide(this.args.item.key, 'enrol');
  };

  discard = () => {
    void this.board.decide(this.args.item.key, 'discard', {}, () =>
      collapse(this.card),
    );
  };
}
