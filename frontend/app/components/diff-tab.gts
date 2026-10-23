import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { fn } from '@ember/helper';
import { on } from '@ember/modifier';
import { service } from '@ember/service';
import type Owner from '@ember/owner';
import CommentBox from 'frontend/components/comment-box';
import CommitBar from 'frontend/components/commit-bar';
import CommitTimeline from 'frontend/components/commit-timeline';
import MergeNote from 'frontend/components/merge-note';
import FileTree from 'frontend/components/file-tree';
import PrDiff from 'frontend/components/pr-diff';
import Waiting from 'frontend/components/waiting';
import { DIFF_FAILED, DIFF_LOADING } from 'frontend/data/diff-rows';
import { treeOf, type TreeRow } from 'frontend/data/file-tree';
import type { Inline } from 'frontend/data/inline';
import { linesOf, selectionOf, type Selection } from 'frontend/data/selection';
import { BLANK, NEW_DRAFT, type Saved } from 'frontend/services/drafts';
import type DraftsService from 'frontend/services/drafts';
import type CommitBoxService from 'frontend/services/commit-box';
import type KeysService from 'frontend/services/keys';
import type { Keymap } from 'frontend/services/keys';
import didChange from 'frontend/modifiers/did-change';
import type PullRequestDiffService from 'frontend/services/pull-request-diff';

const eq = (one: unknown, other: unknown): boolean => one === other;

export interface DiffTabSignature {
  Args: {
    file: string | null;
    line: string | null;
    show: (path: string) => void;
  };
}

export default class DiffTab extends Component<DiffTabSignature> {
  @service declare keys: KeysService;
  @service declare drafts: DraftsService;
  @service declare pullRequestDiff: PullRequestDiffService;
  @service declare commitBox: CommitBoxService;

  @tracked selection: Selection | null = null;
  @tracked editing: Inline | null = null;
  @tracked boxOpen = false;
  @tracked filter = '';
  private pane: HTMLElement | null = null;
  private followed: unknown = null;
  private shownLinked: unknown = null;
  private readonly keymap: Keymap = { take: (key) => this.takes(key) };

  constructor(owner: Owner, args: DiffTabSignature['Args']) {
    super(owner, args);
    this.keys.push('tab', this.keymap);
    this.pullRequestDiff.fetchBranch();
  }

  willDestroy(): void {
    super.willDestroy();
    this.keys.drop(this.keymap);
  }

  private takes(key: string): boolean {
    if ((key === '[' || key === ']') && this.pullRequestDiff.stepper) {
      this.pullRequestDiff.step(key === '[' ? -1 : 1);
      return true;
    }
    if (key === 't' && this.pullRequestDiff.timeline) {
      this.pullRequestDiff.toggleTimeline();
      return true;
    }
    if (key !== 'Escape') return false;
    if (!this.selection && !this.boxOpen) return this.pullRequestDiff.unpick();
    this.close();
    return true;
  }

  get hidden(): boolean {
    return this.commitBox.sizing === 'hidden';
  }

  get draftKey(): string {
    return this.editing?.key ?? NEW_DRAFT;
  }

  get saved(): Saved {
    return this.editing?.draft ?? BLANK;
  }

  select = (selection: Selection, opening: boolean) => {
    this.selection = selection;
    if (opening) this.boxOpen = true;
    if (!this.boxOpen) return;
    this.drafts.place(this.draftKey, this.saved, linesOf(selection));
  };

  edit = (item: Inline) => {
    const file = this.pullRequestDiff.shown?.files.find(
      (one) => one.path === item.path,
    );
    this.editing = item;
    this.selection = file ? selectionOf(file, item.lines) : null;
    this.boxOpen = true;
  };

  close = () => {
    this.selection = null;
    this.editing = null;
    this.boxOpen = false;
  };

  countOf = (row: TreeRow): number =>
    this.pullRequestDiff.inline.shown.filter((one) => one.path === row.path)
      .length;

  get tree(): TreeRow[] {
    return treeOf(this.pullRequestDiff.shown?.files ?? [], this.filter);
  }

  get scrolling(): string {
    return `${this.args.file ?? ''}|${this.args.line ?? ''}|${this.pullRequestDiff.shown ? this.pullRequestDiff.drawing || 'drawn' : ''}`;
  }

  get waitingOn(): string {
    return this.pullRequestDiff.stepper
      ? '/api/diffs/'
      : '/api/pull-request/diff';
  }

  filtering = (event: Event) => {
    this.filter = (event.target as HTMLInputElement).value;
  };

  go = (path: string) => {
    this.args.show(path);
    this.scrollTo(path);
  };

  get linked(): string {
    return this.args.line && this.pullRequestDiff.whole
      ? `${this.args.file ?? ''}|${this.args.line}`
      : '';
  }

  showLinked = (_: HTMLElement, linked: unknown) => {
    if (!linked || linked === this.shownLinked) return;
    this.shownLinked = linked;
    this.pullRequestDiff.showWhole();
  };

  follow = (pane: HTMLElement, scrolling: unknown) => {
    this.pane = pane;
    if (scrolling === this.followed) return;
    this.followed = scrolling;
    if (!this.args.file) {
      pane.scrollTop = 0;
      return;
    }
    if (this.args.line) this.scrollToLine(this.args.file, this.args.line);
    else this.scrollTo(this.args.file);
  };

  private scrollTo(path: string): void {
    this.pane
      ?.querySelector(`[data-path="${CSS.escape(path)}"]`)
      ?.scrollIntoView({ block: 'start' });
  }

