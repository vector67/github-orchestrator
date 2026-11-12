import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import { fn } from '@ember/helper';
import RequestSessionAsk from 'frontend/components/request-session-ask';
import didChange from 'frontend/modifiers/did-change';
import type BoardService from 'frontend/services/board';
import type RequestSessionService from 'frontend/services/request-session';

interface QuestionAnswersSignature {
  Args: {
    conversationId: string;
    options: string[];
    pending: boolean;
  };
}

const ASKED = 'Answer in a visible session?';

const NOTE =
  'A visible session carries on the agent’s own conversation in the ' +
  'terminal with your answer, where you can watch it and type to it. ' +
  'Without one it carries on unwatched. Either way it comes back to the ' +
  'board as a proposal or another question.';

export default class QuestionAnswers extends Component<QuestionAnswersSignature> {
  @service declare board: BoardService;
  @service declare requestSession: RequestSessionService;

  @tracked typing = false;
  @tracked typed = '';
  @tracked choosing: string | null = null;

  readonly asked = ASKED;
  readonly note = NOTE;

  get unsendable(): boolean {
    return this.args.pending || this.typed.trim() === '';
  }

  pick = (option: string) => this.answer(option);

  other = () => {
    this.typing = !this.typing;
  };

  type = (event: Event) => {
    this.typed = (event.target as HTMLTextAreaElement).value;
  };

  focus = (element: HTMLElement) => {
    element.focus();
  };

  submit = (event: Event) => {
    event.preventDefault();
    if (!this.unsendable) this.answer(this.typed.trim());
  };

  private answer(text: string): void {
    const chosen = this.requestSession.answering;
    if (chosen === 'ask') this.choosing = text;
    else void this.send(text, chosen === 'visible');
  }

  choose = (visible: boolean, remember: boolean) => {
    const text = this.choosing;
    this.choosing = null;
    if (remember) this.requestSession.rememberAnswering(visible);
    if (text !== null) void this.send(text, visible);
  };

  stopChoosing = () => {
    this.choosing = null;
  };

  private async send(text: string, visible: boolean): Promise<void> {
    const sent = await this.board.decide(
      this.args.conversationId,
      visible ? 'answer-watched' : 'answer',
      { body: text },
    );
    if (!sent) return;
    this.typing = false;
    this.typed = '';
  }

  <template>
    <div class="question-answers" data-test-question-answers>
      {{#if @options}}
        <ol class="question-options">
          {{#each @options key="@index" as |option|}}
            <li>
              <button
                type="button"
                class="question-option"
                disabled={{@pending}}
                data-test-question-option
                {{on "click" (fn this.pick option)}}
              >{{option}}</button>
            </li>
          {{/each}}
        </ol>
      {{/if}}
      <button
        type="button"
        class="question-option other"
        aria-expanded={{if this.typing "true" "false"}}
        disabled={{@pending}}
        data-test-question-other
        {{on "click" this.other}}
      >Other…</button>
      {{#if this.typing}}
        <form class="reply question-other" {{on "submit" this.submit}}>
          <textarea
            aria-label="your answer"
            rows="3"
            placeholder="Your answer to the agent"
            value={{this.typed}}
            data-test-question-other-text
            {{on "input" this.type}}
            {{didChange this.focus}}
          ></textarea>
          <div class="reply-foot">
            <button
              type="submit"
              class="reply-send"
              disabled={{this.unsendable}}
              data-test-question-other-send
            >Answer</button>
          </div>
        </form>
      {{/if}}
    </div>
    {{#if this.choosing}}
      <RequestSessionAsk
        @question={{this.asked}}
        @note={{this.note}}
        @choose={{this.choose}}
        @cancel={{this.stopChoosing}}
      />
    {{/if}}
  </template>
}
