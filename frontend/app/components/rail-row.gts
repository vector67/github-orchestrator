import type { TOC } from '@ember/component/template-only';
import type { Row } from 'frontend/data/rows';

export interface RailRowSignature {
  Element: HTMLLIElement;
  Args: {
    row: Row;
    selectedId?: string | null;
  };
}

function rowId(row: Row): string {
  return `c-${row.id}`;
}

function selectedWord(row: Row, selectedId?: string | null): string {
  return row.id === selectedId ? 'true' : 'false';
}

const RailRow: TOC<RailRowSignature> = <template>
  <li
    class="rail-row edge"
    role="option"
    id={{rowId @row}}
    aria-selected={{selectedWord @row @selectedId}}
    data-group={{@row.group}}
    data-square={{@row.square}}
    data-provisional={{if @row.provisional "true"}}
    ...attributes
  >
    <span class="rail-row-text">
      <span class="gist" data-test-gist>{{@row.gist}}</span>
      {{#if @row.reference}}
        <span class="path" data-test-path>{{@row.reference}}</span>
      {{/if}}
      {{#if @row.standing}}
        <span
          class="standing"
          data-standing={{@row.standing}}
          data-test-standing
        >{{@row.standing_label}}</span>
      {{/if}}
      {{#if @row.alert}}
        <span class="alert" data-test-alert>{{@row.alert}}</span>
      {{/if}}
      {{#if @row.meta}}
        <span class="meta" data-test-meta>{{@row.meta}}</span>
      {{/if}}
    </span>
  </li>
</template>;

export default RailRow;
