import type { TOC } from '@ember/component/template-only';
import { on } from '@ember/modifier';
import modal from 'frontend/modifiers/modal';

interface HoldWarningSignature {
  Args: {
    keep: () => void;
    resume: () => void;
    cancel: () => void;
  };
}

const answering =
  (keep: () => void, resume: () => void) =>
  (key: string): boolean => {
    if (key === 'k') keep();
    else if (key === 'r') resume();
    else return false;
    return true;
  };

const HoldWarning: TOC<HoldWarningSignature> = <template>
  <div class="decide-dialog">
    <form
      class="hold-warning"
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="hold-warning-question"
      aria-describedby="hold-warning-note"
      tabindex="-1"
      data-test-hold-warning
      {{modal @cancel (answering @keep @resume)}}
    >
      <header class="dialog-head">
        <p class="dialog-kicker">This PR is on hold</p>
        <button
          type="button"
          class="dialog-close"
          aria-label="cancel"
          data-test-hold-warning-cancel
          {{on "click" @cancel}}
        >×</button>
      </header>
      <p class="question" id="hold-warning-question">This mention is the only
        reason you can see this PR.</p>
      <p class="note" id="hold-warning-note">The PR is on hold. An open mention
        brings a held PR back into view, and this is its last one: once it
        closes, the PR goes back on hold. Is that right, or is there more work
        to do?</p>
      <div class="dialog-actions">
        <button
          type="button"
          class="primary"
          data-test-hold-warning-keep
          {{on "click" @keep}}
        >Back on hold <kbd>k</kbd></button>
        <button
          type="button"
          data-test-hold-warning-resume
          {{on "click" @resume}}
        >Resume this PR <kbd>r</kbd></button>
      </div>
    </form>
  </div>
</template>;

export default HoldWarning;
