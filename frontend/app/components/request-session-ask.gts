import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { on } from '@ember/modifier';
import { modifier } from 'ember-modifier';
import modal from 'frontend/modifiers/modal';

interface RequestSessionAskSignature {
  Args: {
    choose: (visible: boolean, remember: boolean) => void;
    cancel: () => void;
  };
}

export default class RequestSessionAsk extends Component<RequestSessionAskSignature> {
  @tracked remember = false;

  shown = modifier((element: HTMLElement) => {
    element.showPopover();
  });

  tick = (event: Event) => {
    this.remember = (event.target as HTMLInputElement).checked;
  };

  visible = () => this.args.choose(true, this.remember);

  invisible = () => this.args.choose(false, this.remember);

  <template>
    <div class="decide-dialog request-ask" popover="manual" {{this.shown}}>
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby="request-ask-question"
        tabindex="-1"
        data-test-request-session
        {{modal @cancel}}
      >
        <header class="dialog-head">
          <p class="question" id="request-ask-question">Run the change in a
            visible session?</p>
          <button
            type="button"
            class="dialog-close"
            aria-label="cancel"
            {{on "click" @cancel}}
          >×</button>
        </header>
        <p class="note">A visible session opens in the terminal, where you can
          watch the agent and type to it. Either way the change comes back to
          the board as a proposal.</p>
        <label class="composer-tick">
          <input
            type="checkbox"
            class="checkbox"
            checked={{this.remember}}
            data-test-request-remember
            {{on "change" this.tick}}
          />
          Remember my choice
        </label>
        <div class="dialog-actions">
          <button
            type="button"
            class="primary"
            data-test-request-visible="yes"
            {{on "click" this.visible}}
          >Visible session</button>
          <button
            type="button"
            data-test-request-visible="no"
            {{on "click" this.invisible}}
          >Without a session</button>
        </div>
      </form>
    </div>
  </template>
}
