import type { TOC } from '@ember/component/template-only';

type Direction = 'up' | 'down' | 'all';

export interface FoldIconSignature {
  Args: { direction: Direction };
}

const eq = (direction: Direction, wanted: Direction) => direction === wanted;

const FoldIcon: TOC<FoldIconSignature> = <template>
  <svg
    class="fold-icon"
    viewBox="0 0 16 16"
    fill="none"
    stroke="currentcolor"
    stroke-width="1.5"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    focusable="false"
  >
    {{#if (eq @direction "up")}}
      <path d="M8 10V2.5M5 5.5l3-3 3 3" />
      <path d="M2 13.5h12" stroke-dasharray="1.5 2.25" />
    {{else if (eq @direction "down")}}
      <path d="M8 6v7.5M5 10.5l3 3 3-3" />
      <path d="M2 2.5h12" stroke-dasharray="1.5 2.25" />
    {{else}}
      <path d="M8 5V1.5M6 3.5l2-2 2 2M8 11v3.5M6 12.5l2 2 2-2" />
      <path d="M2 8h12" stroke-dasharray="1.5 2.25" />
    {{/if}}
  </svg>
</template>;

export default FoldIcon;
