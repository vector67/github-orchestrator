import type { TOC } from '@ember/component/template-only';
import TerminalTab from 'frontend/components/terminal-tab';
import ToastRail from 'frontend/components/toast-rail';

const Terminal: TOC<object> = <template>
  <TerminalTab />
  <ToastRail />
</template>;

export default Terminal;
