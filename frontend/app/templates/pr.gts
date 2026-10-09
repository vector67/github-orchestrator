import type { TOC } from '@ember/component/template-only';
import PrView from 'frontend/components/pr-view';
import type { Numbered } from 'frontend/data/wall';

interface PrSignature {
  Args: { model: Numbered };
}

const Pr: TOC<PrSignature> = <template>
  <PrView @pr={{@model}}>{{outlet}}</PrView>
</template>;

export default Pr;
