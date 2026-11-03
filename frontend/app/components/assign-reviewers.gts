import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { on } from '@ember/modifier';
import type { AssignReviewersRequest, Person } from 'frontend/data/api';
import modal from 'frontend/modifiers/modal';
import ReviewerPicker from 'frontend/components/reviewer-picker';

interface AssignReviewersSignature {
  Args: {
    number: number;
    people: Person[];
    assign: (pick: AssignReviewersRequest) => void;
    cancel: () => void;
  };
}

export default class AssignReviewers extends Component<AssignReviewersSignature> {
  @tracked pick: AssignReviewersRequest = { reviewers: [], detailed: null };

  get nobody(): boolean {
    return this.pick.reviewers.length === 0;
  }

  choose = (pick: AssignReviewersRequest) => {
    this.pick = pick;
  };

  assign = () => {
    if (!this.nobody) this.args.assign(this.pick);
  };

  answering = (key: string): boolean => {
    if (key !== 'y') return false;
    this.assign();
    return true;
  };

  submitted = (event: Event) => {
    event.preventDefault();
    this.assign();
  };

  <template>
    <div class="decide-dialog">
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby="assign-reviewers-question"
        tabindex="-1"
        data-test-assign-reviewers
        {{modal @cancel this.answering}}
        {{on "submit" this.submitted}}
      >
        <header class="dialog-head">
          <p class="question" id="assign-reviewers-question">Assign reviewers to
            #{{@number}}</p>
          <button
            type="button"
            class="dialog-close"
            aria-label="cancel"
            {{on "click" @cancel}}
          >×</button>
        </header>
        <ReviewerPicker
          @people={{@people}}
          @pick={{this.pick}}
          @choose={{this.choose}}
        />
        <div class="dialog-actions">
          <button
            type="submit"
            class="primary"
            disabled={{this.nobody}}
            data-test-assign-option
          >Ask them <kbd>y</kbd></button>
          <button
            type="button"
            class="ghost"
            data-test-assign-cancel
            {{on "click" @cancel}}
          >Cancel <kbd>Esc</kbd></button>
        </div>
      </form>
    </div>
  </template>
}
