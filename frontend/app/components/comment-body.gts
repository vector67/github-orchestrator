import Component from '@glimmer/component';
import { service } from '@ember/service';
import { markdownWith } from 'frontend/data/markdown';
import drawn from 'frontend/modifiers/drawn';
import type StoreService from 'frontend/services/store';

export interface CommentBodySignature {
  Element: HTMLDivElement;
  Args: { body: string };
}

export default class CommentBody extends Component<CommentBodySignature> {
  @service declare store: StoreService;

  get drawing(): (text: string) => DocumentFragment {
    return markdownWith(this.store.emojis);
  }

  <template>
    <div
      class="comment-body"
      data-test-entry-body
      {{drawn this.drawing @body}}
      ...attributes
    ></div>
  </template>
}
