import Component from '@glimmer/component';
import { on } from '@ember/modifier';
import type { AreYouSure as Asking } from 'frontend/data/decisions';
import modal from 'frontend/modifiers/modal';

const MODIFIERS = new Set(['Shift', 'Control', 'Alt', 'Meta', 'CapsLock']);

interface AreYouSureSignature {
  Args: {
    asking: Asking;
    confirm: () => void;
    cancel: () => void;
  };
}

export default class AreYouSure extends Component<AreYouSureSignature> {
  submitted = (event: Event) => {
    event.preventDefault();
    this.args.confirm();
  };

  answer = (key: string): boolean => {
    if (MODIFIERS.has(key)) return true;
    if (key === 'y') this.args.confirm();
    else this.args.cancel();
    return true;
  };

  <template>
    <div class="decide-dialog">
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby="are-you-sure-question"
        tabindex="-1"
        data-test-are-you-sure
        {{modal @cancel this.answer}}
        {{on "submit" this.submitted}}
      >
        <header class="dialog-head">
          <p
            class="question"
            id="are-you-sure-question"
            data-test-are-you-sure-question
          >{{@asking.question}}</p>
          <button
            type="button"
            class="dialog-close"
            aria-label="cancel"
            {{on "click" @cancel}}
          >×</button>
        </header>
        <p
          class="note"
          data-test-are-you-sure-consequence
        >{{@asking.consequence}}</p>
        <div class="dialog-actions">
          <button
            type="submit"
            class="primary danger"
            data-test-are-you-sure-submit
          >{{@asking.label}} <kbd>y</kbd></button>
          <button
            type="button"
            class="ghost"
            data-test-are-you-sure-cancel
            {{on "click" @cancel}}
          >Cancel <kbd>Esc</kbd></button>
        </div>
      </form>
    </div>
  </template>
}
