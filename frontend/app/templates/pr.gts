import type { TOC } from '@ember/component/template-only';
import AnswerReply from 'frontend/components/answer-reply';
import PrView from 'frontend/components/pr-view';
import type { Numbered } from 'frontend/data/wall';

interface PrSignature {
  Args: { model: Numbered };
}

const Pr: TOC<PrSignature> = <template>
  <PrView @pr={{@model}}>{{outlet}}</PrView>
  <AnswerReply />
</template>;

export default Pr;
