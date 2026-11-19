import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import type RouterService from '@ember/routing/router-service';
import AreYouSure from 'frontend/components/are-you-sure';
import PendingRing from 'frontend/components/pending-ring';
import Glyphs from 'frontend/components/glyphs';
import {
  runsAgent,
  type AreYouSure as Asking,
  type Pressing,
} from 'frontend/data/decisions';
import { REBASE_ON_MAIN } from 'frontend/data/git';
import type TerminalService from 'frontend/services/terminal';

interface RebaseButtonSignature {
  Args: {
    asks?: Asking | null;
  };
}

export default class RebaseButton extends Component<RebaseButtonSignature> {
  @service declare terminal: TerminalService;
  @service declare router: RouterService;

  @tracked asking = false;

  get opening(): Pressing | null {
    const session = this.terminal.pressing?.session ?? null;
    return session?.on === REBASE_ON_MAIN.keys ? session : null;
  }

  get pending(): boolean {
    return Boolean(this.opening?.pressed);
  }

  pressed = () => {
    if (this.args.asks) this.asking = true;
    else void this.rebase();
  };

  confirmed = () => {
    this.asking = false;
    void this.rebase();
  };

  cancelled = () => {
    this.asking = false;
  };

  rebase = async () => {
    if (await this.terminal.open(REBASE_ON_MAIN.keys, REBASE_ON_MAIN.display)) {
      void this.router.transitionTo('terminal');
    }
  };

  <template>
    <button
      type="button"
      class="btn {{if @asks 'danger'}}"
      title={{REBASE_ON_MAIN.display}}
      disabled={{this.pending}}
      data-pending={{if this.pending "true"}}
      data-refused={{if this.opening.refused "true"}}
      data-opens-dialog={{if @asks "true"}}
      data-runs-agent={{if (runsAgent "rebase-on-main") "true"}}
      data-test-rebase
      {{on "click" this.pressed}}
    >{{#if this.pending}}{{#if this.opening.ring}}<PendingRing
          />{{/if}}{{this.opening.doing}}{{else}}Rebase on main{{/if}}<Glyphs
        @opensDialog={{if @asks true false}}
        @runsAgent={{runsAgent "rebase-on-main"}}
      /></button>{{#if this.opening.refused}}<span
        class="refusal rebase-refusal"
        data-test-rebase-refusal
      >{{this.opening.refused}}</span>{{/if}}{{#if this.asking}}{{#if
        @asks
      }}<AreYouSure
          @asking={{@asks}}
          @confirm={{this.confirmed}}
          @cancel={{this.cancelled}}
        />{{/if}}{{/if}}
  </template>
}
