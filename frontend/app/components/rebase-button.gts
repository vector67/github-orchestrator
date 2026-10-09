import Component from '@glimmer/component';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import type RouterService from '@ember/routing/router-service';
import { REBASE_ON_MAIN } from 'frontend/data/git';
import type TerminalService from 'frontend/services/terminal';

export default class RebaseButton extends Component {
  @service declare terminal: TerminalService;
  @service declare router: RouterService;

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
      data-test-rebase
      {{on "click" this.rebase}}
    >Rebase on main</button>
  </template>
}
