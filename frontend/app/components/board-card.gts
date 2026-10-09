import type { TOC } from '@ember/component/template-only';
import type { Row } from 'frontend/data/rows';

export interface BoardCardSignature {
  Element: HTMLButtonElement;
  Args: { row: Row };
}

const BoardCard: TOC<BoardCardSignature> = <template>
  <button
    type="button"
    class="board-card"
    data-test-card={{@row.id}}
    data-group={{@row.group}}
    data-square={{@row.square}}
    ...attributes
  >
    {{#if @row.reference}}
      <span class="card-path" data-test-card-path>{{@row.reference}}</span>
    {{/if}}
    <span class="card-title" data-test-card-title>{{@row.gist}}</span>
    {{#if @row.alert}}
      <span class="alert" data-test-alert>{{@row.alert}}</span>
    {{/if}}
    <span class="card-steps">
      {{#each @row.steps key="@index" as |done|}}
        <span
          class="step-square"
          data-test-step
          data-done={{if done "1"}}
        ></span>
      {{/each}}
      <span
        class="card-steps-text"
        title={{if @row.steps_hint @row.steps_hint}}
        data-test-card-steps
      >{{@row.steps_text}}</span>
    </span>
    {{#if @row.meta}}
      <span class="card-meta" data-test-card-meta>{{@row.meta}}</span>
    {{/if}}
  </button>
</template>;

export default BoardCard;
