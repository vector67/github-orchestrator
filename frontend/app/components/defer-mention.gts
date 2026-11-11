import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import { fn } from '@ember/helper';
import modal from 'frontend/modifiers/modal';
import type { DeferMentionRequest, PrMilestone } from 'frontend/data/api';
import {
  MILESTONES,
  parseDeferTime,
  presetsAt,
  whenOf,
  type DeferPreset,
} from 'frontend/data/defer-time';
import type StoreService from 'frontend/services/store';
import type { DeferTarget, MentionRow } from 'frontend/services/store';

type Tab = 'time' | 'pr';

export interface DeferMentionSignature {
  Args: {
    mention: MentionRow;
    close: () => void;
  };
}

const STATES = Object.entries(MILESTONES).map(([state, said]) => ({
  state: state as PrMilestone,
  said,
}));

export default class DeferMention extends Component<DeferMentionSignature> {
  @service declare store: StoreService;

  @tracked tab: Tab = 'time';
  @tracked typed = '';
  @tracked unread = false;
  @tracked refused: string | null = null;
  @tracked picked: string | null = null;

  readonly presets: DeferPreset[] = presetsAt(new Date(Date.now()));
  readonly states = STATES;

  get targets(): DeferTarget[] {
    return this.store.deferTargets;
  }

  get target(): DeferTarget | null {
    const own = `${this.args.mention.repo}#${this.args.mention.number}`;
    const key = this.picked ?? own;
    return (
      this.targets.find((one) => one.key === key) ?? this.targets[0] ?? null
    );
  }

  get lands(): string | null {
    const at = parseDeferTime(this.typed, new Date(Date.now()));
    return at ? whenOf(at) : null;
  }

  isTab = (tab: Tab): boolean => this.tab === tab;

  isTarget = (target: DeferTarget): boolean => this.target?.key === target.key;

  show = (tab: Tab): void => {
    this.tab = tab;
  };

  type = (event: Event): void => {
    this.typed = (event.target as HTMLInputElement).value;
    this.unread = false;
  };

  pick = (event: Event): void => {
    this.picked = (event.target as HTMLSelectElement).value;
  };

  sendTyped = async (event: Event): Promise<void> => {
    event.preventDefault();
    const at = parseDeferTime(this.typed, new Date(Date.now()));
    if (!at) {
      this.unread = true;
      return;
    }
    await this.defer({ until_at: at.toISOString(), until_pr: null });
  };

  sendPreset = async (preset: DeferPreset): Promise<void> => {
    await this.defer({ until_at: preset.at.toISOString(), until_pr: null });
  };

  sendState = async (state: PrMilestone): Promise<void> => {
    const target = this.target;
    if (!target) return;
    await this.defer({
      until_at: null,
      until_pr: { repo: target.repo, number: target.number, state },
    });
  };

  private async defer(
    until: Pick<DeferMentionRequest, 'until_at' | 'until_pr'>,
  ): Promise<void> {
    const { repo, number, comment_id } = this.args.mention;
    this.refused = null;
    const deferred = await this.store.deferMention({
      repo,
      number,
      comment_id,
      ...until,
    });
    if (deferred.done) this.args.close();
    else this.refused = deferred.why;
  }

  <template>
    <div class="decide-dialog defer-mention" data-test-defer-dialog>
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby="defer-mention-question"
        tabindex="-1"
        {{modal @close}}
        {{on "submit" this.sendTyped}}
      >
        <header class="dialog-head">
          <p class="question" id="defer-mention-question">Defer
            {{@mention.author}}’s mention on
            {{@mention.repo}}#{{@mention.number}}</p>
          <button
            type="button"
            class="dialog-close"
            aria-label="close"
            data-test-defer-close
            {{on "click" @close}}
          >×</button>
        </header>
        <p class="note">It stays in the list, greyed, and leaves the count. A
          new comment in its thread brings it back early.</p>
        <div class="defer-tabs" role="tablist">
          <button
            type="button"
            class="tab"
            role="tab"
            aria-selected={{if (this.isTab "time") "true" "false"}}
            data-test-defer-tab="time"
            {{on "click" (fn this.show "time")}}
          >For a time</button>
          <button
            type="button"
            class="tab"
            role="tab"
            aria-selected={{if (this.isTab "pr") "true" "false"}}
            data-test-defer-tab="pr"
            {{on "click" (fn this.show "pr")}}
          >Until a PR…</button>
        </div>
        {{#if (this.isTab "time")}}
          <div class="defer-chips" role="tabpanel">
            {{#each this.presets key="name" as |preset|}}
              <button
                type="button"
                class="chip"
                data-test-defer-preset={{preset.name}}
                {{on "click" (fn this.sendPreset preset)}}
              >{{preset.name}}
                <span class="chip-hint">{{preset.hint}}</span></button>
            {{/each}}
          </div>
          <label class="dialog-tick">
            or until
            <input
              type="text"
              class="defer-typed"
              placeholder="3d, 4h, fri 14:00, tomorrow 9:00"
              data-test-defer-typed
              value={{this.typed}}
              {{on "input" this.type}}
            />
            {{#if this.lands}}
              <span
                class="defer-lands"
                data-test-defer-lands
              >{{this.lands}}</span>
            {{/if}}
          </label>
          {{#if this.unread}}
            <p class="refused" data-test-defer-problem>“{{this.typed}}” is not a
              time to come. Try 3d, 4h, fri 14:00 or tomorrow 9:00.</p>
          {{/if}}
          <div class="dialog-actions">
            <button
              type="submit"
              class="primary"
              data-test-defer-send
            >Defer</button>
            <button
              type="button"
              class="ghost"
              {{on "click" @close}}
            >Cancel</button>
          </div>
        {{else}}
          {{#if this.target}}
            <label class="dialog-tick" role="tabpanel">
              until
              <select data-test-defer-pr {{on "change" this.pick}}>
                {{#each this.targets key="key" as |target|}}
                  <option
                    value={{target.key}}
                    selected={{this.isTarget target}}
                  >{{target.key}} {{target.title}}</option>
                {{/each}}
              </select>
            </label>
            <div class="defer-chips">
              {{#each this.states key="state" as |milestone|}}
                <button
                  type="button"
                  class="chip"
                  data-test-defer-state={{milestone.state}}
                  {{on "click" (fn this.sendState milestone.state)}}
                >{{milestone.said}}</button>
              {{/each}}
            </div>
          {{else}}
            <p class="note" role="tabpanel">No pull request is on the board to
              wait on.</p>
          {{/if}}
        {{/if}}
        {{#if this.refused}}
          <p class="refused" data-test-defer-refused>Not deferred:
            {{this.refused}}</p>
        {{/if}}
      </form>
    </div>
  </template>
}
