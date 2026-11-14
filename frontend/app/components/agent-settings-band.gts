import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import { fn, hash } from '@ember/helper';
import { LinkTo } from '@ember/routing';
import { waitForPromise } from '@ember/test-waiters';
import type RouterService from '@ember/routing/router-service';
import AreYouSure from 'frontend/components/are-you-sure';
import Glyphs from 'frontend/components/glyphs';
import PendingRing from 'frontend/components/pending-ring';
import type { HeldAgentSettings } from 'frontend/data/api';
import {
  agentSettingsAsks,
  type AreYouSure as Asking,
  type Pressing,
} from 'frontend/data/decisions';
import type { Numbered } from 'frontend/data/wall';
import type StoreService from 'frontend/services/store';

interface AgentSettingsBandSignature {
  Args: { pr: Numbered };
}

export default class AgentSettingsBand extends Component<AgentSettingsBandSignature> {
  @service declare store: StoreService;
  @service declare router: RouterService;

  @tracked allowing: boolean | null = null;

  get held(): HeldAgentSettings | null {
    const { repo, number } = this.args.pr;
    return this.store.pr(repo, number)?.flags?.agent_settings ?? null;
  }

  get pressing(): Pressing | null {
    const { repo, number } = this.args.pr;
    return this.store.summary(repo, number)?.pressing['agent-settings'] ?? null;
  }

  get files(): string {
    const count = this.held?.changed.length ?? 0;
    return count === 1 ? '1 file' : `${count} files`;
  }

  get asking(): Asking | null {
    const held = this.held;
    if (this.allowing === null || !held) return null;
    return agentSettingsAsks(this.allowing, held.changed.length);
  }

  labelOf = (allowed: boolean): string =>
    agentSettingsAsks(allowed, this.held?.changed.length ?? 0).label;

  see = () => {
    const first = this.held?.changed[0] ?? null;
    void this.router.transitionTo('pr.diff', {
      queryParams: { file: first, line: null },
    });
  };

  ask = (allowed: boolean) => {
    this.allowing = allowed;
  };

  cancel = () => {
    this.allowing = null;
  };

  confirm = () => {
    const allowed = this.allowing;
    const held = this.held;
    this.allowing = null;
    if (allowed === null || !held) return;
    void waitForPromise(
      this.store.answerAgentSettings(this.args.pr, held.digest, allowed),
    );
  };

  <template>
    {{#if this.held}}
      <section
        class="actionband frozen agent-settings"
        data-pending={{if this.pressing.pressed "true"}}
        data-refused={{if this.pressing.refused "true"}}
        data-test-agent-settings
      >
        <div class="band-words">
          <div class="big" data-test-agent-settings-heading>Agents are stopped
            on this pull request</div>
          <div class="detail">It changes
            {{this.files}}
            that agents load when they work in its checkout. Read the changes
            before any agent runs here.</div>
          <ul class="agent-settings-files">
            {{#each this.held.changed key="@identity" as |path|}}
              <li class="mono" data-test-agent-settings-file><LinkTo
                  class="linkish"
                  @route="pr.diff"
                  @query={{hash file=path line=null}}
                >{{path}}</LinkTo></li>
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
            class="btn fill"
            data-test-agent-settings-see
            {{on "click" this.see}}
          >See the changes</button>
          <button
            type="button"
            class="btn"
            disabled={{this.pressing.pressed}}
            data-opens-dialog="true"
            data-test-agent-settings-allow
            {{on "click" (fn this.ask true)}}
          >{{this.labelOf true}}<Glyphs @opensDialog={{true}} /></button>
          <button
            type="button"
            class="btn"
            disabled={{this.pressing.pressed}}
            data-opens-dialog="true"
            data-test-agent-settings-without
            {{on "click" (fn this.ask false)}}
          >{{this.labelOf false}}<Glyphs @opensDialog={{true}} /></button>
        </div>
      </section>
      {{#if this.asking}}
        <AreYouSure
          @asking={{this.asking}}
          @confirm={{this.confirm}}
          @cancel={{this.cancel}}
        />
      {{/if}}
    {{/if}}
  </template>
}
