import Component from '@glimmer/component';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import { fn } from '@ember/helper';
import { tracked } from '@glimmer/tracking';
import DecideDialog from 'frontend/components/decide-dialog';
import ReworkDialog from 'frontend/components/rework-dialog';
import {
  keyOf,
  LATER,
  laterAsks,
  type DialogSpec,
  type Decision,
  type Gathered,
  type Offer,
} from 'frontend/data/decisions';
import type {
  AcceptView,
  Affordance,
  DraftView,
  Fold,
  ReworkView,
} from 'frontend/data/panel';
import didInsert from 'frontend/modifiers/did-insert';
import type BoardService from 'frontend/services/board';
import type ComposerService from 'frontend/services/composer';
import type DraftsService from 'frontend/services/drafts';
import type KeysService from 'frontend/services/keys';
import type { Keymap } from 'frontend/services/keys';
import type ReworkService from 'frontend/services/rework';

export interface PanelActionsSignature {
  Element: HTMLElement;
  Args: {
    conversationId: string;
    actions: Offer[];
    replyAction?: Affordance | null;
    replies?: boolean;
    canDelete: boolean;
    agentWords?: string | null;
    accept?: AcceptView | null;
    rework?: ReworkView | null;
    fold?: Fold | null;
    draft?: DraftView | null;
  };
}

const SAVE_FIRST =
  'save your edits first: this sends the draft as it was saved';

const COMPOSER = 'reply-box';

const REPLY_KEY = keyOf('reply');

export default class PanelActions extends Component<PanelActionsSignature> {
  @service declare board: BoardService;
  @service declare composer: ComposerService;
  @service declare drafts: DraftsService;
  @service declare keys: KeysService;
  @service declare rework: ReworkService;

  @tracked asking: Decision | null = null;
  @tracked spec: DialogSpec | null = null;

  held = (offered: Offer): boolean => {
    const draft = this.args.draft;
    if (!draft || !offered.savedFirst) return false;
    return this.drafts.unsaved(this.args.conversationId, draft);
  };

  get acting(): boolean {
    return this.board.isActing(this.args.conversationId);
  }

  unavailable = (offered: Offer): boolean => this.acting || this.held(offered);

  titleOf = (offered: Offer): string =>
    this.held(offered) ? SAVE_FIRST : offered.title;

  labelOf = (offered: Offer): string =>
    this.board.doing(this.args.conversationId) === offered.decision
      ? offered.doing
      : offered.label;

  private post(decision: Decision, gathered: Gathered = {}): Promise<boolean> {
    return this.board.decide(this.args.conversationId, decision, gathered);
  }

  get composing(): boolean {
    return this.rework.isOpen(this.args.conversationId);
  }

  cancelRework = () => {
    this.rework.cancel();
  };

  sendRework = () => {
    const brief = this.rework.brief;
    const visible = this.rework.visible;
    this.rework.cancel();
    void this.post(visible ? 'start-session' : 'rework', { brief });
  };

  decide = (offered: Offer) => {
    if (offered.asks === 'rework') {
      this.rework.open(this.args.conversationId);
    } else if (offered.asks === 'composer') {
      this.compose();
    } else if (offered.asks === null) {
      void this.post(offered.decision);
    } else {
      this.asking = offered.decision;
      this.spec = offered.asks;
    }
  };

  private readonly keymap: Keymap = { take: (key) => this.takes(key) };

  offer = () => {
    this.keys.push('board', this.keymap);
  };

  willDestroy(): void {
    super.willDestroy();
    this.keys.drop(this.keymap);
  }

  private takes(key: string): boolean {
    const found = (this.args.actions ?? []).find((one) => one.key === key);
    if (!found && key === REPLY_KEY && this.args.replies) {
      this.compose();
      return true;
    }
    if (!found || this.unavailable(found)) return false;
    this.decide(found);
    return true;
  }

  compose = () => {
    this.composer.open(this.args.conversationId);
    document.getElementById(COMPOSER)?.focus();
  };

  cancel = () => {
    this.asking = null;
    this.spec = null;
  };

  get open(): { decision: Decision; spec: DialogSpec }[] {
    return this.asking && this.spec
      ? [{ decision: this.asking, spec: this.spec }]
      : [];
  }

  confirm = (gathered: Gathered): Promise<boolean> => {
    const decision = this.asking;
    if (decision === 'place' && gathered.modifier === LATER) {
      this.asking = 'defer';
      this.spec = laterAsks();
      return Promise.resolve(true);
    }
    this.cancel();
    return decision
      ? this.post(decision, { ...gathered })
      : Promise.resolve(false);
  };

  <template>
    <footer
      class="actions"
      id="panel-actions"
      aria-busy={{if this.acting "true"}}
      {{didInsert this.offer}}
      ...attributes
    >
      {{#if @replyAction}}
        <button
          type="button"
          class="compose"
          data-weight={{@replyAction.weight}}
          data-test-reply-to
          {{on "click" this.compose}}
        >{{@replyAction.label}}
          {{#if @replies}}<kbd>{{REPLY_KEY}}</kbd>{{/if}}</button>
      {{/if}}
      {{#each @actions key="decision" as |offered|}}
        <button
          type="button"
          class="decide {{offered.decision}}"
          data-weight={{offered.weight}}
          title={{this.titleOf offered}}
          disabled={{this.unavailable offered}}
          data-test-decision={{offered.decision}}
          {{on "click" (fn this.decide offered)}}
        >{{this.labelOf offered}}
          <kbd>{{offered.cap}}</kbd></button>
      {{/each}}
    </footer>
    {{#if this.composing}}
      {{#if @rework}}
        <ReworkDialog
          @conversationId={{@conversationId}}
          @rework={{@rework}}
          @fold={{@fold}}
          @send={{this.sendRework}}
          @cancel={{this.cancelRework}}
        />
      {{/if}}
    {{/if}}
    {{#each this.open key="decision" as |dialog|}}
      <DecideDialog
        @conversationId={{@conversationId}}
        @decision={{dialog.decision}}
        @spec={{dialog.spec}}
        @canDelete={{@canDelete}}
        @agentWords={{@agentWords}}
        @accept={{@accept}}
        @confirm={{this.confirm}}
        @cancel={{this.cancel}}
      />
    {{/each}}
  </template>
}
