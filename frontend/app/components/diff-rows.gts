import type { TOC } from '@ember/component/template-only';
import { fn } from '@ember/helper';
import { on } from '@ember/modifier';
import FoldIcon from 'frontend/components/fold-icon';
import { isHeader, type DiffRow, type Expand } from 'frontend/data/diff-rows';
import { selectable } from 'frontend/data/selection';
import drawn from 'frontend/modifiers/drawn';

export interface DiffRowsSignature {
  Args: {
    rows: DiffRow[];
    reveal: (expand: Expand) => void;
    selectable?: boolean;
    selected?: (row: DiffRow) => boolean;
  };
  Blocks: { gutter: [DiffRow]; after: [DiffRow] };
}

const SIGNS: Record<string, string> = { added: '+', removed: '-' };

function signOf(kind: string): string {
  return SIGNS[kind] ?? '';
}

function isSelected(
  selected: ((row: DiffRow) => boolean) | undefined,
  row: DiffRow,
): boolean {
  return selected?.(row) ?? false;
}

const DiffRows: TOC<DiffRowsSignature> = <template>
  <div class="thread-diff">
    {{#each @rows key="@index" as |row|}}
      {{#if (isHeader row)}}
        <div class="diff-row hunk" data-test-row="hunk"><span
            class="expanders"
          >{{#each row.expands key="direction" as |expand|}}<button
                type="button"
                class="expander"
                aria-label={{expand.label}}
                title={{expand.label}}
                data-test-expand={{expand.direction}}
                {{on "click" (fn @reveal expand)}}
              ><FoldIcon
                  @direction={{expand.direction}}
                /></button>{{/each}}</span><span
            class="code"
            data-test-code
          >{{row.code}}</span></div>
      {{else}}
        <div
          class="diff-row {{row.kind}}"
          data-test-row={{row.kind}}
          data-file={{row.file}}
          data-line={{row.line}}
          data-hunk={{row.hunk}}
          data-at={{row.at}}
          data-test-end={{row.mark}}
          data-selected={{if (isSelected @selected row) "1"}}
        >{{#if row.numbered}}<span
              class="ln"
              data-test-old
            >{{row.old}}</span><span
              class="ln"
              data-test-new
            >{{row.new}}</span>{{/if}}{{#if @selectable}}{{#if
              (selectable row)
            }}<button
                type="button"
                class="gutter-add"
                aria-label="comment on line {{row.mark}}"
                data-test-add
              >+</button>{{else}}<span
                class="gutter-space"
              ></span>{{/if}}{{/if}}{{yield row to="gutter"}}{{#if
            row.numbered
          }}<span class="sign" aria-hidden="true" data-test-sign>{{signOf
                row.kind
              }}</span>{{/if}}<span
            class="code"
            data-test-code
            {{drawn row.draw row.code}}
          ></span></div>
        {{yield row to="after"}}
      {{/if}}
    {{/each}}
  </div>
</template>;

export default DiffRows;
