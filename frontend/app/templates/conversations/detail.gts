import type { TOC } from '@ember/component/template-only';
import ThreadPanel from 'frontend/components/thread-panel';

interface DetailSignature {
  Args: { model: string };
}

const Detail: TOC<DetailSignature> = <template>
  <ThreadPanel @key={{@model}} />
</template>;

export default Detail;
