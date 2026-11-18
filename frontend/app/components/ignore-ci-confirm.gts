import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { on } from '@ember/modifier';
import { fn } from '@ember/helper';
import type { IgnoreCiRequest, IgnoreFor } from 'frontend/data/api';
import type { IgnorableCheck } from 'frontend/data/dashboard';
import modal from 'frontend/modifiers/modal';

interface IgnoreCiConfirmSignature {
  Args: {
    number: number;
    checks: IgnorableCheck[];
    ignore: (asked: IgnoreCiRequest) => void;
    stopIgnoring: () => void;
    cancel: () => void;
  };
}

const HOW_LONG: { for: IgnoreFor; label: string }[] = [
  { for: 'this-push', label: 'until the next push' },
  { for: 'this-pr', label: 'always on this PR' },
  { for: 'this-repo', label: 'always in this repo' },
];

const SQUARE: Record<IgnorableCheck['state'], string> = {
  failed: 'sq alarm',
  running: 'sq wait',
  passed: 'sq done',
};

export default class IgnoreCiConfirm extends Component<IgnoreCiConfirmSignature> {
  @tracked every = false;
  @tracked ticked: string[] = this.args.checks
    .filter((one) => one.ticked)
    .map((one) => one.name);
  @tracked ignoreFor: IgnoreFor = 'this-push';

  howLong = HOW_LONG;

  square = (one: IgnorableCheck): string => SQUARE[one.state];

  isTicked = (one: IgnorableCheck): boolean =>
    one.ignored || this.every || this.ticked.includes(one.name);

  get anyIgnored(): boolean {
    return this.args.checks.some((one) => one.ignored);
  }

  picked = (ignoreFor: IgnoreFor): boolean => this.ignoreFor === ignoreFor;

  get nothingTicked(): boolean {
    return !this.every && this.ticked.length === 0;
  }

  tickEvery = (): void => {
    this.every = !this.every;
  };

  tick = (name: string): void => {
    const now = this.every
      ? this.args.checks.map((one) => one.name)
      : this.ticked;
    this.every = false;
    this.ticked = now.includes(name)
      ? now.filter((one) => one !== name)
      : [...now, name];
  };

  pick = (ignoreFor: IgnoreFor): void => {
    this.ignoreFor = ignoreFor;
  };

  ignore = (event: Event): void => {
    event.preventDefault();
    if (this.nothingTicked) return;
    this.args.ignore({
      checks: this.every
        ? []
        : this.args.checks
            .map((one) => one.name)
            .filter((name) => this.ticked.includes(name)),
      every: this.every,
      for: this.ignoreFor,
    });
  };

  <template>
    <div class="decide-dialog">
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby="ignore-ci-question"
        tabindex="-1"
        data-test-ignore-ci-dialog
        {{modal @cancel}}
        {{on "submit" this.ignore}}
      >
        <header class="dialog-head">
          <p class="question" id="ignore-ci-question">Ignore CI on #{{@number}}</p>
          <button
            type="button"
            class="dialog-close"
            aria-label="cancel"
            {{on "click" @cancel}}
          >×</button>
        </header>
        <p class="note">Nothing changes on GitHub. The board stops asking you to
          fix the checks you tick.</p>
        <fieldset class="dialog-ticks">
          <legend class="dialog-kicker">Checks:</legend>
          <label class="dialog-tick" data-test-ignore-check="*">
            <input
              type="checkbox"
              class="checkbox"
              checked={{this.every}}
              {{on "change" this.tickEvery}}
            />
            All checks
          </label>
          {{#each @checks key="name" as |one|}}
            <label class="dialog-tick" data-test-ignore-check={{one.name}}>
              <input
                type="checkbox"
                class="checkbox"
                checked={{this.isTicked one}}
                disabled={{one.ignored}}
                {{on "change" (fn this.tick one.name)}}
              />
              <i class={{this.square one}}></i>
              {{one.name}}
            </label>
          {{/each}}
        </fieldset>
        <fieldset class="dialog-ticks">
          <legend class="dialog-kicker">Ignore them:</legend>
          {{#each this.howLong key="for" as |one|}}
            <label class="dialog-tick" data-test-ignore-for={{one.for}}>
              <input
                type="radio"
                name="ignore-for"
                value={{one.for}}
                checked={{this.picked one.for}}
                {{on "change" (fn this.pick one.for)}}
              />
              {{one.label}}
            </label>
          {{/each}}
        </fieldset>
        <div class="dialog-actions">
          <button
            type="submit"
            class="primary"
            data-test-ignore-ci-submit
            disabled={{this.nothingTicked}}
          >Ignore</button>
          {{#if this.anyIgnored}}
            <button
              type="button"
              data-test-stop-ignoring-ci
              {{on "click" @stopIgnoring}}
            >Stop ignoring</button>
          {{/if}}
          <button
            type="button"
            class="ghost"
            data-test-ignore-ci-cancel
            {{on "click" @cancel}}
          >Cancel</button>
        </div>
      </form>
    </div>
  </template>
}
