import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import { fn } from '@ember/helper';
import type RouterService from '@ember/routing/router-service';
import { modifier } from 'ember-modifier';
import DeferMention from 'frontend/components/defer-mention';
import { pageOf } from 'frontend/data/wall';
import navigates from 'frontend/modifiers/navigates';
import type KeysService from 'frontend/services/keys';
import type { Keymap } from 'frontend/services/keys';
import type StoreService from 'frontend/services/store';
import type { MentionRow } from 'frontend/services/store';
import type ToastsService from 'frontend/services/toasts';

const EDGE = 8;
const GAP = 4;

export default class MentionsCounter extends Component {
  @service declare router: RouterService;
  @service declare store: StoreService;
  @service declare keys: KeysService;
  @service declare toasts: ToastsService;

  @tracked listing = false;
  @tracked acting: MentionRow | null = null;
  @tracked deferring: MentionRow | null = null;

  private readonly keymap: Keymap = {
    take: (key) => {
      if (key !== 'Escape') return false;
      this.close();
      return true;
    },
  };

  private readonly actionKeys: Keymap = {
    take: (key) => {
      if (key !== 'Escape') return false;
      this.acting = null;
      return true;
    },
  };

  willDestroy(): void {
    super.willDestroy();
    this.keys.drop(this.keymap);
  }

  get mentions(): MentionRow[] {
    return this.store.mentionRows;
  }

  get counted(): number {
    return this.store.mentionCount;
  }

  open = () => {
    this.listing = true;
    this.keys.push('dialog', this.keymap);
  };

  close = () => {
    this.acting = null;
    this.listing = false;
    this.keys.drop(this.keymap);
  };

  hrefOf = (mention: MentionRow): string =>
    pageOf(
      { repo: mention.repo, number: mention.number },
      `/conversations/${encodeURIComponent(mention.thread ?? '')}`,
    );

  go = async (mention: MentionRow): Promise<void> => {
    this.close();
    await this.router.transitionTo(this.hrefOf(mention));
  };

  isActing = (mention: MentionRow): boolean => this.acting === mention;

  toggleActions = (mention: MentionRow): void => {
    this.acting = this.acting === mention ? null : mention;
  };

  leaveActions = (): void => {
    this.acting = null;
  };

  defer = (mention: MentionRow): void => {
    this.acting = null;
    this.deferring = mention;
  };

  stopDialog = (): void => {
    this.deferring = null;
  };

  stopDeferring = async (mention: MentionRow): Promise<void> => {
    this.acting = null;
    const stopped = await this.store.stopDeferringMention({
      repo: mention.repo,
      number: mention.number,
      comment_id: mention.comment_id,
    });
    if (!stopped.done)
      this.toasts.say(`Mention still deferred: ${stopped.why}`, 'failed');
  };

  dismiss = async (mention: MentionRow): Promise<void> => {
    this.acting = null;
    const dismissed = await this.store.dismissMention({
      repo: mention.repo,
      number: mention.number,
      comment_id: mention.comment_id,
    });
    if (!dismissed.done)
      this.toasts.say(`Mention not dismissed: ${dismissed.why}`, 'failed');
  };

  shown = modifier((element: HTMLElement) => {
    const arrow = element.closest('.mention')!.querySelector('.mention-more')!;
    const by = arrow.getBoundingClientRect();
    element.showPopover();
    const below = by.bottom + GAP;
    const fitsBelow = below + element.offsetHeight <= window.innerHeight - EDGE;
    const top = fitsBelow ? below : by.top - GAP - element.offsetHeight;
    element.style.top = `${Math.max(EDGE, top)}px`;
    const room = window.innerWidth - element.offsetWidth - EDGE;
    element.style.left = `${Math.max(EDGE, Math.min(by.right - element.offsetWidth, room))}px`;
    const moved = (scrolled: Event) => {
      if (!element.contains(scrolled.target as Node)) this.acting = null;
    };
    const resized = () => {
      this.acting = null;
    };
    const outside = (pressed: Event) => {
      const target = pressed.target as Node;
      if (!element.contains(target) && !arrow.contains(target))
        this.acting = null;
    };
    document.addEventListener('scroll', moved, true);
    window.addEventListener('resize', resized);
    document.addEventListener('mousedown', outside, true);
    this.keys.push('dialog', this.actionKeys);
    return () => {
      document.removeEventListener('scroll', moved, true);
      window.removeEventListener('resize', resized);
      document.removeEventListener('mousedown', outside, true);
      this.keys.drop(this.actionKeys);
    };
  });

