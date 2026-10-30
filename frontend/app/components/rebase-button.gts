import Component from '@glimmer/component';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import type RouterService from '@ember/routing/router-service';
import PendingRing from 'frontend/components/pending-ring';
import type { Pressing } from 'frontend/data/decisions';
import { REBASE_ON_MAIN } from 'frontend/data/git';
import type TerminalService from 'frontend/services/terminal';

export default class RebaseButton extends Component {
  @service declare terminal: TerminalService;
  @service declare router: RouterService;

  get opening(): Pressing | null {
    const session = this.terminal.pressing?.session ?? null;
    return session?.on === REBASE_ON_MAIN.keys ? session : null;
  }

  get pending(): boolean {
    return Boolean(this.opening?.pressed);
  }

  rebase = async () => {
    if (await this.terminal.open(REBASE_ON_MAIN.keys, REBASE_ON_MAIN.display)) {
      void this.router.transitionTo('terminal');
    }
  };

  <template>
    <button
      type="button"
      class="btn"
      title={{REBASE_ON_MAIN.display}}
      disabled={{this.pending}}
      data-pending={{if this.pending "true"}}
      data-refused={{if this.opening.refused "true"}}
      data-test-rebase
      {{on "click" this.rebase}}
    >{{#if this.pending}}{{#if this.opening.ring}}<PendingRing
          />{{/if}}{{this.opening.doing}}{{else}}Rebase on main{{/if}}</button>{{#if
      this.opening.refused
    }}<span
        class="refusal rebase-refusal"
        data-test-rebase-refusal
      >{{this.opening.refused}}</span>{{/if}}
  </template>
}
