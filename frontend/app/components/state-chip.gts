import type { TOC } from '@ember/component/template-only';
import type { Chip } from 'frontend/data/dashboard';

export interface StateChipSignature {
  Args: { chip: Chip };
}

const blocking = (chip: Chip): true | undefined =>
  chip.tone === 'alarm' ? true : undefined;

const StateChip: TOC<StateChipSignature> = <template>
  <span
    class="state-chip tone-{{@chip.tone}}"
    title={{@chip.hint}}
    data-test-state={{@chip.key}}
    data-test-blocking={{blocking @chip}}
  >{{@chip.text}}</span>
</template>;

export default StateChip;