  <template>
    <span class="mentions">
      <button
        type="button"
        class="mentions-count {{if this.counted 'outstanding'}}"
        aria-haspopup="true"
        aria-expanded={{if this.listing "true" "false"}}
        title="comments naming you that the board has not closed"
        data-test-mentions-count
        {{on "click" this.open}}
      >{{this.counted}}</button>
      {{#if this.listing}}
        <button
          type="button"
          class="mentions-scrim"
          tabindex="-1"
          aria-label="close the mentions"
          {{on "click" this.close}}
        ></button>
        <div class="mentions-menu" data-test-mentions-menu>
          {{#each this.mentions key="url" as |mention|}}
            <div
              class="mention
                {{if (this.isActing mention) 'acting'}}
                {{if mention.deferredUntil 'deferred'}}"
              data-test-mention={{mention.thread}}
            >
              {{#if mention.opensOnTheBoard}}
                <a
                  href={{this.hrefOf mention}}
                  class="mention-open"
                  data-test-mention-open
                  {{navigates (fn this.go mention)}}
                >
                  <span class="mention-head">{{mention.author}}
                    on
                    {{mention.repo}}#{{mention.number}}</span>
                  <span
                    class="mention-body"
                    data-test-mention-body
                  >{{mention.body}}</span>
                  {{#if mention.deferredUntil}}
                    <span
                      class="mention-deferred"
                      data-test-mention-deferred
                    >deferred {{mention.deferredUntil}}</span>
                  {{/if}}
                </a>
              {{else}}
                <a
                  href={{mention.url}}
                  class="mention-open"
                  target="_blank"
                  rel="noopener noreferrer"
                  data-test-mention-github
                >
                  <span class="mention-head">{{mention.author}}
                    on
                    {{mention.repo}}#{{mention.number}}</span>
                  <span
                    class="mention-body"
                    data-test-mention-body
                  >{{mention.body}}</span>
                  <span class="mention-off">{{if
                      mention.building
                      "card being built"
                      "not on the board"
                    }}
                    · opens on GitHub</span>
                  {{#if mention.deferredUntil}}
                    <span
                      class="mention-deferred"
                      data-test-mention-deferred
                    >deferred {{mention.deferredUntil}}</span>
                  {{/if}}
                </a>
              {{/if}}
              <button
                type="button"
                class="mention-more"
                aria-label="Actions for this mention"
                aria-haspopup="menu"
                aria-expanded={{if (this.isActing mention) "true" "false"}}
                data-test-mention-more
                {{on "click" (fn this.toggleActions mention)}}
              >▾</button>
              {{#if (this.isActing mention)}}
                <div
                  class="mention-actions"
                  popover="manual"
                  role="menu"
                  data-test-mention-actions
                  {{this.shown}}
                >
                  <button
                    type="button"
                    class="mention-action"
                    role="menuitem"
                    disabled={{if mention.opensOnTheBoard false true}}
                    data-test-mention-action="context"
                    {{on "click" (fn this.go mention)}}
                  >See in context</button>
                  <a
                    href={{mention.url}}
                    class="mention-action"
                    role="menuitem"
                    target="_blank"
                    rel="noopener noreferrer"
                    data-test-mention-action="github"
                    {{on "click" this.leaveActions}}
                  >See on GitHub</a>
                  {{#if mention.deferredUntil}}
                    <button
                      type="button"
                      class="mention-action"
                      role="menuitem"
                      data-test-mention-action="stop-deferring"
                      {{on "click" (fn this.stopDeferring mention)}}
                    >Stop deferring</button>
                  {{else}}
                    <button
                      type="button"
                      class="mention-action"
                      role="menuitem"
                      data-test-mention-action="defer"
                      {{on "click" (fn this.defer mention)}}
                    >Defer…</button>
                  {{/if}}
                  <button
                    type="button"
                    class="mention-action"
                    role="menuitem"
                    data-test-mention-action="dismiss"
                    {{on "click" (fn this.dismiss mention)}}
                  >Dismiss</button>
                </div>
              {{/if}}
            </div>
          {{else}}
            <span class="mention-none">No mentions waiting on you.</span>
          {{/each}}
        </div>
      {{/if}}
      {{#if this.deferring}}
        <DeferMention @mention={{this.deferring}} @close={{this.stopDialog}} />
      {{/if}}
    </span>
  </template>
}
