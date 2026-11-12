import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import { fn } from '@ember/helper';
import { modifier } from 'ember-modifier';
import type { Reaction, ReactionKind } from 'frontend/data/api';
import type KeysService from 'frontend/services/keys';
import type { Keymap } from 'frontend/services/keys';
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

const EDGE = 8;
const GAP = 4;

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
  @service declare keys: KeysService;
  @service declare threads: ThreadsService;
  @service declare toasts: ToastsService;

  @tracked picking = false;
  @tracked sending = false;

  faces = FACES;

  private readonly keymap: Keymap = {
    take: (key) => {
      if (key !== 'Escape') return false;
      this.picking = false;
      return true;
    },
  };

  shown = modifier((element: HTMLElement) => {
    const trigger = element
      .closest('.comment-reactions')!
      .querySelector('.reaction-add')!;
    const smiley = trigger.getBoundingClientRect();
    element.showPopover();
    const below = smiley.bottom + GAP;
    const above = smiley.top - GAP - element.offsetHeight;
    const fitsBelow = below + element.offsetHeight <= window.innerHeight - EDGE;
    element.style.top = `${fitsBelow || above < EDGE ? below : above}px`;
    const room = window.innerWidth - element.offsetWidth - EDGE;
    element.style.left = `${Math.max(EDGE, Math.min(smiley.left, room))}px`;
    const moved = (scrolled: Event) => {
      if (element.contains(scrolled.target as Node)) return;
      const now = trigger.getBoundingClientRect();
      if (now.top !== smiley.top || now.left !== smiley.left)
        this.picking = false;
    };
    const outside = (pressed: Event) => {
      const target = pressed.target as Node;
      if (!element.contains(target) && !trigger.contains(target))
        this.picking = false;
    };
    document.addEventListener('scroll', moved, true);
    document.addEventListener('mousedown', outside, true);
    this.keys.push('dialog', this.keymap);
    return () => {
      document.removeEventListener('scroll', moved, true);
      document.removeEventListener('mousedown', outside, true);
      this.keys.drop(this.keymap);
    };
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
        ><svg
            class="smiley"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentcolor"
            stroke-width="1.5"
            stroke-linecap="round"
            aria-hidden="true"
            focusable="false"
          ><circle cx="8" cy="8" r="6.75" /><path
              d="M5.5 9.75c.6.8 1.45 1.25 2.5 1.25s1.9-.45 2.5-1.25"
            /><circle cx="5.75" cy="6.5" r=".5" fill="currentcolor" /><circle
              cx="10.25"
              cy="6.5"
              r=".5"
              fill="currentcolor"
            /></svg></button>
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
