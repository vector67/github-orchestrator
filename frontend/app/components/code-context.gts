import Component from '@glimmer/component';
import { waitForPromise } from '@ember/test-waiters';
import { cached, tracked } from '@glimmer/tracking';
import { service } from '@ember/service';
import { LinkTo } from '@ember/routing';
import Waiting from 'frontend/components/waiting';
import {
  highlightedLines,
  languageOf,
  type Highlighter,
} from 'frontend/data/highlight';
import type { Code } from 'frontend/data/panel';
import didChange from 'frontend/modifiers/did-change';
import drawn from 'frontend/modifiers/drawn';
import type StoreService from 'frontend/services/store';

export interface CodeContextSignature {
  Element: HTMLElement;
  Args: { code: Code };
}

export default class CodeContext extends Component<CodeContextSignature> {
  @service declare store: StoreService;

  @tracked failed: string | null = null;
  private asked: string | null = null;

  get asking(): string {
    const { sha, path, from_line, to_line } = this.args.code;
    const query = new URLSearchParams({
      sha,
      path,
      from_line: String(from_line),
      to_line: String(to_line),
    }).toString();
    return query;
  }

  get diffAt(): { file: string; line: string } {
    return { file: this.args.code.path, line: String(this.args.code.first) };
  }

  @cached
  get lines(): {
    number: number;
    text: string;
    marked: boolean;
    draw: Highlighter;
  }[] {
    const read = this.store.fileLines(this.asking);
    const { first, last, path } = this.args.code;
    const lines = read?.lines ?? [];
    const drawn = highlightedLines(
      lines.map((one) => one.text),
      languageOf(path),
    );
    return lines.map((one, at) => ({
      ...one,
      marked: one.number >= first && one.number <= last,
      draw: drawn[at]!,
    }));
  }

  get loading(): boolean {
    return (
      this.store.fileLines(this.asking) === undefined &&
      this.failed !== this.asking
    );
  }

  load = () => {
    const asking = this.asking;
    if (this.asked === asking) return;
    this.asked = asking;
    void waitForPromise(this.fetchLines(asking));
  };

  private async fetchLines(asking: string): Promise<void> {
    if ((await this.store.readLines(asking)) === 'failed') {
      this.failed = asking;
    }
  }

  <template>
    <section
      id="panel-code"
      data-test-context
      {{didChange this.load this.asking}}
      ...attributes
    >
      {{#if this.lines.length}}
        <div class="diff-frame">
          <div class="diff-frame-head">
            <span class="diff-frame-title">{{@code.path}}</span>
            {{#if @code.outdated}}
              <span
                class="code-outdated"
                data-test-code-outdated
              >{{@code.outdated}}</span>
            {{/if}}
            <LinkTo
              @route="pr.diff"
              @query={{this.diffAt}}
              class="btn see-in-diff"
              data-test-see-in-diff
            >See in Diff</LinkTo>
          </div>
          <div class="thread-diff">
            {{#each this.lines key="number" as |line|}}
              <div
                class="diff-row context"
                data-test-row="context"
                data-ranged={{if line.marked "1"}}
              ><span class="ln">{{line.number}}</span><span
                  class="code"
                  data-test-code
                  {{drawn line.draw line.text}}
                ></span></div>
            {{/each}}
          </div>
        </div>
      {{else if this.loading}}
        <p class="diff-placeholder" data-test-loading="code">
          Loading the code…
        </p>
        <Waiting @on="/api/files?" />
      {{/if}}
    </section>
  </template>
}
