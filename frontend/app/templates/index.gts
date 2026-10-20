import type { TOC } from '@ember/component/template-only';
import ToastRail from 'frontend/components/toast-rail';
import Tour from 'frontend/components/tour';
import Wall from 'frontend/components/wall';
import type IndexController from 'frontend/controllers/index';

interface IndexSignature {
  Args: { controller: IndexController };
}

const Index: TOC<IndexSignature> = <template>
  <Wall @ready={{@controller.ready}} />
  <Tour />
  <ToastRail />
</template>;

export default Index;
