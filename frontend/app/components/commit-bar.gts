import Component from '@glimmer/component';
import { fn } from '@ember/helper';
import { on } from '@ember/modifier';
import { service } from '@ember/service';
import { relativeOf } from 'frontend/data/dashboard';
import type CommitBoxService from 'frontend/services/commit-box';
import type HubService from 'frontend/services/hub';
import type { CommitNote, PickedRange, Stepper } from 'frontend/services/store';
import didChange from 'frontend/modifiers/did-change';

export interface CommitBarSignature {
  Args: {
    stepper: Stepper;
    step: (by: number) => void;
    go: (sha: string) => void;
    tick: (marked: boolean) => void;
    note: CommitNote | null;
    base: string;
    dismissNote: () => void;
    picked: PickedRange | null;
    pickedFiles: number | null;
    unpick: () => void;
    timelineOpen: boolean;
    toggleTimeline: () => void;
    fit: (across: number) => void;
  };
}

export default class CommitBar extends Component<CommitBarSignature> {
  @service declare hub: HubService;
  @service declare commitBox: CommitBoxService;

  get age(): string {
    return relativeOf(this.args.stepper.authoredAt, this.hub.now);
  }

  measure = (pips: HTMLElement) => {
    const watching = new ResizeObserver(() => this.args.fit(pips.clientWidth));
    watching.observe(pips);
    return () => watching.disconnect();
  };

  get full(): boolean {
    return this.commitBox.sizing === 'full';
  }

  get pushed(): string {
    const count = this.args.note?.count ?? 0;
    return `${count} ${count === 1 ? 'commit' : 'commits'}`;
  }

  get fresh(): string {
    const count = this.args.note?.count ?? 0;
    return `${count} ${count === 1 ? 'is' : 'are'} new`;
  }

  get rewritten(): string {
    return this.args.note?.rebased?.matched === 1 ? 'was' : 'were';
  }

  get unchanged(): string {
    const count = this.args.note?.rebased?.unchanged ?? 0;
    return count === 1
      ? '1 is read as it was'
      : `${count} are read as they were`;
  }

  get rangeCommits(): string {
    const count = this.args.picked?.count ?? 0;
    return `${count} ${count === 1 ? 'commit' : 'commits'}`;
  }

  get rangeFiles(): string {
    const count = this.args.pickedFiles;
    if (count === null) return '… files';
    return `${count} ${count === 1 ? 'file' : 'files'}`;
  }

  ticked = (event: Event) => {
    this.args.tick((event.target as HTMLInputElement).checked);
  };

