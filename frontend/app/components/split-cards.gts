import Component from '@glimmer/component';
import { fn } from '@ember/helper';
import { on } from '@ember/modifier';
import { service } from '@ember/service';
import { tracked } from '@glimmer/tracking';
import DecideDialog from 'frontend/components/decide-dialog';
import {
  editAsks,
  type DialogSpec,
  type Gathered,
  type PartOffer,
} from 'frontend/data/decisions';
import type { SplitCard, SplitView } from 'frontend/data/panel';
import type BoardService from 'frontend/services/board';
import type ReworkService from 'frontend/services/rework';

interface Editing {
  card: SplitCard;
  spec: DialogSpec;
}

export interface SplitCardsSignature {
  Element: HTMLDivElement;
  Args: { conversationId: string; split: SplitView; pending: boolean };
}

export default class SplitCards extends Component<SplitCardsSignature> {
  @service declare board: BoardService;
  @service declare rework: ReworkService;

  @tracked editing: Editing | null = null;

  get open(): Editing[] {
    return this.editing ? [this.editing] : [];
  }

  act = (card: SplitCard, offer: PartOffer) => {
    if (offer.act === 'accept') {
      void this.board.decide(this.args.conversationId, 'approve', {
        part: card.part,
        resolve: this.args.split.resolving,
      });
    } else if (offer.act === 'edit') {
      this.editing = { card, spec: editAsks(card.part, card) };
    } else {
      this.rework.open(this.args.conversationId, card.part);
    }
  };

  save = (gathered: Gathered): Promise<boolean> => {
    const part = this.editing?.card.part;
    this.editing = null;
    if (!part) return Promise.resolve(false);
    return this.board.decide(this.args.conversationId, 'edit-part', {
      ...gathered,
      part,
    });
  };

  cancel = () => {
    this.editing = null;
  };

  <template>
    <div class="split-cards" data-test-split-cards ...attributes>
      {{#each @split.cards key="part" as |card|}}
        <section
          class="split-card"
          data-state={{card.state}}
          data-test-split-card={{card.part}}
        >
          <p class="part-kicker" data-test-part-kicker>{{card.kicker}}</p>
          {{#if card.result}}
            <p class="part-result" data-test-part-result>
              <span class="part-result-lead">{{card.result.lead}}</span>
              {{#if card.result.url}}
                <a
                  href={{card.result.url}}
                  target="_blank"
                  rel="noopener noreferrer"
                >{{card.result.text}}</a>
              {{else}}
                <span class="part-result-text">{{card.result.text}}</span>
              {{/if}}
            </p>
          {{/if}}
          {{#if card.failure}}
            <p class="part-failure" data-test-part-failure>
              <strong>The last try failed.</strong>
              {{card.failure}}
            </p>
          {{/if}}
          {{#if card.banner}}
            <aside
              class="fix-banner {{card.banner.tone}}"
              data-tone={{card.banner.tone}}
              data-test-part-banner
            >
              <span class="square" data-square={{card.banner.tone}}></span>
              <span class="banner-text">
                <strong>{{card.banner.title}}</strong>
                {{#if card.banner.body}}
                  <span>{{card.banner.body}}</span>
                {{/if}}
              </span>
            </aside>
          {{/if}}
          {{#if card.ticket}}
            <div class="proposed-ticket" data-test-proposed-ticket>
              <p class="ticket-head">
                <span
                  class="ticket-project"
                  data-test-ticket-project-shown
                >{{card.ticket.project}}</span>
                <span
                  class="ticket-title"
                  data-test-ticket-title-shown
                >{{card.ticket.title}}</span>
              </p>
              <p
                class="ticket-body"
                data-test-ticket-body-shown
              >{{card.ticket.body}}</p>
            </div>
          {{/if}}
          {{#each card.files key="path" as |file|}}
            <p class="file-row" data-test-part-file>
              <span class="file-path">{{file.path}}</span>
              <span class="file-added">+{{file.added}}</span>
              <span class="file-removed">−{{file.removed}}</span>
            </p>
          {{/each}}
          {{#if card.new_pr}}
            <p class="part-branch">
              <code data-test-part-branch>{{card.new_pr.branch}}</code>
              into
              <code data-test-part-base>{{card.new_pr.base}}</code>
            </p>
            <p
              class="part-note"
              data-test-part-base-reason
            >{{card.new_pr.base_reason}}</p>
          {{/if}}
          {{#if card.reply}}
            <blockquote
              class="proposed-reply"
              data-test-proposed-reply
            >{{card.reply}}</blockquote>
          {{/if}}
          {{#if card.offers.length}}
            <p class="part-acts">
              {{#each card.offers key="act" as |offer|}}
                <button
                  type="button"
                  class="btn {{if (isPrimary offer) 'fill'}}"
                  title={{offer.title}}
                  disabled={{@pending}}
                  data-test-part-act={{offer.act}}
                  {{on "click" (fn this.act card offer)}}
                >{{offer.label}}</button>
              {{/each}}
            </p>
          {{/if}}
        </section>
      {{/each}}
    </div>
    {{#each this.open key="card.part" as |edit|}}
      <DecideDialog
        @conversationId={{@conversationId}}
        @decision="edit-{{edit.card.part}}"
        @spec={{edit.spec}}
        @canDelete={{false}}
        @confirm={{this.save}}
        @cancel={{this.cancel}}
      />
    {{/each}}
  </template>
}

function isPrimary(offer: PartOffer): boolean {
  return offer.weight === 'primary';
}
