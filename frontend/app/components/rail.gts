import Component from '@glimmer/component';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import { fn } from '@ember/helper';
import RailRow from 'frontend/components/rail-row';
import { WAITING_FOR_FACTS } from 'frontend/components/thread-panel';
import type { Section } from 'frontend/services/threads';
import type BoardService from 'frontend/services/board';
import type BoardKeysService from 'frontend/services/board-keys';
import { moves, selects } from 'frontend/motion';

export interface RailSignature {
  Element: HTMLUListElement;
  Args: {
    sections: Section[];
    waiting?: boolean;
  };
}

export default class Rail extends Component<RailSignature> {
  @service declare board: BoardService;
  @service('board-keys') declare boardKeys: BoardKeysService;

  get selected(): string | null {
    return this.boardKeys.openId;
  }

  get sections(): Section[] {
    return this.args.sections ?? [];
  }

  <template>
    <ul
      id="rows"
      role="listbox"
      {{moves}}
      {{selects this.selected}}
      ...attributes
    >
      {{#if @waiting}}
        <li
          class="work-placeholder"
          role="presentation"
          data-test-board-waiting
        >
          {{WAITING_FOR_FACTS}}
        </li>
      {{/if}}
      {{#each this.sections key="group.key" as |section|}}
        <li
          class="group-head"
          role="presentation"
          title={{section.group.hint}}
          data-flip-key="head:{{section.group.key}}"
          data-test-heading={{section.group.key}}
        >
          <span class="group-name">{{section.group.label}}</span>
          <span class="group-count" data-test-count>
            {{section.rows.length}}
          </span>
        </li>
        {{#each section.rows key="id" as |row|}}
          <RailRow
            @row={{row}}
            @selectedId={{this.selected}}
            data-flip-key={{row.id}}
            data-flip-group={{section.group.key}}
            data-decided={{if (this.board.isDecided row.id) "true"}}
            {{on "click" (fn this.boardKeys.open row.id)}}
          />
        {{/each}}
      {{/each}}
    </ul>
  </template>
}
