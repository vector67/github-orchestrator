import Component from '@glimmer/component';
import { fn } from '@ember/helper';
import { on } from '@ember/modifier';
import { service } from '@ember/service';
import { relativeOf } from 'frontend/data/dashboard';
import type HubService from 'frontend/services/hub';
import type { Stepper } from 'frontend/services/store';

export interface CommitBarSignature {
  Args: {
    stepper: Stepper;
    step: (by: number) => void;
    tick: (marked: boolean) => void;
  };
}

export default class CommitBar extends Component<CommitBarSignature> {
  @service declare hub: HubService;

  get age(): string {
    return relativeOf(this.args.stepper.authoredAt, this.hub.now);
  }

  ticked = (event: Event) => {
    this.args.tick((event.target as HTMLInputElement).checked);
  };

  <template>
    <div class="commit-stepper" data-test-commit-stepper>
      <div class="commit-bar" data-test-commit-bar>
        <button
          type="button"
          class="btn"
          title="the previous commit ["
          disabled={{if @stepper.previous false true}}
          data-test-step="previous"
          {{on "click" (fn @step -1)}}
        >‹ Prev <kbd>[</kbd></button>
        <span class="commit-what">
          <b data-test-commit-place>Commit
            {{@stepper.place}}
            of
            {{@stepper.count}}</b>
          <span class="commit-sep">·</span>
          <code class="commit-sha">{{@stepper.short}}</code>
          <span class="commit-subject">{{@stepper.subject}}</span>
          <span class="commit-sep">·</span>
          <span class="commit-by">{{@stepper.author}}</span>
          <span class="commit-sep">·</span>
          <span class="commit-age">{{this.age}}</span>
        </span>
        <label class="commit-read">
          <input
            type="checkbox"
            checked={{@stepper.read}}
            data-test-read
            {{on "change" this.ticked}}
          />
          Read
        </label>
        <button
          type="button"
          class="btn commit-next"
          title="the next commit ]"
          disabled={{if @stepper.next false true}}
          data-test-step="next"
          {{on "click" (fn @step 1)}}
        >Next <kbd>]</kbd> ›</button>
      </div>
      <ol class="commit-pips" aria-label="the pull request's commits">
        {{#each @stepper.pips key="sha" as |pip|}}
          <li class="commit-pip" data-state={{pip.state}} data-test-pip></li>
        {{/each}}
      </ol>
    </div>
  </template>
}
