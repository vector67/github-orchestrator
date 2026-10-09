import Component from '@glimmer/component';
import { cached, tracked } from '@glimmer/tracking';
import { fn, get } from '@ember/helper';
import { on } from '@ember/modifier';
import { service } from '@ember/service';
import type Owner from '@ember/owner';
import DiffRows from 'frontend/components/diff-rows';
import { copyPath } from 'frontend/data/address';
import type { Diff, FileChange } from 'frontend/data/api';
import { fileOf, type DiffRow, type Expand } from 'frontend/data/diff-rows';
import { inTreeOrder } from 'frontend/data/file-tree';
import Reveals from 'frontend/data/reveals';
import didChange from 'frontend/modifiers/did-change';
import type { Inline } from 'frontend/data/inline';
import {
  endsAt,
  holds,
  landsOn,
  spanOf,
  type Selection,
} from 'frontend/data/selection';
import InlineCard from 'frontend/components/inline-card';
import { LinkTo } from '@ember/routing';
import type StoreService from 'frontend/services/store';
import type ToastsService from 'frontend/services/toasts';

const BIG = 400;

export interface PrDiffSignature {
  Element: HTMLDivElement;
  Args: {
    diff: Diff;
    selection?: Selection | null;
    select?: (selection: Selection, opening: boolean) => void;
    boxOpen?: boolean;
    inline?: Inline[];
    outdated?: Record<string, string[]>;
    editing?: string | null;
    edit?: (item: Inline) => void;
    markers?: boolean;
    only?: string;
  };
  Blocks: { commenting: [Selection | null] };
}

interface Pressed {
  path: string;
  hunk: number;
  origin: number;
  opening: boolean;
}

const PRESSABLE = '.ln, .gutter-add';

function rowUnder(event: Event): HTMLElement | null {
  const target = event.target as Element | null;
  return target?.closest<HTMLElement>('.diff-row[data-hunk]') ?? null;
}

interface Shown {
  change: FileChange;
  rows: DiffRow[];
  folded: boolean;
  held: string | null;
  outdated: string[];
}

function outdatedLabel(keys: string[]): string {
  return `${keys.length} outdated`;
}

function heldBecause(change: FileChange): string | null {
  if (change.status === 'removed')
    return 'Deleted files are not shown by default.';
  if (change.added + change.removed > BIG)
    return 'Large diffs are not rendered by default.';
  return null;
}

export default class PrDiff extends Component<PrDiffSignature> {
  @service declare store: StoreService;
  @service declare toasts: ToastsService;

  @tracked private toggled: Record<string, boolean> = {};
  @tracked private loaded: string[] = [];
  @tracked private dragging: Selection | null = null;
  private pressed: Pressed | null = null;
  private readonly reveals: Reveals;

  constructor(owner: Owner, args: PrDiffSignature['Args']) {
    super(owner, args);
    this.reveals = new Reveals(this.store);
  }

  @cached
  get files(): Shown[] {
    const { head, files } = this.args.diff;
    const only = this.args.only;
    const drawn = only ? files.filter((one) => one.path === only) : files;
    return inTreeOrder(drawn).map((change) => ({
      change,
      rows: fileOf(change, this.reveals.of(head, change.path)).rows,
      folded: this.toggled[change.path] ?? false,
      held: this.loaded.includes(change.path) ? null : heldBecause(change),
      outdated: this.args.outdated?.[change.path] ?? [],
    }));
  }

  reveal = (path: string, expand: Expand) => {
    this.reveals.reveal(this.args.diff.head, path, expand);
  };

  fold = (shown: Shown) => {
    this.toggled = { ...this.toggled, [shown.change.path]: !shown.folded };
  };

  load = (shown: Shown) => {
    this.loaded = [...this.loaded, shown.change.path];
  };

  get selectable(): boolean {
    return this.args.select !== undefined;
  }

  get shownSelection(): Selection | null {
    return this.dragging ?? this.args.selection ?? null;
  }

  selected = (row: DiffRow): boolean => holds(this.shownSelection, row);

  get edited(): Inline | undefined {
    return this.args.inline?.find((item) => item.key === this.args.editing);
  }

  get held(): Selection | null {
    return this.args.selection ?? null;
  }

  private boxLandsOn(row: DiffRow): boolean {
    const selection = this.held;
    if (selection) return endsAt(selection, row);
    const edited = this.edited;
    return edited !== undefined && landsOn(row, edited.lines);
  }

  boxAt = (row: DiffRow): boolean =>
    this.args.boxOpen === true &&
    this.dragging === null &&
    this.boxLandsOn(row);

  at = (row: DiffRow): Inline[] =>
    (this.args.inline ?? []).filter(
      (item) => item.key !== this.args.editing && landsOn(row, item.lines),
    );

  cardsAt = (row: DiffRow): Inline[] => (this.args.markers ? [] : this.at(row));

  markersAt = (row: DiffRow): Inline[] =>
    this.args.markers ? this.at(row) : [];

  opensAt = (row: DiffRow): boolean =>
    this.boxAt(row) || this.cardsAt(row).length > 0;

  private spanTo(row: HTMLElement): Selection | null {
    const pressed = this.pressed;
    const file = this.args.diff.files.find((one) => one.path === pressed?.path);
    if (!pressed || !file) return null;
    if (row.dataset['file'] !== pressed.path) return null;
    if (Number(row.dataset['hunk']) !== pressed.hunk) return null;
    return spanOf(
      file,
      pressed.hunk,
      pressed.origin,
      Number(row.dataset['at']),
    );
  }

