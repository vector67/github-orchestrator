import Component from '@glimmer/component';
import Glyphs from 'frontend/components/glyphs';
import { tracked } from '@glimmer/tracking';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import { runsAgent } from 'frontend/data/decisions';
import type StoreService from 'frontend/services/store';
import type ToastsService from 'frontend/services/toasts';

export interface CheckForFixesSignature {
  Args: { conversation: string };
}

export default class CheckForFixes extends Component<CheckForFixesSignature> {
  @service declare store: StoreService;
  @service declare toasts: ToastsService;

  @tracked asking = false;

  check = async (): Promise<void> => {
    this.asking = true;
    const checked = await this.store.checkForFixes(this.args.conversation);
    this.asking = false;
    if (checked.done) {
      this.toasts.say(
        'Asked an agent whether the changes since your comment address it.',
        'done',
      );
    } else {
      this.toasts.say(`Not checked: ${checked.why}`, 'failed');
    }
  };

  <template>
    <button
      type="button"
      class="decide"
      data-weight="secondary"
      title="Asks an agent whether the changes since your comment address it: Assumed done if they do, My move if not"
      disabled={{this.asking}}
      data-runs-agent={{if (runsAgent "check-for-fixes") "true"}}
      data-test-check-for-fixes
      {{on "click" this.check}}
    >Check for fixes<Glyphs
        @runsAgent={{runsAgent "check-for-fixes"}}
      /></button>
  </template>
}
