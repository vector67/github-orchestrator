import type { TOC } from '@ember/component/template-only';
import LoadTrouble from 'frontend/components/load-trouble';

interface ApplicationErrorSignature {
  Args: { model: unknown };
}

const ApplicationError: TOC<ApplicationErrorSignature> = <template>
  <LoadTrouble @trouble={{@model}} />
</template>;

export default ApplicationError;
