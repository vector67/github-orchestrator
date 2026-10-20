import type { TOC } from '@ember/component/template-only';
import { on } from '@ember/modifier';
import { fn } from '@ember/helper';
import type { DismissUntil } from 'frontend/data/api';
import type { DismissWording } from 'frontend/data/dashboard';
import modal from 'frontend/modifiers/modal';

interface DismissConfirmSignature {
  Args: {
    number: number;
    wording: DismissWording;
    dismiss: (until: DismissUntil) => void;
    cancel: () => void;
  };
}

const answering =
  (dismiss: (until: DismissUntil) => void, wording: DismissWording) =>
  (key: string): boolean => {
    if (key === 'u') dismiss('next-event');
    else if (key === 'r' && wording.untilReady) dismiss('ready-for-review');
    else if (key === 'f') dismiss('forever');
    else return false;
    return true;
  };

const DismissConfirm: TOC<DismissConfirmSignature> = <template>
  <div class="decide-dialog">
    <form
      role="dialog"
      aria-modal="true"
      aria-labelledby="dismiss-confirm-question"
      tabindex="-1"
      data-test-dismiss-confirm
      {{modal @cancel (answering @dismiss @wording)}}
    >
      <header class="dialog-head">
        <p class="question" id="dismiss-confirm-question">Dismiss #{{@number}}?</p>
        <button
          type="button"
          class="dialog-close"
          aria-label="cancel"
          {{on "click" @cancel}}
        >×</button>
      </header>
      <div class="dialog-actions">
        <button
          type="button"
          class="primary"
          data-test-dismiss-option="u"
          {{on "click" (fn @dismiss "next-event")}}
        >{{@wording.untilNextEvent}} <kbd>u</kbd></button>
        {{#if @wording.untilReady}}
          <button
            type="button"
            data-test-dismiss-option="r"
            {{on "click" (fn @dismiss "ready-for-review")}}
          >{{@wording.untilReady}} <kbd>r</kbd></button>
        {{/if}}
        <button
          type="button"
          data-test-dismiss-option="f"
          title={{@wording.foreverDetail}}
          {{on "click" (fn @dismiss "forever")}}
        >{{@wording.forever}} <kbd>f</kbd></button>
      </div>
    </form>
  </div>
</template>;

export default DismissConfirm;
