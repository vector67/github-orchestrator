import Component from '@glimmer/component';
import { waitForPromise } from '@ember/test-waiters';
import { cached, tracked } from '@glimmer/tracking';
import { fn } from '@ember/helper';
import type Owner from '@ember/owner';
import { service } from '@ember/service';
import type { Commits, Diff } from 'frontend/data/api';
import DiffRows from 'frontend/components/diff-rows';
import Waiting from 'frontend/components/waiting';
import {
  DIFF_LOADING,
  filesOf,
  type DiffFile,
  type Expand,
} from 'frontend/data/diff-rows';
import Reveals from 'frontend/data/reveals';
import didChange from 'frontend/modifiers/did-change';
import type ReworkService from 'frontend/services/rework';
import { commitsOf } from 'frontend/services/store';
import type StoreService from 'frontend/services/store';

const POINTABLE = '.diff-row[data-file][data-line]';

export interface DiffSlotSignature {
  Element: HTMLDivElement;
  Args: {
    conversationId: string;
    commits: Commits;
    pointable?: boolean;
  };
}

export default class DiffSlot extends Component<DiffSlotSignature> {
  @service declare rework: ReworkService;

  @service declare store: StoreService;

  @tracked failed: string | null = null;
  @tracked updated: string | null = null;
  private readonly reveals: Reveals;
  private asked: string | null = null;
  private drawnFor: string | null = null;

  constructor(owner: Owner, args: DiffSlotSignature['Args']) {
    super(owner, args);
    this.reveals = new Reveals(this.store);
  }

  get asking(): string {
    return commitsOf(this.args.commits);
  }

  load = () => {
    const asking = this.asking;
    if (this.asked === asking) return;
    const moved =
      this.asked !== null && this.drawnFor === this.args.conversationId;
    this.updated = moved ? asking : null;
    this.asked = asking;
    this.drawnFor = this.args.conversationId;
    void waitForPromise(this.fetchDiff(asking));
  };

  get diff(): Diff | undefined {
    return this.store.diff(this.args.commits);
  }

  @cached
  get files(): DiffFile[] {
    const diff = this.diff;
    if (!diff) return [];
    return filesOf(diff, (path) => this.reveals.of(diff.head, path));
  }

  reveal = (path: string, expand: Expand) => {
    const head = this.diff?.head;
    if (head) this.reveals.reveal(head, path, expand);
  };

  get shown(): boolean {
    return this.diff !== undefined;
  }

  get isFailed(): boolean {
    return !this.shown && this.failed === this.asking;
  }

  get isUpdated(): boolean {
    return this.updated === this.asking;
  }

  get loading(): boolean {
    return !this.shown && !this.isFailed;
  }

  get pointing(): boolean {
    return Boolean(this.args.pointable);
  }

  get marked(): string {
    const ids = this.rework.pointed.map((one) => this.rework.idOf(one));
    const rows = this.files.reduce((sum, file) => sum + file.rows.length, 0);
    return `${this.pointing}|${this.asking}|${rows}|${ids.join(',')}`;
  }

  draw = (slot: HTMLElement) => {
    slot.addEventListener('click', this.point);
    slot.addEventListener('keydown', this.press);
    for (const row of slot.querySelectorAll(POINTABLE)) {
      this.drawRow(row);
    }
    return () => {
      slot.removeEventListener('click', this.point);
      slot.removeEventListener('keydown', this.press);
    };
  };

  private drawRow(row: Element): void {
    const id = this.rework.idOf(this.lineOf(row));
    if (!this.pointing) {
      row.removeAttribute('role');
      row.removeAttribute('tabindex');
      row.removeAttribute('data-pointed');
      return;
    }
    row.setAttribute('role', 'button');
    row.setAttribute('tabindex', '0');
    if (this.rework.isPointed(id)) row.setAttribute('data-pointed', '1');
    else row.removeAttribute('data-pointed');
  }

  private lineOf(row: Element) {
    return {
      file: row.getAttribute('data-file') ?? '',
      line: Number(row.getAttribute('data-line')),
      text: row.querySelector('.code')?.textContent ?? '',
    };
  }

  press = (event: KeyboardEvent) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    this.point(event);
  };

  point = (event: Event) => {
    if (!this.pointing) return;
    const row = (event.target as Element | null)?.closest?.(POINTABLE);
    if (!row) return;
    this.rework.toggle(this.lineOf(row));
  };

  private async fetchDiff(asking: string): Promise<void> {
    if ((await this.store.readDiff(this.args.commits)) === 'failed') {
      this.failed = asking;
    }
  }

  <template>
    <div
      class="diff-slot"
      data-test-diff
      data-updated={{if this.isUpdated "1"}}
      {{didChange this.load this.asking}}
      {{didChange this.draw this.marked}}
    >
      {{#if this.files.length}}
        {{#each this.files key="@index" as |file|}}
          <div class="diff-file">
            <div class="diff-row file" data-test-diff-file>{{file.path}}</div>
            <DiffRows
              @rows={{file.rows}}
              @reveal={{fn this.reveal file.path}}
            />
          </div>
        {{/each}}
      {{else if this.isFailed}}
        <p class="land-error">that diff will not render</p>
      {{else if this.loading}}
        <p
          class="diff-placeholder"
          data-test-loading="diff"
        >{{DIFF_LOADING}}</p>
        <Waiting @on="/diff" />
      {{/if}}
    </div>
  </template>
}
