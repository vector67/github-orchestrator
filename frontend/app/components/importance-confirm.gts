import type { TOC } from '@ember/component/template-only';
import { on } from '@ember/modifier';
import { fn } from '@ember/helper';
import type { Importance } from 'frontend/data/api';
import modal from 'frontend/modifiers/modal';
import eq from 'frontend/helpers/eq';

interface ImportanceConfirmSignature {
  Args: {
    number: number;
    current: Importance | null;
    pick: (importance: Importance) => void;
    cancel: () => void;
  };
}

const KEYS: Record<string, Importance> = {
  i: 'important',
  n: 'normal',
  s: 'someday',
};

const answering =
  (pick: (importance: Importance) => void) =>
  (key: string): boolean => {
    const importance = KEYS[key];
    if (!importance) return false;
    pick(importance);
    return true;
  };

const ImportanceConfirm: TOC<ImportanceConfirmSignature> = <template>
  <div class="decide-dialog">
    <form
      role="dialog"
      aria-modal="true"
      aria-labelledby="importance-confirm-question"
      tabindex="-1"
      data-test-importance-confirm
      {{modal @cancel (answering @pick)}}
    >
      <header class="dialog-head">
        <p class="question" id="importance-confirm-question">Set importance for
          #{{@number}}</p>
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
          class={{if (eq @current "important") "primary"}}
          aria-current={{if (eq @current "important") "true"}}
          title="Listed first in its section. Once it has waited on others for a day, it moves to Needs you as a nudge"
          data-test-importance-option="important"
          {{on "click" (fn @pick "important")}}
        >Important <kbd>i</kbd></button>
        <button
          type="button"
          class={{if (eq @current "normal") "primary"}}
          aria-current={{if (eq @current "normal") "true"}}
          title="Listed after the important ones"
          data-test-importance-option="normal"
          {{on "click" (fn @pick "normal")}}
        >Normal <kbd>n</kbd></button>
        <button
          type="button"
          class={{if (eq @current "someday") "primary"}}
          aria-current={{if (eq @current "someday") "true"}}
          title="Listed last in its section, greyed"
          data-test-importance-option="someday"
          {{on "click" (fn @pick "someday")}}
        >Someday <kbd>s</kbd></button>
      </div>
    </form>
  </div>
</template>;

export default ImportanceConfirm;
