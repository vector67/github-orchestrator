import type { TOC } from '@ember/component/template-only';
import DraftComposer from 'frontend/components/draft-composer';

const NewDraftTemplate: TOC<object> = <template>
  <section id="panel-body" data-test-new-draft-panel>
    <div id="panel-top">
      <DraftComposer @key={{null}} @draft={{null}}>
        <header class="panel-head">
          <span class="square" data-square="ready"></span>
          <span class="panel-who">
            <span class="panel-kicker">
              <span class="kicker-place">New draft</span>
            </span>
          </span>
        </header>
      </DraftComposer>
    </div>
  </section>
</template>;

export default NewDraftTemplate;
