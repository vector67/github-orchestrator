import Component from '@glimmer/component';
import type Owner from '@ember/owner';
import { on } from '@ember/modifier';
import { service } from '@ember/service';
import { tracked } from '@glimmer/tracking';
import {
  WAKE_CONDITIONS,
  type DialogSpec,
  type Gathered,
} from 'frontend/data/decisions';
import type { Ticket } from 'frontend/data/api';
import type { AcceptView } from 'frontend/data/panel';
import { modifier } from 'ember-modifier';
import modal, { focusFirstField } from 'frontend/modifiers/modal';
import type DialogDraftsService from 'frontend/services/dialog-drafts';
import type { Held } from 'frontend/services/dialog-drafts';

const focused = modifier((element: HTMLElement) => {
  element.focus();
});

export interface DecideDialogSignature {
  Element: HTMLDivElement;
  Args: {
    conversationId: string;
    decision: string | null;
    spec: DialogSpec;
    canDelete: boolean;
    agentWords?: string | null;
    accept?: AcceptView | null;
    confirm: (gathered: Gathered) => Promise<boolean>;
    cancel: () => void;
  };
}

export default class DecideDialog extends Component<DecideDialogSignature> {
  @service declare dialogDrafts: DialogDraftsService;

  @tracked typed = this.args.spec.prefill ?? '';
  @tracked wake = 'manual';
  @tracked wakePr = '';
  @tracked deleting = false;
  @tracked resolving = this.args.spec.resolving === true;
  @tracked thumbing = this.args.spec.thumbsUp === true;
  @tracked wording: string | null = null;
  @tracked ticket: Ticket | null = this.args.spec.ticket ?? null;
  @tracked outcome = this.args.spec.outcomes?.[0]?.to ?? '';
  @tracked asking = false;

  constructor(owner: Owner, args: DecideDialogSignature['Args']) {
    super(owner, args);
    const kept = this.dialogDrafts.heldFor(
      args.conversationId,
      args.decision ?? '',
    );
    if (!kept) return;
    this.typed = kept.typed;
    this.wake = kept.wake;
    this.wakePr = kept.wakePr;
    this.deleting = kept.deleting;
    this.resolving = kept.resolving ?? this.resolving;
    this.thumbing = kept.thumbing ?? this.thumbing;
    this.wording = kept.wording ?? null;
    if (kept.ticket) this.ticket = kept.ticket;
  }

  readonly conditions = WAKE_CONDITIONS;

  get wantsPrNumber(): boolean {
    return this.wake === 'pr';
  }

  get unsaid(): boolean {
    if (!this.args.spec.requiresReply) return false;
    const typed = this.typed.trim();
    return !typed || typed === (this.args.spec.prefill ?? '').trim();
  }

  get touched(): boolean {
    return (
      this.typed !== (this.args.spec.prefill ?? '') ||
      this.deleting ||
      this.resolving !== (this.args.spec.resolving === true) ||
      this.thumbing !== (this.args.spec.thumbsUp === true) ||
      this.reworded !== null ||
      this.ticket !== (this.args.spec.ticket ?? null) ||
      this.wake !== 'manual' ||
      this.wakePr !== ''
    );
  }

  get unfinished(): boolean {
    return (this.wantsPrNumber && !this.wakePr.trim()) || this.unsaid;
  }

  get accepting(): AcceptView | null {
    return this.args.spec.accept ? (this.args.accept ?? null) : null;
  }

  get question(): string {
    return this.accepting?.title ?? this.args.spec.question;
  }

  get note(): string {
    return this.accepting?.lead ?? this.args.spec.note;
  }

  get placeholder(): string {
    return this.args.spec.placeholder ?? '';
  }

  get submitLabel(): string {
    return this.args.spec.submit(
      this.typed.trim(),
      this.resolving,
      this.thumbing,
      this.outcome,
    );
  }

  get wordingOpen(): boolean {
    return this.wording !== null;
  }

  get reworded(): string | null {
    const wording = this.wording?.trim() ?? '';
    const message = this.accepting?.message?.trim() ?? '';
    return wording && wording !== message ? wording : null;
  }

  get offersResolve(): boolean {
    return Boolean(this.args.spec.resolves || this.accepting?.resolvable);
  }

  get offersThumbsUp(): boolean {
    return (
      Boolean(this.args.spec.thumbsUp) &&
      !this.typed.trim() &&
      (!this.offersResolve || this.resolving)
    );
  }

  get offersGithubTicks(): boolean {
    return this.offersDelete || this.offersResolve || this.offersThumbsUp;
  }

  get offersDelete(): boolean {
    return Boolean(this.args.spec.del) && this.args.canDelete;
  }

  retitle = (field: keyof Ticket) => (event: Event) => {
    if (!this.ticket) return;
    const value = (event.target as HTMLInputElement | HTMLTextAreaElement)
      .value;
    this.ticket = { ...this.ticket, [field]: value };
  };

