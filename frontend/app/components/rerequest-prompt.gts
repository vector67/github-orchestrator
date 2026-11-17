import type { TOC } from '@ember/component/template-only';
import { on } from '@ember/modifier';
import modal from 'frontend/modifiers/modal';
import type { RerequestPrompt as Prompt } from 'frontend/services/store';

interface RerequestPromptSignature {
  Args: {
    prompt: Prompt;
    label: string;
    rerequest: () => void;
    only: () => void;
    cancel: () => void;
  };
}

const answering =
  (rerequest: () => void, only: () => void) =>
  (key: string): boolean => {
    if (key === 'r') rerequest();
    else if (key === 'o') only();
    else return false;
    return true;
  };

const RerequestPrompt: TOC<RerequestPromptSignature> = <template>
  <div class="decide-dialog">
    <form
      class="hold-warning rerequest-prompt"
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="rerequest-prompt-question"
      aria-describedby="rerequest-prompt-note"
      tabindex="-1"
      data-test-rerequest-prompt
      {{modal @cancel (answering @rerequest @only)}}
    >
      <header class="dialog-head">
        <p class="dialog-kicker" data-test-rerequest-kicker>Last comment from
          {{@prompt.reviewer}}</p>
        <button
          type="button"
          class="dialog-close"
          aria-label="cancel"
          data-test-rerequest-cancel
          {{on "click" @cancel}}
        >×</button>
      </header>
      <p
        class="question"
        id="rerequest-prompt-question"
        data-test-rerequest-question
      >Re-request {{@prompt.reviewer}}'s review of #{{@prompt.number}}?</p>
      <p class="rerequest-standing"><span
          class="state-chip
            {{if @prompt.badge.alarm 'tone-alarm' 'tone-plain'}}"
          data-test-rerequest-badge
        >{{@prompt.badge.text}}</span></p>
      <p
        class="note"
        id="rerequest-prompt-note"
        data-test-rerequest-summary
      >{{@prompt.summary}}</p>
      {{#if @prompt.flag}}
        <p class="note" data-test-rerequest-flag><strong
          >{{@prompt.flag}}</strong></p>
      {{/if}}
      <div class="dialog-actions">
        <button
          type="button"
          class="primary"
          data-test-rerequest-and
          {{on "click" @rerequest}}
        >{{@label}} and re-request <kbd>r</kbd></button>
        <button
          type="button"
          data-test-rerequest-only
          {{on "click" @only}}
        >{{@label}} only <kbd>o</kbd></button>
      </div>
    </form>
  </div>
</template>;

export default RerequestPrompt;