  press = (event: MouseEvent) => {
    const row = rowUnder(event);
    const target = event.target as Element | null;
    if (!this.selectable || !row || !target?.closest(PRESSABLE)) return;
    event.preventDefault();
    const path = row.dataset['file'] ?? '';
    const hunk = Number(row.dataset['hunk']);
    const at = Number(row.dataset['at']);
    const held = this.args.selection;
    const opening = target.closest('.gutter-add') !== null;
    const inside =
      held?.path === path &&
      held.hunk === hunk &&
      at >= held.from &&
      at <= held.to;
    if (opening && !event.shiftKey && held && inside) {
      this.args.select?.(held, true);
      return;
    }
    const extends_ =
      event.shiftKey && held?.path === path && held.hunk === hunk;
    const origin = extends_ ? (at >= held.from ? held.from : held.to) : at;
    this.pressed = { path, hunk, origin, opening };
    this.dragging = this.spanTo(row);
    document.addEventListener('mouseup', this.release, { once: true });
  };

  over = (event: MouseEvent) => {
    const row = rowUnder(event);
    if (!this.pressed || !row) return;
    this.dragging = this.spanTo(row) ?? this.dragging;
  };

  listen = (element: HTMLElement) => {
    element.addEventListener('mousedown', this.press);
    element.addEventListener('mouseover', this.over);
    return () => {
      element.removeEventListener('mousedown', this.press);
      element.removeEventListener('mouseover', this.over);
    };
  };

  release = () => {
    const chosen = this.dragging;
    const opening = this.pressed?.opening ?? false;
    this.pressed = null;
    this.dragging = null;
    if (chosen) this.args.select?.(chosen, opening);
  };

  willDestroy(): void {
    super.willDestroy();
    document.removeEventListener('mouseup', this.release);
  }

  titleIfCut = (event: MouseEvent) => {
    const name = event.currentTarget as HTMLElement;
    if (name.scrollWidth > name.clientWidth) name.title = name.textContent;
    else name.removeAttribute('title');
  };

  copy = async (path: string) => {
    this.toasts.say(await copyPath(path), 'done');
  };

  <template>
    <div
      class="pr-diff"
      data-dragging={{if this.dragging "1"}}
      data-test-pr-diff
      {{didChange this.listen}}
      ...attributes
    >
      {{#each this.files key="change.path" as |shown|}}
        <section
          class="diff-file"
          data-path={{shown.change.path}}
          data-collapsed={{if shown.folded "1"}}
          data-test-file={{shown.change.path}}
        >
          <header class="file-head">
            <button
              type="button"
              class="file-fold"
              aria-label="fold the file"
              aria-expanded={{if shown.folded "false" "true"}}
              data-test-fold
              {{on "click" (fn this.fold shown)}}
            >{{if shown.folded "▸" "▾"}}</button>
            <button
              type="button"
              class="file-path"
              data-test-file-path
              {{on "mouseenter" this.titleIfCut}}
              {{on "click" (fn this.fold shown)}}
            >{{shown.change.path}}</button>
            <button
              type="button"
              class="file-copy"
              aria-label="copy the path"
              title="copy the path"
              data-test-copy-path
              {{on "click" (fn this.copy shown.change.path)}}
            >⧉</button>
            <span
              class="file-counts"
              data-test-file-counts
            >+{{shown.change.added}}
              −{{shown.change.removed}}</span>
            <span class="grow"></span>
            {{#if shown.outdated.length}}
              <LinkTo
                @route="conversations.detail"
                @model={{get shown.outdated 0}}
                class="file-outdated"
                data-test-outdated
              >{{outdatedLabel shown.outdated}}</LinkTo>
            {{/if}}
          </header>
          {{#unless shown.folded}}{{#if shown.change.is_binary}}
              <div class="file-held" data-test-held>
                <p>Binary files are not rendered by default.</p>
              </div>
            {{else if shown.held}}
              <div class="file-held" data-test-held>
                <button
                  type="button"
                  class="file-load"
                  data-test-load-diff
                  {{on "click" (fn this.load shown)}}
                >Load diff</button>
                <p>{{shown.held}}</p>
              </div>
            {{else}}
              <DiffRows
                @rows={{shown.rows}}
                @reveal={{fn this.reveal shown.change.path}}
                @selectable={{this.selectable}}
                @selected={{this.selected}}
              >
                <:gutter as |row|>{{#each
                    (this.markersAt row) key="key"
                    as |item|
                  }}<LinkTo
                      @route="conversations.detail"
                      @model={{item.key}}
                      class="gutter-marker"
                      title="a conversation on this line"
                      data-test-marker={{item.key}}
                    >●</LinkTo>{{/each}}</:gutter>
                <:after as |row|>
                  {{#if (this.opensAt row)}}
                    <div class="inline-block" data-test-inline>
                      {{#each (this.cardsAt row) key="key" as |item|}}
                        <InlineCard @item={{item}} @edit={{@edit}} />
                      {{/each}}
                      {{#if (this.boxAt row)}}
                        {{yield this.held to="commenting"}}
                      {{/if}}
                    </div>
                  {{/if}}
                </:after>
              </DiffRows>
            {{/if}}{{/unless}}
        </section>
      {{/each}}
    </div>
  </template>
}
