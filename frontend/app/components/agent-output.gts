import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { on } from '@ember/modifier';
import followsEnd from 'frontend/modifiers/follows-end';
import type { HeardLine } from 'frontend/services/store';

interface Signature {
  Args: { lines: HeardLine[] };
}

export default class AgentOutput extends Component<Signature> {
  @tracked private away = false;
  @tracked private seenUpTo = 0;

  private pane: HTMLElement | null = null;

  get unseen(): string | null {
    if (!this.away) return null;
    const count = this.args.lines.filter(
      (line) => line.n > this.seenUpTo,
    ).length;
    if (!count) return null;
    return `${count} new ${count === 1 ? 'line' : 'lines'} ↓`;
  }

  noted = (atEnd: boolean, pane: HTMLElement): void => {
    this.pane = pane;
    if (atEnd === !this.away) return;
    this.away = !atEnd;
    if (this.away) this.seenUpTo = this.args.lines.at(-1)?.n ?? 0;
  };

  toEnd = (): void => {
    if (this.pane) this.pane.scrollTop = this.pane.scrollHeight;
    this.away = false;
  };

  <template>
    <div class="tx-frame">
      <ol class="tx" data-test-output {{followsEnd @lines this.noted}}>
        {{#each @lines key="n" as |line|}}
          {{#if line.run_boundary}}
            <li class="rule" data-test-run-boundary>── new run</li>
          {{else}}
            <li>{{line.text}}</li>
          {{/if}}
        {{/each}}
      </ol>
      {{#if this.unseen}}
        <button
          type="button"
          class="tx-new"
          data-test-output-new
          {{on "click" this.toEnd}}
        >{{this.unseen}}</button>
      {{/if}}
    </div>
  </template>
}
