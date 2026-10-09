import Component from '@glimmer/component';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import { fn } from '@ember/helper';
import BoardCard from 'frontend/components/board-card';
import type BoardKeysService from 'frontend/services/board-keys';
import type { Group } from 'frontend/data/groups';
import type { Row } from 'frontend/data/rows';
import { moves } from 'frontend/motion';

export interface BoardColumnsSignature {
  Element: HTMLDivElement;
  Args: {
    columns: { column: Group; rows: Row[] }[];
  };
}

export default class BoardColumns extends Component<BoardColumnsSignature> {
  @service('board-keys') declare boardKeys: BoardKeysService;

  <template>
    <div
      id="board-columns"
      data-test-board-columns
      {{moves "slide-far"}}
      ...attributes
    >
      {{#each @columns key="column.key" as |column|}}
        <section class="board-column" data-test-column={{column.column.key}}>
          <h2 class="column-head">
            <span class="square" data-square={{column.column.key}}></span>
            <span
              class="column-name"
              title={{column.column.hint}}
              data-test-column-name
            >{{column.column.label}}</span>
            <span class="column-count" data-test-column-count>
              {{column.rows.length}}
            </span>
          </h2>
          <div class="column-cards">
            {{#each column.rows key="id" as |row|}}
              <BoardCard
                @row={{row}}
                data-flip-key={{row.id}}
                data-flip-group={{column.column.key}}
                {{on "click" (fn this.boardKeys.open row.id)}}
              />
            {{/each}}
          </div>
        </section>
      {{/each}}
    </div>
  </template>
}
