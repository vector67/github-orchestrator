import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import type RouterService from '@ember/routing/router-service';
import FileTree from 'frontend/components/file-tree';
import PrDiff from 'frontend/components/pr-diff';
import type { FileChange } from 'frontend/data/api';
import { DIFF_FAILED, DIFF_LOADING } from 'frontend/data/diff-rows';
import { treeOf, type TreeRow } from 'frontend/data/file-tree';
import { draftLocked } from 'frontend/data/panel';
import {
  LINES_GONE,
  anchoredAt,
  linesOf,
  selectionOf,
  type Lines,
  type Selection,
} from 'frontend/data/selection';
import didChange from 'frontend/modifiers/did-change';
import {
  BLANK,
  NEW_DRAFT,
  linesIn,
  type Copy,
  type Saved,
} from 'frontend/services/drafts';
import type DraftsService from 'frontend/services/drafts';
import type PullRequestDiffService from 'frontend/services/pull-request-diff';
import type ReviewService from 'frontend/services/review';

export interface DraftComposerSignature {
  Args: {
    key: string | null;
    draft:
      | (Saved & { editable: boolean; enrolled: boolean; posting: boolean })
      | null;
  };
  Blocks: { default: [] };
}

interface Browsing {
  key: string;
  path: string | null;
}

const ENROLLED_NOTE =
  'In your review. Changes go out when you send the review.';

const GOING_NOTE =
  'On its way to GitHub; it cannot change until the board has it.';

const SAVING_NOTE = 'The board is saving this; nothing is posted to GitHub.';

const PICK_A_LINE =
  'Pick a line in the diff on the right to place this comment.';

const DRAFT_NOTE =
  'Nothing reaches GitHub until you post it or send the review it is in.';

export default class DraftComposer extends Component<DraftComposerSignature> {
  @service declare drafts: DraftsService;
  @service declare router: RouterService;
  @service declare review: ReviewService;
  @service declare pullRequestDiff: PullRequestDiffService;

  @tracked private browsing: Browsing | null = null;

  get key(): string {
    return this.args.key ?? NEW_DRAFT;
  }

  get saved(): Saved {
    return this.args.draft ?? BLANK;
  }

  get creating(): boolean {
    return this.args.key === null;
  }

  get copy(): Copy {
    return this.drafts.copyOf(this.key, this.saved);
  }

  get locked(): boolean {
    const draft = this.args.draft;
    if (this.creating) return false;
    return !draft || draftLocked(draft, this.review.inFlight);
  }

  get unsaveable(): boolean {
    return !this.drafts.saveable(this.key, this.saved);
  }

  get saveLabel(): string {
    return this.creating ? 'Create draft' : 'Save draft';
  }

  get going(): boolean {
    const draft = this.args.draft;
    if (!draft) return false;
    return draft.posting || (draft.enrolled && this.review.inFlight);
  }

  get note(): string {
    if (this.going) return GOING_NOTE;
    if (this.locked) return SAVING_NOTE;
    if (!this.lines) return PICK_A_LINE;
    return this.args.draft?.enrolled ? ENROLLED_NOTE : DRAFT_NOTE;
  }

  get lines(): Lines | null {
    return linesIn(this.copy);
  }

  get file(): string | undefined {
    const browsing = this.browsing;
    if (browsing?.key === this.key) return browsing.path ?? undefined;
    return this.lines?.path;
  }

  get files(): FileChange[] {
    return this.pullRequestDiff.diff?.files ?? [];
  }

  get placedIn(): string | null {
    return this.lines?.path ?? null;
  }

  get tree(): TreeRow[] {
    return treeOf(this.files, '');
  }

  get change(): FileChange | undefined {
    return this.files.find((one) => one.path === this.file);
  }

  get selection(): Selection | null {
    const lines = this.lines;
    const own = this.files.find((one) => one.path === lines?.path);
    return lines && own ? selectionOf(own, lines) : null;
  }