  private scrollToLine(path: string, line: string): void {
    const row = this.pane?.querySelector(
      `[data-path="${CSS.escape(path)}"] .diff-row:not(.removed)[data-line="${CSS.escape(line)}"]`,
    );
    if (row) row.scrollIntoView({ block: 'center' });
    else this.scrollTo(path);
  }

  <template>
    <div
      class="diff-tab"
      data-test-diff-tab
      {{didChange this.pullRequestDiff.load this.pullRequestDiff.asking}}
      {{didChange
        this.pullRequestDiff.readDetails
        this.pullRequestDiff.anchored
      }}
      {{didChange this.pullRequestDiff.draw this.pullRequestDiff.drawing}}
      {{didChange this.showLinked this.linked}}
    >
      <aside class="diff-tree" data-test-tree>
        <div class="diff-sources" data-test-diff-sources>
          <span
            class="seg"
            role="group"
            aria-label="which head the diff runs to"
          >
            <button
              type="button"
              aria-pressed={{if
                (eq this.pullRequestDiff.source "origin")
                "true"
                "false"
              }}
              title="origin: the PR branch on GitHub, as last fetched"
              data-test-source="origin"
              {{on "click" (fn this.pullRequestDiff.show "origin")}}
            >origin</button>
            <button
              type="button"
              aria-pressed={{if
                (eq this.pullRequestDiff.source "local")
                "true"
                "false"
              }}
              title="local: the commit the PR's worktree has checked out, with any commits not pushed yet"
              data-test-source="local"
              {{on "click" (fn this.pullRequestDiff.show "local")}}
            >local</button>
          </span>
          {{#if this.hidden}}
            {{#if this.pullRequestDiff.timeline}}
              <button
                type="button"
                class="btn"
                title="the branch's timeline t"
                aria-pressed={{if
                  this.pullRequestDiff.timelineOpen
                  "true"
                  "false"
                }}
                data-test-timeline-toggle
                {{on "click" this.pullRequestDiff.toggleTimeline}}
              >Timeline <kbd>t</kbd></button>
            {{/if}}
          {{/if}}
        </div>
        {{#if this.pullRequestDiff.fetching}}
          <span class="fetching-chip" data-test-fetching>fetching…</span>
        {{/if}}
        <input
          type="search"
          class="diff-tree-filter"
          aria-label="filter the changed files"
          placeholder="Filter changed files"
          data-test-tree-filter
          value={{this.filter}}
          {{on "input" this.filtering}}
        />
        <FileTree
          @rows={{this.tree}}
          @current={{@file}}
          @choose={{this.go}}
          @count={{this.countOf}}
        />
      </aside>
      <div class="diff-main">
        {{#if this.pullRequestDiff.stepper}}
          <CommitBar
            @stepper={{this.pullRequestDiff.stepper}}
            @step={{this.pullRequestDiff.step}}
            @go={{this.pullRequestDiff.go}}
            @tick={{this.pullRequestDiff.tick}}
            @note={{this.pullRequestDiff.note}}
            @base={{this.pullRequestDiff.baseName}}
            @dismissNote={{this.pullRequestDiff.dismissNote}}
            @picked={{this.pullRequestDiff.picked}}
            @pickedFiles={{this.pullRequestDiff.pickedFiles}}
            @unpick={{this.pullRequestDiff.unpick}}
            @timelineOpen={{this.pullRequestDiff.timelineOpen}}
            @toggleTimeline={{this.pullRequestDiff.toggleTimeline}}
          />
        {{/if}}
        {{#if this.pullRequestDiff.mergeNote}}
          <MergeNote
            @note={{this.pullRequestDiff.mergeNote}}
            @base={{this.pullRequestDiff.baseName}}
            @skipping={{this.commitBox.skipMerges}}
            @skip={{this.pullRequestDiff.skipMerges}}
          />
        {{/if}}
        {{#if this.pullRequestDiff.timelineOpen}}
          {{#if this.pullRequestDiff.timeline}}
            <CommitTimeline
              @timeline={{this.pullRequestDiff.timeline}}
              @pick={{this.pullRequestDiff.pick}}
              @stretch={{this.pullRequestDiff.stretch}}
              @choose={{this.pullRequestDiff.choose}}
              @fit={{this.pullRequestDiff.fit}}
            />
          {{/if}}
        {{/if}}
        <div
          class="diff-files"
          data-test-diff-files
          {{didChange this.follow this.scrolling}}
        >
          {{#if this.pullRequestDiff.shown}}
            {{#if this.pullRequestDiff.commenting}}
              <PrDiff
                @diff={{this.pullRequestDiff.shown}}
                @selection={{this.selection}}
                @select={{this.select}}
                @boxOpen={{this.boxOpen}}
                @inline={{this.pullRequestDiff.inline.shown}}
                @outdated={{this.pullRequestDiff.inline.outdated}}
                @editing={{this.editing.key}}
                @edit={{this.edit}}
              >
                <:commenting as |selection|>
                  <CommentBox
                    @selection={{selection}}
                    @draft={{this.draftKey}}
                    @saved={{this.saved}}
                    @close={{this.close}}
                  />
                </:commenting>
              </PrDiff>
            {{else}}
              <PrDiff @diff={{this.pullRequestDiff.shown}} />
            {{/if}}
          {{else if this.pullRequestDiff.shownFailed}}
            <p class="land-error" data-test-diff-failed>{{DIFF_FAILED}}</p>
          {{else}}
            <p
              class="diff-placeholder"
              data-test-loading="diff"
            >{{DIFF_LOADING}}</p>
            <Waiting @on={{this.waitingOn}} />
          {{/if}}
        </div>
      </div>
    </div>
  </template>
}
