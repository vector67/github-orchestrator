import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { service } from '@ember/service';
import type StoreService from 'frontend/services/store';

export const WAITING_MS = 10_000;
const EVERY_MS = 1000;

interface WaitingSignature {
  Args: { on?: string };
}

export default class Waiting extends Component<WaitingSignature> {
  @service declare store: StoreService;

  @tracked private now = Date.now();
  private readonly since = Date.now();
  private readonly timer = setInterval(() => {
    this.now = Date.now();
  }, EVERY_MS);

  willDestroy(): void {
    super.willDestroy();
    clearInterval(this.timer);
  }

  get seconds(): number {
    return Math.floor((this.now - this.since) / 1000);
  }

  get waitingOn(): string {
    if (this.now - this.since < WAITING_MS) return '';
    const on = this.args.on ?? '';
    const paths = this.store.pending().filter((path) => path.includes(on));
    return [...new Set(paths)].join(', ');
  }

  <template>
    {{#if this.waitingOn}}
      <p class="waiting-note" data-test-waiting>
        Still waiting after
        {{this.seconds}}
        s for
        {{this.waitingOn}}
      </p>
    {{/if}}
  </template>
}
