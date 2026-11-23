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
    const choice = wording.choices.find((one) => one.key === key);
    if (!choice) return false;
    dismiss(choice.until);
    return true;
  };

const isForever = (until: DismissUntil): boolean => until === 'forever';

const DismissConfirm: TOC<DismissConfirmSignature> = <template>
  <div class="decide-dialog dismiss-confirm">
    <form
      role="dialog"
      aria-modal="true"
      aria-labelledby="dismiss-confirm-question"
      tabindex="-1"
      data-test-dismiss-confirm
      {{modal @cancel (answering @dismiss @wording)}}
    >
      <header class="dialog-head">
        <p class="question" id="dismiss-confirm-question">Dismiss #{{@number}}</p>
        <button
          type="button"
          class="dialog-close"
          aria-label="cancel"
          {{on "click" @cancel}}
        >×</button>
      </header>
      <p class="note">Its manager stops and the PR leaves the board. For how
        long?</p>
      <div class="dismiss-choices">
        {{#each @wording.choices key="until" as |choice|}}
          <button
            type="button"
            class="chip {{if (isForever choice.until) 'forever'}}"
            data-test-dismiss-option={{choice.key}}
            {{on "click" (fn @dismiss choice.until)}}
          ><span class="chip-label">{{choice.label}}</span>
            <span class="chip-hint">{{choice.hint}}</span>
            <kbd>{{choice.key}}</kbd></button>
        {{/each}}
      </div>
      <p class="note" data-test-dismiss-undo>Undo forever with
        <code>{{@wording.undismissCommand}}</code></p>
    </form>
  </div>
</template>;

export default DismissConfirm;
