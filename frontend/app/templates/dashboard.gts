import type { TOC } from '@ember/component/template-only';
import DashboardTab from 'frontend/components/dashboard-tab';
import ToastRail from 'frontend/components/toast-rail';
import type DashboardController from 'frontend/controllers/dashboard';

interface DashboardSignature {
  Args: { controller: DashboardController };
}

const Dashboard: TOC<DashboardSignature> = <template>
  <DashboardTab @pane={{@controller.pane}} />
  <ToastRail />
</template>;

export default Dashboard;
