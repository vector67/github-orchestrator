import type { TOC } from '@ember/component/template-only';
import CodeContext from 'frontend/components/code-context';
import CommentBody from 'frontend/components/comment-body';
import CopyDirectory from 'frontend/components/copy-directory';
import DiffFold from 'frontend/components/diff-fold';
import DraftComposer from 'frontend/components/draft-composer';
import FixMeta from 'frontend/components/fix-meta';
import GoToSession from 'frontend/components/go-to-session';
import PanelActions from 'frontend/components/panel-actions';
import PanelHeader from 'frontend/components/panel-header';
import ReplyBoxComponent from 'frontend/components/reply-box';
import Waiting from 'frontend/components/waiting';
import type { Panel } from 'frontend/data/panel';

export interface PanelSignature {
  Element: HTMLElement;
  Args: { panel: Panel };
}

function offersAnything(panel: Panel) {
  return Boolean(panel.actions?.length) || Boolean(panel.reply_action);
}

function replies(panel: Panel) {
  return Boolean(panel.reply);
}

function reviewing(panel: Panel) {
  return panel.role === 'reviewer';
}

const PanelView: TOC<PanelSignature> = <template>
  <section id="panel-body" ...attributes>
    <div id="panel-top">
      {{#if @panel.draft}}
        <DraftComposer @key={{@panel.id}} @draft={{@panel.draft}}>
          <PanelHeader @panel={{@panel}} />
        </DraftComposer>
      {{else}}
        <div id="panel-talk">
          <PanelHeader @panel={{@panel}} />
          {{#if @panel.loading}}
            <p class="work-placeholder" data-test-loading="thread">
              Loading the thread…
            </p>
            <Waiting @on="/api/conversations/{{@panel.id}}/" />
          {{else if @panel.transcript}}
            <section id="panel-thread" data-test-transcript>
              {{#each @panel.transcript key="@index" as |entry|}}
                <article
                  class="transcript-entry"
                  data-marked={{if entry.highlighted "1"}}
                  data-test-entry
                >
                  <div class="entry-head">
                    <span class="entry-who" data-test-entry-who>{{if
                        entry.author_name
                        entry.author_name
                        entry.author
                      }}</span>
                    {{#if entry.meta}}
                      <span class="entry-meta" data-test-entry-meta>
                        {{entry.meta}}
                      </span>
                    {{/if}}
                  </div>
                  <CommentBody @body={{entry.body}} />
                </article>
              {{/each}}
            </section>
          {{/if}}
          {{#if @panel.reply}}
            <ReplyBoxComponent
              @conversationId={{@panel.id}}
              @reply={{@panel.reply}}
              @reviewerName={{@panel.reply_to}}
            />
          {{/if}}
        </div>
        {{#if @panel.code}}
          <div id="panel-anchor">
            <CodeContext @code={{@panel.code}} />
          </div>
        {{/if}}
      {{/if}}
    </div>
    <div id="panel-work">
      <div id="panel-fix">
        {{#if @panel.draft}}{{else if (reviewing @panel)}}
          {{#unless @panel.mention}}
            <p class="work-placeholder" data-test-work-placeholder>
              What the author did lands here
            </p>
          {{/unless}}
        {{else}}
          {{#if @panel.fix_label}}
            <h2 class="fix-label" data-test-fix-label>{{@panel.fix_label}}
              {{#if @panel.fix_directory}}
                <CopyDirectory @directory={{@panel.fix_directory}} />
              {{/if}}
            </h2>
          {{/if}}
          {{#if @panel.in_session}}
            <GoToSession @directory={{@panel.fix_directory}} />
          {{/if}}
          {{#if @panel.banner}}
            <aside
              class="fix-banner {{@panel.banner.tone}}"
              data-test-banner-fix
            >
              <span class="square" data-square={{@panel.square}}></span>
              <span class="banner-text">
                <strong>{{@panel.banner.title}}</strong>
                <span>{{@panel.banner.body}}</span>
              </span>
            </aside>
          {{/if}}
          {{#if @panel.proposed_ticket}}
            <div class="proposed-ticket" data-test-proposed-ticket>
              <p class="ticket-head">
                <span
                  class="ticket-project"
                  data-test-ticket-project-shown
                >{{@panel.proposed_ticket.project}}</span>
                <span
                  class="ticket-title"
                  data-test-ticket-title-shown
                >{{@panel.proposed_ticket.title}}</span>
              </p>
              <p
                class="ticket-body"
                data-test-ticket-body-shown
              >{{@panel.proposed_ticket.body}}</p>
            </div>
          {{/if}}
          {{#if @panel.proposed_reply}}
            <blockquote
              class="proposed-reply"
              data-test-proposed-reply
            >{{@panel.proposed_reply}}</blockquote>
          {{/if}}
          {{#if @panel.summary}}
            <p class="gist" data-test-panel-summary>{{@panel.summary}}</p>
          {{/if}}
          {{#if @panel.failure}}
            <section class="panel-failure" data-test-failure>
              <p class="land-headline">{{@panel.failure.headline}}</p>
              {{#if @panel.failure.summary}}
                <p
                  class="land-cause"
                  data-test-failure-summary
                >{{@panel.failure.summary}}</p>
              {{/if}}
              <p class="land-standing">{{@panel.failure.standing}}</p>
              {{#if @panel.failure.machine}}
                <details class="land-output">
                  <summary>{{@panel.failure.output_label}}</summary>
                  <pre
                    class="land-error"
                    data-test-failure-output
                  >{{@panel.failure.machine}}</pre>
                </details>
              {{/if}}
            </section>
          {{else}}
            {{#if @panel.plan}}
              <ol class="plan" data-test-plan>
                {{#each @panel.plan key="@index" as |step|}}
                  <li
                    class="plan-step"
                    data-done={{if step.done "1"}}
                    data-test-plan-step
                  >
                    <span class="plan-mark"></span>
                    <span class="step-text">{{step.text}}</span>
                    <span
                      class="step-file"
                      data-test-step-file
                    >{{step.file}}</span>
                  </li>
                {{/each}}
              </ol>
            {{/if}}
            {{#if @panel.confidence}}
              <div class="confidence" data-test-confidence>
                <p class="kicker">Confidence: {{@panel.confidence}}</p>
                {{#if @panel.confidence_note}}
                  <p class="note">{{@panel.confidence_note}}</p>
                {{/if}}
              </div>
            {{/if}}
            <FixMeta @panel={{@panel}} />
          {{/if}}
        {{/if}}
        {{#if @panel.notes}}
          <section class="notes" data-test-notes>
            {{#each @panel.notes key="@index" as |note|}}
              <p class="note {{note.kind}}">{{note.text}}</p>
              {{#if note.detail}}
                <details class="note-detail">
                  <summary>Details</summary>
                  <pre data-test-note-detail>{{note.detail}}</pre>
                </details>
              {{/if}}
            {{/each}}
          </section>
        {{/if}}
      </div>
      <div id="panel-diff">
        {{#unless (reviewing @panel)}}
          {{#if @panel.fold}}
            <DiffFold
              @conversationId={{@panel.id}}
              @fold={{@panel.fold}}
              @anchor={{@panel.anchor}}
            />
          {{else if @panel.fold_placeholder}}
            <p class="diff-placeholder" data-test-fold-placeholder>
              {{@panel.fold_placeholder}}
            </p>
          {{/if}}
        {{/unless}}
      </div>
    </div>
    {{#if (offersAnything @panel)}}
      <PanelActions
        @conversationId={{@panel.id}}
        @actions={{@panel.actions}}
        @replyAction={{@panel.reply_action}}
        @replies={{replies @panel}}
        @canDelete={{@panel.can_delete}}
        @agentWords={{@panel.agent_words}}
        @accept={{@panel.accept}}
        @rework={{@panel.rework}}
        @fold={{@panel.fold}}
        @draft={{@panel.draft}}
      />
    {{/if}}
  </section>
</template>;

export default PanelView;