  type = (event: Event) => {
    this.typed = (event.target as HTMLTextAreaElement).value;
  };

  chosen = (value: string): boolean => value === this.wake;

  picked = (value: string): boolean => value === this.outcome;

  pickOutcome = (event: Event) => {
    this.outcome = (event.target as HTMLInputElement).value;
  };

  pickWake = (event: Event) => {
    this.wake = (event.target as HTMLSelectElement).value;
  };

  typePr = (event: Event) => {
    this.wakePr = (event.target as HTMLInputElement).value;
  };

  toggleDelete = () => {
    this.deleting = !this.deleting;
  };

  toggleResolve = () => {
    this.resolving = !this.resolving;
  };

  toggleThumbsUp = () => {
    this.thumbing = !this.thumbing;
  };

  useAgentWords = () => {
    this.typed = this.args.agentWords ?? '';
  };

  editMessage = () => {
    this.wording = this.accepting?.message ?? '';
  };

  reword = (event: Event) => {
    this.wording = (event.target as HTMLTextAreaElement).value;
  };

  private form: HTMLElement | null = null;

  holds = modifier((element: HTMLElement) => {
    this.form = element;
  });

  leave = () => {
    if (this.asking) this.stay();
    else if (this.touched) this.asking = true;
    else this.close();
  };

  get held(): Held | null {
    return this.touched
      ? {
          typed: this.typed,
          deleting: this.deleting,
          resolving: this.resolving,
          thumbing: this.thumbing,
          wording: this.wording,
          wake: this.wake,
          wakePr: this.wakePr,
          ...(this.ticket ? { ticket: this.ticket } : {}),
        }
      : null;
  }

  close = () => {
    this.dialogDrafts.keep(
      this.args.conversationId,
      this.args.decision ?? '',
      this.held,
    );
    this.args.cancel();
  };

  stay = () => {
    this.asking = false;
    if (this.form) focusFirstField(this.form);
  };

  confirm = (event: Event) => {
    event.preventDefault();
    if (this.unfinished) return;
    const gathered: Gathered = {};
    const typed = this.typed.trim();
    if (typed && !this.deleting) gathered.body = typed;
    if (this.deleting) gathered.delete = true;
    if (this.offersResolve) gathered.resolve = this.resolving && !this.deleting;
    if (this.offersThumbsUp && !this.thumbing) gathered.thumbsUp = false;
    if (this.accepting && this.reworded) gathered.message = this.reworded;
    if (this.ticket) gathered.ticket = this.ticket;
    if (this.args.spec.outcomes) gathered.modifier = this.outcome;
    if (this.args.spec.wake) {
      gathered.modifier = this.wantsPrNumber
        ? `pr:${this.wakePr.trim()}`
        : this.wake;
    }
    const id = this.args.conversationId;
    const decision = this.args.decision ?? '';
    this.dialogDrafts.keep(id, decision, this.held);
    void this.args.confirm(gathered).then((taken) => {
      if (taken) this.dialogDrafts.keep(id, decision, null);
    });
  };

