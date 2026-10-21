import Modifier from 'ember-modifier';
import { registerDestructor } from '@ember/destroyable';
import { service } from '@ember/service';
import type { Emoji } from 'frontend/data/api';
import { emojiNamed, glyphOf, typedAs } from 'frontend/data/emoji';
import type StoreService from 'frontend/services/store';

const TYPED = /(?:^|\s):([\w+-]+)$/;

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

interface Typed {
  start: number;
  end: number;
  offered: Emoji[];
  at: number;
}

function typedAtCaret(
  field: HTMLTextAreaElement,
  emojis: Emoji[],
): Typed | null {
  const end = field.selectionEnd;
  if (field.selectionStart !== end) return null;
  const match = TYPED.exec(field.value.slice(0, end));
  if (!match?.[1]) return null;
  const offered = emojiNamed(emojis, match[1]);
  if (!offered.length) return null;
  return { start: end - match[1].length - 1, end, offered, at: 0 };
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

function completing(
  field: HTMLTextAreaElement,
  emojis: () => Emoji[],
): () => void {
  let typed: Typed | null = null;
  const list = document.createElement('ul');
  list.className = 'emoji-suggestions';
  list.setAttribute('role', 'listbox');
  list.dataset['testEmojiSuggestions'] = '';

  const close = () => {
    typed = null;
    list.remove();
  };

  const draw = (shown: Typed) => {
    list.replaceChildren(
      ...shown.offered.map((emoji, index) => {
        const option = document.createElement('li');
        option.className = 'emoji-option';
        option.setAttribute('role', 'option');
        option.setAttribute('aria-selected', String(index === shown.at));
        option.dataset['testEmojiOption'] = '';
        option.append(pictured(emoji), ` :${emoji.name}:`);
        option.addEventListener('mousedown', (event) => event.preventDefault());
        option.addEventListener('click', () => put(shown, emoji));
        return option;
      }),
    );
    const caret = caretBelow(field, shown.start);
    list.style.left = `${caret.left}px`;
    list.style.top = `${caret.top}px`;
    if (!list.isConnected) field.after(list);
  };

  const put = (shown: Typed, emoji: Emoji) => {
    close();
    field.focus();
    field.setSelectionRange(shown.start, shown.end);
    document.execCommand('insertText', false, typedAs(emoji));
  };

  const look = () => {
    typed = typedAtCaret(field, emojis());
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

interface EmojiCompleteSignature {
  Element: HTMLTextAreaElement;
}

export default class EmojiComplete extends Modifier<EmojiCompleteSignature> {
  @service declare store: StoreService;

  private completing = false;

  modify(field: HTMLTextAreaElement): void {
    if (this.completing) return;
    this.completing = true;
    registerDestructor(
      this,
      completing(field, () => this.store.emojis),
    );
  }
}
