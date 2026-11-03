import Component from '@glimmer/component';
import { service } from '@ember/service';
import type RouterService from '@ember/routing/router-service';
import navigates from 'frontend/modifiers/navigates';
import type TerminalService from 'frontend/services/terminal';

export interface GoToSessionSignature {
  Args: { conversation: string; directory: string | null };
}

export default class GoToSession extends Component<GoToSessionSignature> {
  @service declare router: RouterService;
  @service declare terminal: TerminalService;

  get href(): string {
    return this.router.urlFor('terminal');
  }

  go = async (): Promise<void> => {
    const { conversation, directory } = this.args;
    const { terminal } = this;
    await this.router.transitionTo('terminal');
    await terminal.goTo(conversation, directory);
  };

  <template>
    <a
      href={{this.href}}
      class="linkish go-to-session"
      data-test-go-to-session
      {{navigates this.go}}
    >Go to the session in the Terminal tab</a>
  </template>
}