  <template>
    <div
      class="commit-stepper"
      data-sizing={{this.commitBox.sizing}}
      data-test-commit-stepper
    >
      <div class="commit-box" data-test-commit-box>
        {{#if this.full}}
          {{#if @picked}}
            <div class="commit-bar" data-test-commit-bar data-mode="range">
              <span class="commit-pill" data-test-range-pill>range</span>
              <span class="commit-what" data-test-range>
                <code class="commit-sha">{{@picked.fromShort}}</code>
                →
                <code class="commit-sha">{{@picked.toShort}}</code>
                <span class="commit-sep">·</span>
                {{this.rangeCommits}}
                <span class="commit-sep">·</span>
                {{this.rangeFiles}}
              </span>
              <button
                type="button"
                class="btn"
                title="back to the commit you were on Esc"
                data-test-back-to-stepping
                {{on "click" @unpick}}
              >Back<span class="commit-wordy"> to stepping</span></button>
              <button
                type="button"
                class="btn"
                title="the branch's timeline t"
                aria-pressed={{if @timelineOpen "true" "false"}}
                data-test-timeline-toggle
                {{on "click" @toggleTimeline}}
              >Timeline <kbd>t</kbd></button>
            </div>
          {{else}}
            <div class="commit-bar" data-test-commit-bar>
              <button
                type="button"
                class="btn"
                title="the previous commit ["
                disabled={{if @stepper.previous false true}}
                data-test-step="previous"
                {{on "click" (fn @step -1)}}
              >‹<span class="commit-step-word"> Prev</span>
                <kbd>[</kbd></button>
              <span class="commit-what">
                <b data-test-commit-place><span
                    class="commit-wordy"
                  >Commit</span>
                  {{@stepper.place}}
                  of
                  {{@stepper.count}}</b>
                {{#if @stepper.offOrigin}}
                  <span
                    class="commit-pill"
                    data-pill="not-pushed"
                    data-test-not-pushed
                  >{{@stepper.offOrigin}}</span>
                {{/if}}
                {{#if @stepper.merge}}
                  <span class="commit-pill" data-test-merge-pill>merge</span>
                {{/if}}
                <span class="commit-sep">·</span>
                <code class="commit-sha">{{@stepper.short}}</code>
                <span class="commit-subject">{{@stepper.subject}}</span>
                <span class="commit-sep">·</span>
                <span class="commit-by">{{@stepper.author}}</span>
                <span class="commit-sep">·</span>
                <span class="commit-age">{{this.age}}</span>
              </span>
              <label
                class="commit-read"
                data-pending={{if @stepper.marking "true"}}
                data-refused={{if @stepper.markRefused "true"}}
                data-test-read-box
              >
                <input
                  type="checkbox"
                  checked={{@stepper.read}}
                  data-test-read
                  {{on "change" this.ticked}}
                />
                {{if @stepper.marking @stepper.marking "Read"}}
              </label>
              <button
                type="button"
                class="btn"
                title="the branch's timeline t"
                aria-pressed={{if @timelineOpen "true" "false"}}
                data-test-timeline-toggle
                {{on "click" @toggleTimeline}}
              >Timeline <kbd>t</kbd></button>
              <button
                type="button"
                class="btn commit-next"
                title="the next commit ]"
                disabled={{if @stepper.next false true}}
                data-test-step="next"
                {{on "click" (fn @step 1)}}
              ><span class="commit-step-word">Next </span><kbd>]</kbd>
                ›</button>
            </div>
          {{/if}}
        {{/if}}
        <div class="commit-pips-measure" {{didChange this.measure}}></div>
        <ol
          class="commit-pips"
          aria-label="the pull request's commits"
          data-thin={{if @stepper.thin "true"}}
        >
          {{#each @stepper.pips key="sha" as |pip|}}
            <li class="commit-pip-slot"><button
                type="button"
                class="commit-pip"
                title={{pip.label}}
                aria-label={{pip.label}}
                data-state={{pip.state}}
                data-merge={{if pip.merge "true"}}
                data-test-pip
                {{on "click" (fn @go pip.sha)}}
              ></button></li>
          {{/each}}
        </ol>
      </div>
    </div>
    {{#if @stepper.markRefused}}
      <p class="refusal" data-refused="true" data-test-read-refused>
        {{@stepper.markRefused}}
      </p>
    {{/if}}
    {{#if @note}}
      <div class="commit-note-row">
        <p class="commit-note" data-test-commit-note>
          {{#if @note.rebased}}
            <span><b>Rebased since your review</b>
              (force-pushed{{#if @note.rebased.pushedOn}}
                {{@note.rebased.pushedOn}}{{/if}}).
              {{@note.rebased.matched}}
              of your read commits
              {{this.rewritten}}
              rewritten onto newer
              {{@base}}
              and matched by message;
              <b>{{this.fresh}}</b>{{#if @note.rebased.unchanged}};
                {{this.unchanged}}{{/if}}.</span>
          {{else}}
            <span>Picked up at the first new commit:
              <b>{{this.pushed}}</b>
              pushed since your review on
              {{@note.reviewedOn}}.</span>
          {{/if}}
          <button
            type="button"
            class="commit-note-close"
            aria-label="hide this note until the pull request has a new head"
            title="hide this note until the pull request has a new head"
            data-test-commit-note-close
            {{on "click" @dismissNote}}
          >×</button>
        </p>
      </div>
    {{/if}}
  </template>
}
