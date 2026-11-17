import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import { fn } from '@ember/helper';
import AreYouSure from 'frontend/components/are-you-sure';
import Glyphs from 'frontend/components/glyphs';
import PendingRing from 'frontend/components/pending-ring';
import modal from 'frontend/modifiers/modal';
import type { WorktreeCleanUp } from 'frontend/data/api';
import {
  deleteWorktreeAsks,
  type AreYouSure as Asking,
  type Pressing,
} from 'frontend/data/decisions';
import { presetsAt, type DeferPreset } from 'frontend/data/defer-time';
import type DashboardService from 'frontend/services/dashboard';
import type PrControlsService from 'frontend/services/pr-controls';
import type StoreService from 'frontend/services/store';
import type { ShownPr } from 'frontend/services/store';

type Asked = 'delete' | 'dismiss' | null;

export default class CleanUpBand extends Component {
  @service declare dashboard: DashboardService;
  @service declare store: StoreService;
  @service('pr-controls') declare controls: PrControlsService;

  @tracked asked: Asked = null;
  @tracked presets: DeferPreset[] = [];

  get shown(): ShownPr | null {
    return this.dashboard.shown;
  }

  get cleanUp(): WorktreeCleanUp | null {
    return this.shown?.flags?.clean_up ?? null;
  }

  get pressing(): Pressing | null {
    const shown = this.shown;
    if (!shown) return null;
    return (
      this.store.summary(shown.repo, shown.number)?.pressing['clean-up'] ?? null
    );
  }

  get files(): string {
    const count = this.cleanUp?.files.length ?? 0;
    return count === 1 ? '1 file' : `${count} files`;
  }

  get deleting(): Asking | null {
    return this.asked === 'delete'
      ? deleteWorktreeAsks(this.cleanUp?.files.length ?? 0)
      : null;
  }

  get dismissing(): boolean {
    return this.asked === 'dismiss';
  }

  askDelete = () => {
    this.asked = 'delete';
  };

  askDismiss = () => {
    this.presets = presetsAt(new Date(Date.now()));
    this.asked = 'dismiss';
  };

  cancel = () => {
    this.asked = null;
  };

  delete = () => {
    const shown = this.shown;
    this.asked = null;
    if (shown) void this.controls.deleteWorktree(shown);
  };

  dismiss = (preset: DeferPreset) => {
    const shown = this.shown;
    this.asked = null;
    if (shown) void this.controls.dismissCleanUp(shown, preset.at);
  };

  <template>
    {{#if this.cleanUp}}
      <section
        class="actionband frozen clean-up"
        data-pending={{if this.pressing.pressed "true"}}
        data-refused={{if this.pressing.refused "true"}}
        data-test-clean-up
      >
        <div class="band-words">
          <div class="big" data-test-clean-up-heading>Your permission is needed
            to clean up this worktree</div>
          <div class="detail">{{#if this.cleanUp.files.length}}<span
                class="mono"
              >{{this.cleanUp.worktree}}</span>
              holds
              {{this.files}}
              no agent wrote. Deleting the worktree deletes them, and every file
              git ignores in it.{{else}}Git could not list what
              <span class="mono">{{this.cleanUp.worktree}}</span>
              holds, so the watcher left it in place.{{/if}}</div>
          <ul class="agent-settings-files">
            {{#each this.cleanUp.files key="@identity" as |path|}}
              <li class="mono" data-test-clean-up-file>{{path}}</li>
            {{/each}}
          </ul>
          {{#if this.pressing.pressed}}
            <div class="computed">{{#if this.pressing.ring}}<PendingRing
                />{{/if}}{{this.pressing.doing}}</div>
          {{/if}}
          {{#if this.pressing.refused}}
            <p class="refusal" data-test-refusal>{{this.pressing.refused}}</p>
          {{/if}}
        </div>
        <div class="controls">
          <button
            type="button"
            class="btn danger"
            disabled={{this.pressing.pressed}}
            data-opens-dialog="true"
            data-test-clean-up-delete
            {{on "click" this.askDelete}}
          >Delete this worktree<Glyphs @opensDialog={{true}} /></button>
          <button
            type="button"
            class="btn"
            disabled={{this.pressing.pressed}}
            data-opens-dialog="true"
            data-test-clean-up-dismiss
            {{on "click" this.askDismiss}}
          >Dismiss for a while<Glyphs @opensDialog={{true}} /></button>
        </div>
      </section>
      {{#if this.deleting}}
        <AreYouSure
          @asking={{this.deleting}}
          @confirm={{this.delete}}
          @cancel={{this.cancel}}
        />
      {{/if}}
      {{#if this.dismissing}}
        <div class="decide-dialog defer-mention" data-test-clean-up-dialog>
          <form
            role="dialog"
            aria-modal="true"
            aria-labelledby="clean-up-dismiss-question"
            tabindex="-1"
            {{modal this.cancel}}
          >
            <header class="dialog-head">
              <p class="question" id="clean-up-dismiss-question">Dismiss the
                clean-up of #{{this.shown.number}}</p>
              <button
                type="button"
                class="dialog-close"
                aria-label="close"
                {{on "click" this.cancel}}
              >×</button>
            </header>
            <p class="note">It leaves the wall and the worktree stays as it is.
              A closed pull request gets no events, so it comes back only at the
              time you pick.</p>
            <div class="defer-chips">
              {{#each this.presets key="name" as |preset|}}
                <button
                  type="button"
                  class="chip"
                  data-test-defer-preset={{preset.name}}
                  {{on "click" (fn this.dismiss preset)}}
                >{{preset.name}}
                  <span class="chip-hint">{{preset.hint}}</span></button>
              {{/each}}
            </div>
          </form>
        </div>
      {{/if}}
    {{/if}}
  </template>
}
