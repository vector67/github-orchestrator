import Component from '@glimmer/component';
import type { FileStat, Panel } from 'frontend/data/panel';

export interface FixMetaSignature {
  Element: HTMLDivElement;
  Args: { panel: Panel };
}

export default class FixMeta extends Component<FixMetaSignature> {
  get verdict(): string {
    const { tests } = this.args.panel;
    return tests ? `Tests ${tests}` : '';
  }

  get files(): FileStat[] {
    return this.args.panel.files ?? [];
  }

  get shows(): boolean {
    return Boolean(this.verdict || this.files.length);
  }

  <template>
    {{#if this.shows}}
      <div class="fix-meta" data-test-fix-meta ...attributes>
        {{#if this.verdict}}
          {{#if @panel.tests_note}}
            <details class="meta-pop" name="fix-meta" data-test-verdict>
              <summary>{{this.verdict}}</summary>
              <div class="pop">
                <span class="kicker">Tests</span>
                <p>{{@panel.tests_note}}</p>
              </div>
            </details>
          {{else}}
            <span class="meta-item" data-test-verdict>{{this.verdict}}</span>
          {{/if}}
        {{/if}}
        {{#if this.files.length}}
          <details class="meta-pop" name="fix-meta" data-test-files>
            <summary>{{@panel.files_label}}</summary>
            <div class="pop">
              <span class="kicker">Files touched</span>
              {{#each this.files key="path" as |file|}}
                <p class="file-row">
                  <span class="file-path">{{file.path}}</span>
                  <span class="file-added">+{{file.added}}</span>
                  <span class="file-removed">−{{file.removed}}</span>
                </p>
              {{/each}}
            </div>
          </details>
        {{/if}}
      </div>
    {{/if}}
  </template>
}
