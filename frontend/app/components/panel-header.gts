import Component from '@glimmer/component';
import { service } from '@ember/service';
import { squareTitleOf } from 'frontend/data/groups';
import navigates from 'frontend/modifiers/navigates';
import type { Panel } from 'frontend/data/panel';
import { BOARD_ONLY } from 'frontend/data/thread';
import type BoardKeysService from 'frontend/services/board-keys';

export interface PanelHeaderSignature {
  Element: HTMLElement;
  Args: { panel: Panel };
}

export default class PanelHeader extends Component<PanelHeaderSignature> {
  @service('board-keys') declare boardKeys: BoardKeysService;

  get nextLabel() {
    return this.args.panel.role === 'reviewer'
      ? 'Next answered →'
      : 'Next ready →';
  }

  hrefOfStep = (by: number): string | undefined => {
    const landing = this.boardKeys.readyStep(by);
    return landing ? this.boardKeys.hrefOf(landing) : undefined;
  };

  get roleLineShown() {
    return Boolean(this.args.panel.started || this.args.panel.role_line);
  }

  <template>
    <header class="panel-head" ...attributes>
      <span
        class="square"
        role="img"
        title={{squareTitleOf @panel.square}}
        aria-label={{squareTitleOf @panel.square}}
        data-square={{@panel.square}}
        data-test-square
      ></span>
      <span class="panel-who">
        <span class="panel-kicker" data-test-kicker>
          <span
            class="kicker-place"
            title={{@panel.kicker_hint}}
          >{{@panel.kicker}}</span>
          {{#if @panel.location}}
            <span class="kicker-sep">·</span>
            <a
              class="anchor-out"
              href={{@panel.url}}
              target="_blank"
              rel="noopener noreferrer"
            >
              <span class="anchor-out-where">{{@panel.location}}</span>
              <svg
                class="anchor-out-icon"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentcolor"
                stroke-width="2.5"
                stroke-linecap="round"
                stroke-linejoin="round"
                aria-hidden="true"
                focusable="false"
                data-test-anchor-out-icon
              >
                <path
                  d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"
                />
                <path d="M15 3h6v6" />
                <path d="M10 14 21 3" />
              </svg>
            </a>
          {{/if}}
        </span>
        {{#if @panel.board_only}}
          <span class="board-only" data-test-board-only>{{BOARD_ONLY}}</span>
        {{/if}}
        <span class="panel-name">
          <span
            class="author"
            data-test-panel-author
          >{{@panel.reviewer_name}}</span>
          {{#if this.roleLineShown}}
            <span class="role-line" data-test-role-line>
              {{#if @panel.started}}
                <time
                  title={{@panel.started_at}}
                  data-test-started
                >{{@panel.started}}</time>
                {{#if @panel.role_line}}·{{/if}}
              {{/if}}
              {{@panel.role_line}}
            </span>
          {{/if}}
        </span>
      </span>
      <span class="panel-walk">
        <a
          href={{this.hrefOfStep -1}}
          class="walk"
          data-test-prev
          {{navigates this.boardKeys.previousReady}}
        >← Prev</a>
        <a
          href={{this.hrefOfStep 1}}
          class="walk"
          data-test-next
          {{navigates this.boardKeys.nextReady}}
        >{{this.nextLabel}}</a>
      </span>
    </header>
  </template>
}
