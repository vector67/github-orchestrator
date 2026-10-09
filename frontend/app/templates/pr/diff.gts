import type { TOC } from '@ember/component/template-only';
import DiffTab from 'frontend/components/diff-tab';
import ToastRail from 'frontend/components/toast-rail';
import type PrDiffController from 'frontend/controllers/pr/diff';

interface PrDiffSignature {
  Args: { controller: PrDiffController };
}

const PrDiff: TOC<PrDiffSignature> = <template>
  <DiffTab
    @file={{@controller.file}}
    @line={{@controller.line}}
    @show={{@controller.show}}
  />
  <ToastRail />
</template>;

export default PrDiff;
