import Component from '@glimmer/component';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import type RouterService from '@ember/routing/router-service';
import type TerminalService from 'frontend/services/terminal';

export interface GoToSessionSignature {
  Args: { conversation: string; directory: string | null };
}

export default class GoToSession extends Component<GoToSessionSignature> {
  @service declare router: RouterService;
  @service declare terminal: TerminalService;

  go = async (): Promise<void> => {
    const { conversation, directory } = this.args;
    const { terminal } = this;
    await this.router.transitionTo('terminal');
    await terminal.goTo(conversation, directory);
  };

  <template>
    <button
      type="button"
      class="linkish go-to-session"
      data-test-go-to-session
      {{on "click" this.go}}
    >Go to the session in the Terminal tab</button>
  </template>
}