  get drawing(): string {
    return `${this.key}|${this.change?.path ?? ''}`;
  }

  scroll = (pane: HTMLElement) => {
    let top = 0;
    let at = pane.querySelector<HTMLElement>('[data-selected]');
    if (!at) return;
    while (at && at !== pane) {
      top += at.offsetTop;
      at = at.offsetParent as HTMLElement | null;
    }
    pane.scrollTop = top - pane.clientHeight / 3;
  };

  get gone(): boolean {
    if (!this.lines || !this.pullRequestDiff.diff) return false;
    return this.selection === null;
  }

  pick = () => {
    this.browsing = { key: this.key, path: null };
  };

  choose = (path: string) => {
    this.browsing = { key: this.key, path };
  };

  get anchor(): string {
    return this.selection ? anchoredAt(this.selection) : '';
  }

  get select(): ((selection: Selection) => void) | undefined {
    return this.locked ? undefined : this.place;
  }

  place = (selection: Selection) => {
    this.drafts.place(this.key, this.saved, linesOf(selection));
    this.browsing = null;
  };

  type = (event: Event) => {
    const value = (event.target as HTMLTextAreaElement).value;
    this.drafts.change(this.key, this.saved, 'body', value);
  };

  save = async (event: Event) => {
    event.preventDefault();
    const made = await this.drafts.save(this.key, this.saved);
    if (made && this.creating) {
      await this.router.transitionTo('conversations.detail', made);
    }
  };

  <template>
    <div id="panel-talk">
      {{yield}}
      <form class="draft-composer" data-test-composer {{on "submit" this.save}}>
        <textarea
          aria-label="the comment"
          data-test-draft-body
          rows="6"
          placeholder="What should the author change, and why…"
          value={{this.copy.body}}
          disabled={{this.locked}}
          {{on "input" this.type}}
        ></textarea>
        {{#if this.anchor}}
          <p class="draft-anchor" data-test-draft-anchor>{{this.anchor}}</p>
        {{/if}}
        <div class="draft-foot">
          {{#unless this.locked}}
            <button
              type="submit"
              class="reply-send"
              data-test-draft-save
              disabled={{this.unsaveable}}
            >{{this.saveLabel}}</button>
          {{/unless}}
          <p class="composer-note" data-test-draft-note>{{this.note}}</p>
        </div>
      </form>
    </div>
    <div
      id="panel-anchor"
      {{didChange this.pullRequestDiff.load this.pullRequestDiff.asking}}
      {{didChange
        this.pullRequestDiff.readDetails
        this.pullRequestDiff.anchored
      }}
    >
      {{#if this.pullRequestDiff.diff}}
        {{#if this.gone}}
          <p class="anchor-gone" data-test-draft-gone>{{LINES_GONE}}</p>
        {{/if}}
        {{#if this.change}}
          {{#unless this.locked}}
            <button
              type="button"
              class="anchor-file"
              title="choose another changed file"
              data-test-anchor-file
              {{on "click" this.pick}}
            >{{this.change.path}}</button>
          {{/unless}}
          <div
            class="anchor-diff"
            data-test-anchor-diff
            {{didChange this.scroll this.drawing}}
          >
            <PrDiff
              @diff={{this.pullRequestDiff.diff}}
              @only={{this.change.path}}
              @markers={{true}}
              @inline={{this.pullRequestDiff.inline.shown}}
              @editing={{this.key}}
              @selection={{this.selection}}
              @select={{this.select}}
            />
          </div>
        {{else}}
          <FileTree
            @rows={{this.tree}}
            @current={{this.placedIn}}
            @choose={{this.choose}}
          />
        {{/if}}
      {{else if this.pullRequestDiff.failed}}
        <p class="land-error" data-test-diff-failed>{{DIFF_FAILED}}</p>
      {{else}}
        <p
          class="diff-placeholder"
          data-test-loading="diff"
        >{{DIFF_LOADING}}</p>
      {{/if}}
    </div>
  </template>
}
