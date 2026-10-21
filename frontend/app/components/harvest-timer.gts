import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import type Owner from '@ember/owner';
import type { Numbered } from 'frontend/data/wall';
import modal from 'frontend/modifiers/modal';
import type StoreService from 'frontend/services/store';
import type ToastsService from 'frontend/services/toasts';

interface HarvestTimerSignature {
  Args: { pr: Numbered };
}

const answering =
  (stop: () => void) =>
  (key: string): boolean => {
    if (key !== 'y') return false;
    stop();
    return true;
  };

const submitted = (stop: () => void) => (event: Event) => {
  event.preventDefault();
  stop();
};

export default class HarvestTimer extends Component<HarvestTimerSignature> {
  @service declare store: StoreService;
  @service declare toasts: ToastsService;

  @tracked asking = false;

  constructor(owner: Owner, args: HarvestTimerSignature['Args']) {
    super(owner, args);
    void this.store.readHarvestTimer(args.pr);
  }

  get timer() {
    return this.store.harvestTimer(this.args.pr);
  }

  get running(): boolean {
    return this.timer?.running === true;
  }

  get label(): string {
    return this.running
      ? 'Harvest timer running: stop it'
      : 'Start a Harvest timer';
  }

  press = async () => {
    if (this.running) {
      this.asking = true;
      return;
    }
    this.said(await this.store.startHarvestTimer(this.args.pr));
  };

  stop = async () => {
    this.asking = false;
    this.said(await this.store.stopHarvestTimer(this.args.pr));
  };

  cancel = () => {
    this.asking = false;
  };

  private said(refused: string | null): void {
    if (refused !== null) this.toasts.say(refused, 'failed');
  }

  <template>
    {{#if this.timer.tracked}}
      <button
        type="button"
        class="harvest-pick {{if this.running 'running'}}"
        aria-label={{this.label}}
        title={{this.label}}
        aria-pressed={{if this.running "true" "false"}}
        data-test-harvest-timer
        {{on "click" this.press}}
      ><svg
          class="stopwatch"
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentcolor"
          stroke-width="2"
          aria-hidden="true"
          focusable="false"
        ><circle cx="8" cy="9.25" r="5.25" /><path
            d="M6 1.5h4M8 9.25V6.5"
          /></svg></button>
      {{#if this.asking}}
        <div class="decide-dialog">
          <form
            role="dialog"
            aria-modal="true"
            aria-labelledby="harvest-stop-question"
            tabindex="-1"
            data-test-harvest-stop-confirm
            {{modal this.cancel (answering this.stop)}}
            {{on "submit" (submitted this.stop)}}
          >
            <header class="dialog-head">
              <p class="question" id="harvest-stop-question">Stop the timer?</p>
              <button
                type="button"
                class="dialog-close"
                aria-label="cancel"
                {{on "click" this.cancel}}
              >×</button>
            </header>
            <div class="dialog-actions">
              <button type="submit" class="primary" data-test-harvest-stop>Stop
                it
                <kbd>y</kbd></button>
              <button
                type="button"
                class="ghost"
                data-test-harvest-stop-cancel
                {{on "click" this.cancel}}
              >Cancel <kbd>Esc</kbd></button>
            </div>
          </form>
        </div>
      {{/if}}
    {{/if}}
  </template>
}
