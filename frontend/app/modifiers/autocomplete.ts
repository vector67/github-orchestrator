import Modifier from 'ember-modifier';
import { registerDestructor } from '@ember/destroyable';
import { service } from '@ember/service';
import type { Emoji, Person } from 'frontend/data/api';
import { emojiNamed, glyphOf, typedAs } from 'frontend/data/emoji';
import { peopleNamed } from 'frontend/data/mention';
import type HereService from 'frontend/services/here';
import type StoreService from 'frontend/services/store';

const EMOJI_TYPED = /(?:^|\s):([\w+-]+)$/;

const PERSON_TYPED = /(?:^|\s)@([\w-]*)$/;

const MIRRORED = [
  'boxSizing',
  'width',
  'paddingTop',
  'paddingRight',
  'paddingBottom',
  'paddingLeft',
  'borderTopWidth',
  'borderRightWidth',
  'borderBottomWidth',
  'borderLeftWidth',
  'fontFamily',
  'fontSize',
  'fontWeight',
  'fontStyle',
  'letterSpacing',
  'lineHeight',
  'tabSize',
  'textTransform',
  'wordSpacing',
] as const;

interface Suggestion {
  shown: (Node | string)[];
  put: string;
}

interface Typed {
  start: number;
  end: number;
  offered: Suggestion[];
  at: number;
}

interface Sources {
  emojis: () => Emoji[];
  people: () => Person[];
}

function pictured(emoji: Emoji): HTMLElement {
  const glyph = glyphOf(emoji);
  if (glyph) {
    const drawn = document.createElement('span');
    drawn.className = 'emoji-glyph';
    drawn.textContent = glyph;
    return drawn;
  }
  const picture = document.createElement('img');
  picture.className = 'emoji-glyph';
  picture.src = emoji.picture;
  picture.alt = '';
  return picture;
}

function named(person: Person): (Node | string)[] {
  if (!person.name) return [`@${person.login}`];
  const name = document.createElement('span');
  name.className = 'suggestion-name';
  name.textContent = person.name;
  return [`@${person.login} `, name];
}

function offeredFor(
  before: string,
  sources: Sources,
): { typed: string; offered: Suggestion[] } | null {
  const emoji = EMOJI_TYPED.exec(before)?.[1];
  if (emoji) {
    const offered = emojiNamed(sources.emojis(), emoji).map((one) => ({
      shown: [pictured(one), ` :${one.name}:`],
      put: typedAs(one),
    }));
    return { typed: emoji, offered };
  }
  const person = PERSON_TYPED.exec(before)?.[1];
  if (person === undefined) return null;
  const offered = peopleNamed(sources.people(), person).map((one) => ({
    shown: named(one),
    put: `@${one.login} `,
  }));
  return { typed: person, offered };
}

function typedAtCaret(
  field: HTMLTextAreaElement,
  sources: Sources,
): Typed | null {
  const end = field.selectionEnd;
  if (field.selectionStart !== end) return null;
  const found = offeredFor(field.value.slice(0, end), sources);
  if (!found?.offered.length) return null;
  const start = end - found.typed.length - 1;
  return { start, end, offered: found.offered, at: 0 };
}

function caretBelow(
  field: HTMLTextAreaElement,
  at: number,
): { left: number; top: number } {
  const style = getComputedStyle(field);
  const mirror = document.createElement('div');
  for (const property of MIRRORED) mirror.style[property] = style[property];
  mirror.style.position = 'absolute';
  mirror.style.visibility = 'hidden';
  mirror.style.whiteSpace = 'pre-wrap';
  mirror.style.overflowWrap = 'break-word';
  mirror.textContent = field.value.slice(0, at);
  const caret = document.createElement('span');
  caret.textContent = '​';
  mirror.append(caret);
  document.body.append(mirror);
  const left = field.offsetLeft + caret.offsetLeft - field.scrollLeft;
  const top =
    field.offsetTop + caret.offsetTop + caret.offsetHeight - field.scrollTop;
  mirror.remove();
  return { left, top };
}

function completing(field: HTMLTextAreaElement, sources: Sources): () => void {
  let typed: Typed | null = null;
  const list = document.createElement('ul');
  list.className = 'suggestions';
  list.setAttribute('role', 'listbox');
  list.dataset['testSuggestions'] = '';

  const close = () => {
    typed = null;
    list.remove();
  };

  const draw = (shown: Typed) => {
    list.replaceChildren(
      ...shown.offered.map((suggestion, index) => {
        const option = document.createElement('li');
        option.className = 'suggestion';
        option.setAttribute('role', 'option');
        option.setAttribute('aria-selected', String(index === shown.at));
        option.dataset['testSuggestion'] = '';
        option.append(...suggestion.shown);
        option.addEventListener('mousedown', (event) => event.preventDefault());
        option.addEventListener('click', () => put(shown, suggestion));
        return option;
      }),
    );
    const caret = caretBelow(field, shown.start);
    list.style.left = `${caret.left}px`;
    list.style.top = `${caret.top}px`;
    if (!list.isConnected) field.after(list);
  };

  const put = (shown: Typed, suggestion: Suggestion) => {
    close();
    field.focus();
    field.setSelectionRange(shown.start, shown.end);
    document.execCommand('insertText', false, suggestion.put);
  };

  const look = () => {
    typed = typedAtCaret(field, sources);
    if (typed) draw(typed);
    else close();
  };

  const press = (event: KeyboardEvent) => {
    const shown = typed;
    if (!shown || event.isComposing) return;
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    const moves: Record<string, number> = { ArrowDown: 1, ArrowUp: -1 };
    const move = moves[event.key];
    const chosen = shown.offered[shown.at];
    if (move !== undefined) {
      const count = shown.offered.length;
      typed = { ...shown, at: (shown.at + move + count) % count };
      draw(typed);
    } else if (
      (event.key === 'Tab' && !event.shiftKey) ||
      event.key === 'Enter'
    ) {
      if (chosen) put(shown, chosen);
    } else if (event.key === 'Escape') {
      close();
    } else {
      return;
    }
    event.preventDefault();
    event.stopImmediatePropagation();
  };

  field.addEventListener('input', look);
  field.addEventListener('keydown', press, { capture: true });
  field.addEventListener('blur', close);
  return () => {
    close();
    field.removeEventListener('input', look);
    field.removeEventListener('keydown', press, { capture: true });
    field.removeEventListener('blur', close);
  };
}

interface AutocompleteSignature {
  Element: HTMLTextAreaElement;
}

export default class Autocomplete extends Modifier<AutocompleteSignature> {
  @service declare store: StoreService;
  @service declare here: HereService;

  private completing = false;

  modify(field: HTMLTextAreaElement): void {
    if (this.completing) return;
    this.completing = true;
    const pr = this.here.at;
    if (this.here.pr) this.store.readMentionable(pr);
    registerDestructor(
      this,
      completing(field, {
        emojis: () => this.store.emojis,
        people: () => (this.here.pr ? this.store.mentionable(pr) : []),
      }),
    );
  }
}
