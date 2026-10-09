import type { TOC } from '@ember/component/template-only';
import BoardColumns from 'frontend/components/board-columns';
import BoardStrip from 'frontend/components/board-strip';
import BoardUnreachable from 'frontend/components/board-unreachable';
import ToastRail from 'frontend/components/toast-rail';
import type ThreadsService from 'frontend/services/threads';

interface BoardSignature {
  Args: { model: ThreadsService };
}

const BoardView: TOC<BoardSignature> = <template>
  {{#if @model.loaded}}
    <BoardStrip @header={{@model.header}} />
    <BoardColumns @columns={{@model.columns}} />
  {{else}}
    <BoardUnreachable />
  {{/if}}
  <ToastRail />
</template>;

export default BoardView;
