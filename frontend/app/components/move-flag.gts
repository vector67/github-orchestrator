import type { TOC } from '@ember/component/template-only';
import type { MoveFlag } from 'frontend/data/dashboard';

export interface MoveFlagSignature {
  Args: { flag: MoveFlag };
}

const MoveFlagTag: TOC<MoveFlagSignature> = <template>
  <span
    class="move-flag {{if @flag.alarm 'alarm'}}"
    data-test-move-flag={{@flag.code}}
  >{{#if @flag.alarm}}<i class="sq alarm"></i>{{/if}}{{@flag.text}}</span>
</template>;

export default MoveFlagTag;
