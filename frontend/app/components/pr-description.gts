import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { service } from '@ember/service';
import { fn } from '@ember/helper';
import { on } from '@ember/modifier';
import { waitForPromise } from '@ember/test-waiters';
import CommentBody from 'frontend/components/comment-body';
import sharesHeight from 'frontend/modifiers/shares-height';
import type HereService from 'frontend/services/here';
import type StoreService from 'frontend/services/store';

type Pane = 'write' | 'preview';

interface OnGithub {
  title: string;
  body: string;
}

interface PrDescriptionSignature {
  Args: {
    title: string | null;
    body: string | null;
    unchecked: boolean;
    shown: boolean;
    covered: boolean;
    onShow: () => void;
    onHide: () => void;
  };
  Blocks: { default: [] };
}

export default class PrDescription extends Component<PrDescriptionSignature> {
  @service declare here: HereService;
  @service declare store: StoreService;

  @tracked editing = false;
  @tracked title = '';
  @tracked text = '';
  @tracked pane: Pane = 'write';
  @tracked moved: OnGithub | null = null;
  @tracked refused: string | null = null;
  @tracked saving = false;
  private startedFrom: OnGithub = { title: '', body: '' };

  isPane = (pane: Pane): boolean => this.pane === pane;

  get offersShow(): boolean {
    return !this.args.shown || this.args.covered;
  }

  get unsaveable(): boolean {
    return this.saving || !this.title.trim();
  }

  edit = (): void => {
    this.title = this.args.title ?? '';
    this.text = this.args.body ?? '';
    this.startedFrom = {
      title: this.args.title ?? '',
      body: this.args.body ?? '',
    };
    this.pane = 'write';
    this.moved = null;
    this.refused = null;
    this.editing = true;
  };

  check = (): void => {
    if (!this.args.unchecked || this.args.body === null) return;
    void waitForPromise(
      this.store.checkDescription(this.here.at, this.args.body),
    );
  };

  cancel = (): void => {
    this.editing = false;
  };

  show = (pane: Pane): void => {
    this.pane = pane;
  };

  typeTitle = (event: Event): void => {
    this.title = (event.target as HTMLInputElement).value;
  };

  typeText = (event: Event): void => {
    this.text = (event.target as HTMLTextAreaElement).value;
  };

  save = (): void => {
    void waitForPromise(this.saveFrom(this.startedFrom));
  };

  saveOver = (): void => {
    void waitForPromise(this.saveFrom(this.moved ?? this.startedFrom));
  };

  startAgain = (): void => {
    if (this.moved) {
      this.title = this.moved.title;
      this.text = this.moved.body;
      this.startedFrom = this.moved;
    }
    this.moved = null;
    this.pane = 'write';
  };

  private async saveFrom(startedFrom: OnGithub): Promise<void> {
    this.saving = true;
    this.refused = null;
    const taken = await this.store.saveDescription(this.here.at, {
      title: this.title,
      body: this.text,
      title_started_from: startedFrom.title,
      started_from: startedFrom.body,
    });
    this.saving = false;
    if (!taken.done) {
      this.refused = taken.why;
      return;
    }
    if (!taken.body.saved) {
      this.moved = {
        title: taken.body.title_on_github,
        body: taken.body.on_github,
      };
      return;
    }
    this.moved = null;
    this.editing = false;
  }

  <template>
    <header
      class="summary-pr"
      data-test-summary-pr
      {{sharesHeight "--summary-pr-height"}}
    >
      {{#if this.editing}}
        <input
          type="text"
          class="summary-pr-title-field"
          aria-label="title"
          value={{this.title}}
          data-test-description-title
          {{on "input" this.typeTitle}}
        />
      {{else}}
        <div class="summary-pr-title-row" data-test-summary-title-row>
          <h2 class="summary-pr-title" data-test-summary-title>
            {{@title}}
          </h2>
          {{#if this.offersShow}}
            <button
              type="button"
              class="btn summary-pr-show"
              data-test-description-show
              {{on "click" @onShow}}
            >Show description</button>
          {{/if}}
        </div>
      {{/if}}
      {{yield}}
    </header>
    <div class="summary-pr-body" data-test-summary-pr-body>
      {{#if this.editing}}
        <div class="description-editor" data-test-description-editor>
          <div class="defer-tabs" role="tablist">
            <button
              type="button"
              class="tab"
              role="tab"
              aria-selected={{if (this.isPane "write") "true" "false"}}
              data-test-description-tab="write"
              {{on "click" (fn this.show "write")}}
            >Write</button>
            <button
              type="button"
              class="tab"
              role="tab"
              aria-selected={{if (this.isPane "preview") "true" "false"}}
              data-test-description-tab="preview"
              {{on "click" (fn this.show "preview")}}
            >Preview</button>
          </div>
          {{#if (this.isPane "write")}}
            <textarea
              class="description-text"
              aria-label="description"
              rows="12"
              value={{this.text}}
              data-test-description-text
              {{on "input" this.typeText}}
              {{on "focus" this.check}}
            ></textarea>
          {{else}}
            <CommentBody
              class="description-preview"
              @body={{this.text}}
              data-test-description-preview
            />
          {{/if}}
          {{#if this.moved}}
            <div class="description-moved" data-test-description-moved>
              <p class="said" data-refused="true">The title or description
                changed on GitHub since you opened it. Yours is in the box
                above; GitHub’s is below.</p>
              <h3
                class="description-title-on-github"
                data-test-description-title-on-github
              >{{this.moved.title}}</h3>
              <CommentBody
                class="description-on-github"
                @body={{this.moved.body}}
                data-test-description-on-github
              />
              <div class="dialog-actions">
                <button
                  type="button"
                  class="primary"
                  disabled={{this.saving}}
                  data-test-description-save-over
                  {{on "click" this.saveOver}}
                >Save over GitHub’s</button>
                <button
                  type="button"
                  class="ghost"
                  data-test-description-start-again
                  {{on "click" this.startAgain}}
                >Start again from GitHub’s</button>
              </div>
            </div>
          {{/if}}
          {{#if this.refused}}
            <p
              class="said"
              data-refused="true"
              data-test-description-refused
            >{{this.refused}}</p>
          {{/if}}
          <div class="dialog-actions">
            {{#unless this.moved}}
              <button
                type="button"
                class="primary"
                disabled={{this.unsaveable}}
                data-test-description-save
                {{on "click" this.save}}
              >Save</button>
            {{/unless}}
            <button
              type="button"
              class="ghost"
              data-test-description-cancel
              {{on "click" this.cancel}}
            >Cancel</button>
          </div>
        </div>
      {{else if @shown}}
        {{#if @body}}
          <CommentBody
            class="summary-pr-description"
            @body={{@body}}
            data-test-description
          />
        {{/if}}
        <div class="summary-pr-actions">
          <button
            type="button"
            class="btn"
            data-test-description-edit
            {{on "click" this.edit}}
          >Edit</button>
          <button
            type="button"
            class="btn"
            data-test-description-hide
            {{on "click" @onHide}}
          >Hide</button>
        </div>
      {{/if}}
    </div>
  </template>
}