  <template>
    <div class="decide-dialog" data-test-dialog ...attributes>
      <form
        class={{if this.accepting "accept"}}
        role="dialog"
        aria-modal="true"
        aria-labelledby="decide-dialog-question"
        tabindex="-1"
        {{modal this.leave}}
        {{this.holds}}
        {{on "submit" this.confirm}}
      >
        <header class="dialog-head">
          <p
            class="question"
            id="decide-dialog-question"
            data-test-dialog-question
          >{{this.question}}</p>
          <button
            type="button"
            class="dialog-close"
            aria-label="close"
            data-test-dialog-close
            {{on "click" this.leave}}
          >×</button>
        </header>
        <p class="note">{{this.note}}</p>
        {{#if this.accepting}}
          {{#if this.accepting.message}}
            <div class="commit-head">
              <p class="dialog-kicker">Commit</p>
              {{#unless this.wordingOpen}}
                <button
                  type="button"
                  class="commit-edit"
                  data-test-edit-message
                  {{on "click" this.editMessage}}
                >Edit message</button>
              {{/unless}}
            </div>
            {{#if this.wordingOpen}}
              <textarea
                aria-label="commit message"
                data-test-message-body
                rows="4"
                value={{this.wording}}
                {{on "input" this.reword}}
              ></textarea>
            {{else}}
              <pre
                class="commit-message"
                data-test-commit-message
              >{{this.accepting.message}}</pre>
            {{/if}}
          {{/if}}
          {{#if this.accepting.files}}
            <div class="commit-files">
              {{#each this.accepting.files key="path" as |file|}}
                <p class="commit-file" data-test-commit-file>
                  <span class="commit-path">{{file.path}}</span>
                  <span class="commit-stat">+{{file.added}}
                    &minus;{{file.removed}}</span>
                </p>
              {{/each}}
            </div>
          {{/if}}
        {{/if}}
        {{#if this.ticket}}
          <fieldset class="dialog-ticket" data-test-ticket>
            <legend class="dialog-kicker">Ticket</legend>
            <label class="ticket-field">
              <span class="ticket-label">Project</span>
              <input
                type="text"
                data-test-ticket-project
                value={{this.ticket.project}}
                {{on "input" (this.retitle "project")}}
              />
            </label>
            <label class="ticket-field">
              <span class="ticket-label">Title</span>
              <input
                type="text"
                data-test-ticket-title
                value={{this.ticket.title}}
                {{on "input" (this.retitle "title")}}
              />
            </label>
            <textarea
              aria-label="ticket description"
              data-test-ticket-body
              rows="5"
              value={{this.ticket.body}}
              {{on "input" (this.retitle "body")}}
            ></textarea>
          </fieldset>
        {{/if}}
        {{#if @spec.reply}}
          {{#if this.accepting}}
            <p
              class="dialog-kicker"
              data-test-reply-kicker
            >{{this.accepting.reply_kicker}}</p>
          {{/if}}
          {{#if @agentWords}}
            <button
              type="button"
              class="btn agent-words"
              data-test-agent-words
              {{on "click" this.useAgentWords}}
            >Use the agent’s words</button>
          {{/if}}
          <textarea
            aria-label="your reply"
            data-test-dialog-body
            rows="3"
            placeholder={{this.placeholder}}
            value={{this.typed}}
            {{on "input" this.type}}
          ></textarea>
        {{/if}}
        {{#if this.offersGithubTicks}}
          <fieldset class="dialog-ticks" data-test-github-ticks>
            <legend class="dialog-kicker">On GitHub, also:</legend>
            {{#if this.offersDelete}}
              <label class="dialog-tick">
                <input
                  type="checkbox"
                  class="checkbox"
                  data-test-delete
                  checked={{this.deleting}}
                  {{on "change" this.toggleDelete}}
                />
                Delete the comment
              </label>
            {{/if}}
            {{#if this.offersResolve}}
              <label class="dialog-tick">
                <input
                  type="checkbox"
                  class="checkbox"
                  data-test-resolve
                  checked={{this.resolving}}
                  disabled={{this.deleting}}
                  {{on "change" this.toggleResolve}}
                />
                Resolve the thread
              </label>
            {{/if}}
            {{#if this.offersThumbsUp}}
              <label class="dialog-tick">
                <input
                  type="checkbox"
                  class="checkbox"
                  data-test-thumbs-up
                  checked={{this.thumbing}}
                  {{on "change" this.toggleThumbsUp}}
                />
                Put 👍 on the newest reply
              </label>
            {{/if}}
          </fieldset>
        {{/if}}
        {{#if @spec.outcomes}}
          <fieldset class="dialog-ticks" data-test-outcomes>
            <legend class="dialog-kicker">It is now:</legend>
            {{#each @spec.outcomes key="to" as |one|}}
              <label class="dialog-tick">
                <input
                  type="radio"
                  name="outcome"
                  value={{one.to}}
                  data-test-outcome={{one.to}}
                  checked={{this.picked one.to}}
                  {{on "change" this.pickOutcome}}
                />
                {{one.label}}
              </label>
            {{/each}}
          </fieldset>
        {{/if}}
        {{#if @spec.wake}}
          <label class="dialog-tick">
            wake it
            <select data-test-wake {{on "change" this.pickWake}}>
              {{#each this.conditions key="value" as |condition|}}
                <option
                  value={{condition.value}}
                  selected={{this.chosen condition.value}}
                >{{condition.label}}</option>
              {{/each}}
            </select>
          </label>
          {{#if this.wantsPrNumber}}
            <input
              type="number"
              min="1"
              aria-label="PR number"
              placeholder="PR number"
              data-test-wake-pr
              value={{this.wakePr}}
              {{on "input" this.typePr}}
            />
          {{/if}}
          <p class="note" data-test-wake-by-reply>A reply to this thread will
            wake it automatically.</p>
        {{/if}}
        {{#if this.asking}}
          <div class="dialog-actions">
            <p class="dialog-ask" data-test-close-ask>Are you sure you want to
              close?</p>
            <button
              type="button"
              class="primary"
              data-test-close-confirm
              {{focused}}
              {{on "click" this.close}}
            >Close</button>
            <button
              type="button"
              class="ghost"
              data-test-close-keep
              {{on "click" this.stay}}
            >Keep editing</button>
          </div>
        {{else}}
          <div class="dialog-actions">
            <button
              type="submit"
              class="primary"
              data-test-dialog-submit
              disabled={{this.unfinished}}
            >{{this.submitLabel}}</button>
            <button
              type="button"
              class="ghost"
              data-test-dialog-cancel
              {{on "click" this.leave}}
            >Cancel</button>
          </div>
        {{/if}}
      </form>
    </div>
  </template>
}
