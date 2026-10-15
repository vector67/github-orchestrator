import type { TOC } from '@ember/component/template-only';
import SummaryTab from 'frontend/components/summary-tab';
import ToastRail from 'frontend/components/toast-rail';

const Summary: TOC<object> = <template>
  <SummaryTab />
  <ToastRail />
</template>;

export default Summary;
