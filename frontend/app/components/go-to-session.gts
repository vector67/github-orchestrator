import Component from '@glimmer/component';
import { service } from '@ember/service';
import type RouterService from '@ember/routing/router-service';
import { pressedBy } from 'frontend/data/decisions';
import navigates from 'frontend/modifiers/navigates';
import type TerminalService from 'frontend/services/terminal';

export interface GoToSessionSignature {
  Args: {
    conversation: string;
    directory: string | null;
    pressed: string | null;
  };
}

export default class GoToSession extends Component<GoToSessionSignature> {
  @service declare router: RouterService;
  @service declare terminal: TerminalService;

  get href(): string {
    return this.router.urlFor('terminal');
  }

  get checking(): string | null {
    const { pressed } = this.args;
    return pressed === 'check-session'
      ? pressedBy({ kind: pressed, state: 'sent' }).doing
      : null;
  }

  go = async (): Promise<void> => {
    if (this.checking) return;
    const { conversation, directory } = this.args;
    await this.terminal.goTo(conversation, directory, this.arrive);
  };

  private arrive = async (): Promise<void> => {
    await this.router.transitionTo('terminal');
  };

  <template>
    <a
      href={{this.href}}
      class="linkish go-to-session"
      data-pending={{if this.checking "true"}}
      data-test-go-to-session
      {{navigates this.go}}
    >{{if
        this.checking
        this.checking
        "Go to the session in the Terminal tab"
      }}</a>
  </template>
}
