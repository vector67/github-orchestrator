import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import { fn } from '@ember/helper';
import { modifier } from 'ember-modifier';
import type { Reaction, ReactionKind } from 'frontend/data/api';
import type ThreadsService from 'frontend/services/threads';
import type ToastsService from 'frontend/services/toasts';

interface Face {
  kind: ReactionKind;
  face: string;
}

const FACES: Face[] = [
  { kind: 'thumbs-up', face: '👍' },
  { kind: 'thumbs-down', face: '👎' },
  { kind: 'laugh', face: '😄' },
  { kind: 'hooray', face: '🎉' },
  { kind: 'confused', face: '😕' },
  { kind: 'heart', face: '❤️' },
  { kind: 'rocket', face: '🚀' },
  { kind: 'eyes', face: '👀' },
];

function faceOf(kind: ReactionKind): string {
  return FACES.find((one) => one.kind === kind)?.face ?? '';
}

function pressed(reaction: Reaction): string {
  return reaction.mine ? 'true' : 'false';
}

export interface CommentReactionsSignature {
  Args: { conversation: string; comment: number; reactions: Reaction[] };
}

export default class CommentReactions extends Component<CommentReactionsSignature> {
  @service declare threads: ThreadsService;
  @service declare toasts: ToastsService;

  @tracked picking = false;
  @tracked sending = false;

  faces = FACES;

  shown = modifier((element: HTMLElement) => {
    const smiley = element
      .closest('.comment-reactions')!
      .querySelector('.reaction-add')!
      .getBoundingClientRect();
    element.style.top = `${smiley.bottom + 4}px`;
    element.style.left = `${smiley.left}px`;
    element.showPopover();
    const close = (scrolled: Event) => {
      if (!element.contains(scrolled.target as Node)) this.picking = false;
    };
    document.addEventListener('scroll', close, true);
    return () => document.removeEventListener('scroll', close, true);
  });

  togglePicker = (): void => {
    this.picking = !this.picking;
  };

  pick = async (content: ReactionKind): Promise<void> => {
    this.picking = false;
    const held = this.args.reactions.find((one) => one.content === content);
    await this.send(content, !held?.mine);
  };

  press = async (reaction: Reaction): Promise<void> => {
    await this.send(reaction.content, !reaction.mine);
  };

  private async send(content: ReactionKind, mine: boolean): Promise<void> {
    this.sending = true;
    const sent = await this.threads.react(
      this.args.conversation,
      this.args.comment,
      {
        content,
        mine,
      },
    );
    this.sending = false;
    if (!sent.done) this.toasts.say(`Reaction not sent: ${sent.why}`, 'failed');
  }

  <template>
    <div class="comment-reactions" data-test-reactions>
      <div class="reaction-row">
        <button
          type="button"
          class="reaction-add"
          aria-label="Add a reaction"
          aria-expanded={{if this.picking "true" "false"}}
          disabled={{this.sending}}
          data-test-react
          {{on "click" this.togglePicker}}
        >☺</button>
        {{#each @reactions key="content" as |reaction|}}
          <button
            type="button"
            class="reaction"
            aria-pressed={{pressed reaction}}
            disabled={{this.sending}}
            data-test-reaction={{reaction.content}}
            {{on "click" (fn this.press reaction)}}
          >{{faceOf reaction.content}} {{reaction.count}}</button>
        {{/each}}
      </div>
      {{#if this.picking}}
        <div
          class="reaction-picker"
          popover="manual"
          role="menu"
          data-test-reaction-picker
          {{this.shown}}
        >
          {{#each this.faces key="kind" as |offered|}}
            <button
              type="button"
              class="reaction-option"
              role="menuitem"
              aria-label={{offered.kind}}
              data-test-reaction-option={{offered.kind}}
              {{on "click" (fn this.pick offered.kind)}}
            >{{offered.face}}</button>
          {{/each}}
        </div>
      {{/if}}
    </div>
  </template>
}
