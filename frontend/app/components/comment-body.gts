import type { TOC } from '@ember/component/template-only';
import { markdownOf } from 'frontend/data/markdown';
import drawn from 'frontend/modifiers/drawn';

export interface CommentBodySignature {
  Element: HTMLDivElement;
  Args: { body: string };
}

const CommentBody: TOC<CommentBodySignature> = <template>
  <div
    class="comment-body"
    data-test-entry-body
    {{drawn markdownOf @body}}
    ...attributes
  ></div>
</template>;

export default CommentBody;
