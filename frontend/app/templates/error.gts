import type { TOC } from '@ember/component/template-only';
import LoadTrouble from 'frontend/components/load-trouble';

interface ErrorSignature {
  Args: { model: unknown };
}

const ErrorView: TOC<ErrorSignature> = <template>
  <LoadTrouble @trouble={{@model}} />
</template>;

export default ErrorView;
