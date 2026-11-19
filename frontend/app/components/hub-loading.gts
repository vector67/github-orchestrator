import type { TOC } from '@ember/component/template-only';
import Waiting from 'frontend/components/waiting';

interface HubLoadingSignature {
  Args: { on: 'wall' | 'runs' | 'terminals' | 'setup' };
}

const HubLoading: TOC<HubLoadingSignature> = <template>
  <div class="page-loading">
    <p class="work-placeholder" data-test-loading={{@on}}>
      Loading the
      {{@on}}…
    </p>
    <Waiting />
  </div>
</template>;

export default HubLoading;
