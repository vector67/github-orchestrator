import type { TOC } from '@ember/component/template-only';

const PendingRing: TOC<{ Element: HTMLSpanElement }> = <template>
  <span
    class="pending-ring"
    aria-hidden="true"
    data-test-ring
    ...attributes
  ></span>
</template>;

export default PendingRing;
