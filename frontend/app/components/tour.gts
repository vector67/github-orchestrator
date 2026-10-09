import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import type RouterService from '@ember/routing/router-service';
import modal from 'frontend/modifiers/modal';
import type StoreService from 'frontend/services/store';

interface Step {
  key: string;
  title: string;
  says: string[];
}

const STEPS: Step[] = [
  {
    key: 'wall',
    title: 'The wall',
    says: [
      'One row for each open pull request you are part of, in the repos you watch.',
      'Rows are grouped by who has the next move. Needs you is at the top: those are waiting on you. Agent working, Waiting on others and On hold come after.',
    ],
  },
  {
    key: 'move',
    title: 'Your move',
    says: [
      'The first column says what you do next on each pull request, and Why says what makes it your move. The cells after it show CI, conflicts, review, the agent and threads at a glance.',
      'Clicking a row only opens it. Nothing runs until you choose.',
    ],
  },
  {
    key: 'filter',
    title: 'The repo filter',
    says: [
      'The repo button in the top bar picks which repos the wall shows. The wall remembers your choice until you change it.',
    ],
  },
  {
    key: 'pr',
    title: 'A pull request’s page',
    says: [
      'Open a row, or move to it with j and k and press Enter. The page has four tabs, on keys 1 to 4.',
      'Board: the review threads, grouped by what each needs from you, with the agent’s proposed reply or fix. Dashboard: what the PR’s manager is doing and the agent’s runs and output. Terminal: a shell in the pull request’s worktree. Diff: the change itself.',
    ],
  },
  {
    key: 'help',
    title: 'Setup and doctor',
    says: [
      'Setup in the top bar adds and removes repos and changes the options.',
      'When something looks wrong, run github-orchestrator doctor in a terminal. It checks the install, GitHub and each repo, and says how to fix what fails. github-orchestrator tutorial shows this tour again.',
    ],
  },
];

const LAST = STEPS.length - 1;

export default class Tour extends Component {
  @service declare store: StoreService;
  @service declare router: RouterService;

  @tracked at = 0;

  get asked(): boolean {
    return this.router.currentRoute?.queryParams['tour'] === '1';
  }

  get shown(): boolean {
    return (
      this.asked ||
      (this.store.tour?.due === true && this.store.wall.length > 0)
    );
  }

  get step(): Step {
    return STEPS[this.at]!;
  }

  get number(): number {
    return this.at + 1;
  }

  get first(): boolean {
    return this.at === 0;
  }

  get last(): boolean {
    return this.at === LAST;
  }

  back = () => {
    this.at = Math.max(0, this.at - 1);
  };

  next = () => {
    if (this.last) this.close();
    else this.at += 1;
  };

  close = () => {
    this.at = 0;
    if (this.store.tour?.due) this.store.sawTour();
    if (this.asked)
      void this.router.transitionTo({ queryParams: { tour: null } });
  };

  <template>
    {{#if this.shown}}
      <div class="decide-dialog tour">
        <form
          role="dialog"
          aria-modal="true"
          aria-labelledby="tour-title"
          tabindex="-1"
          data-test-tour
          data-test-tour-step={{this.step.key}}
          {{modal this.close}}
        >
          <header class="dialog-head">
            <p class="dialog-kicker">Tour ·
              {{this.number}}
              of
              {{STEPS.length}}</p>
            <button
              type="button"
              class="dialog-close"
              aria-label="skip the tour"
              data-test-tour-skip
              {{on "click" this.close}}
            >×</button>
          </header>
          <p class="question" id="tour-title">{{this.step.title}}</p>
          {{#each this.step.says key="@index" as |said|}}
            <p class="tour-text">{{said}}</p>
          {{/each}}
          <div class="dialog-actions">
            <button
              type="button"
              class="primary"
              data-test-tour-next
              {{on "click" this.next}}
            >{{if this.last "Done" "Next"}}</button>
            <button
              type="button"
              disabled={{this.first}}
              data-test-tour-back
              {{on "click" this.back}}
            >Back</button>
            <button
              type="button"
              class="ghost"
              data-test-tour-skip
              {{on "click" this.close}}
            >Skip the tour</button>
          </div>
        </form>
      </div>
    {{/if}}
  </template>
}
