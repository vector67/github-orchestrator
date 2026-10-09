import type { TOC } from '@ember/component/template-only';
import BoardStrip from 'frontend/components/board-strip';
import BoardUnreachable from 'frontend/components/board-unreachable';
import Rail from 'frontend/components/rail';
import ToastRail from 'frontend/components/toast-rail';
import type ThreadsService from 'frontend/services/threads';

interface ConversationsSignature {
  Args: { model: ThreadsService };
}

const Conversations: TOC<ConversationsSignature> = <template>
  {{#if @model.loaded}}
    <BoardStrip @header={{@model.header}} />
    <div id="board">
      <Rail
        @sections={{@model.sections}}
        @waiting={{if @model.role false true}}
      />
      <section id="panel">
        {{outlet}}
      </section>
    </div>
  {{else}}
    <BoardUnreachable />
  {{/if}}
  <ToastRail />
</template>;

export default Conversations;
