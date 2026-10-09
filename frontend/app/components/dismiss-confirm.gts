import type { TOC } from '@ember/component/template-only';
import { on } from '@ember/modifier';
import { fn } from '@ember/helper';
import type { DismissWording } from 'frontend/data/dashboard';
import modal from 'frontend/modifiers/modal';

interface DismissConfirmSignature {
  Args: {
    number: number;
    wording: DismissWording;
    dismiss: (forever: boolean) => void;
    cancel: () => void;
  };
}

const answering =
  (dismiss: (forever: boolean) => void) =>
  (key: string): boolean => {
    if (key !== 'u' && key !== 'f') return false;
    dismiss(key === 'f');
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
      {{modal @cancel (answering @dismiss)}}
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
          {{on "click" (fn @dismiss false)}}
        >{{@wording.untilNextEvent}} <kbd>u</kbd></button>
        <button
          type="button"
          data-test-dismiss-option="f"
          title={{@wording.foreverDetail}}
          {{on "click" (fn @dismiss true)}}
        >{{@wording.forever}} <kbd>f</kbd></button>
      </div>
    </form>
  </div>
</template>;

export default DismissConfirm;
