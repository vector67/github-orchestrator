import DOMPurify from 'dompurify';
import MarkdownIt from 'markdown-it';
import type { StateInline } from 'markdown-it';
import type { Emoji } from 'frontend/data/api';
import { glyphOf } from 'frontend/data/emoji';
import {
  highlightedHtml,
  keepingClasses,
  knownLanguage,
  MOST_HIGHLIGHTED,
  remembered,
} from 'frontend/data/highlight';

const SAFE_HREF = /^https?:\/\//i;

const DRAWN_TAGS = [
  'p',
  'br',
  'strong',
  'em',
  'code',
  'pre',
  'blockquote',
  'ul',
  'ol',
  'li',
  'h1',
  'h2',
  'h3',
  'h4',
  'h5',
  'h6',
  's',
  'del',
  'hr',
  'a',
  'table',
  'thead',
  'tbody',
  'tr',
  'th',
  'td',
  'span',
];

const SUMMARY_TAGS = ['details', 'summary', 'figure'];

const EMOJI_TAGS = ['img'];

const EMOJI_ATTRIBUTES = ['src', 'alt'];

const EMOJI_TYPED = /^:([\w+-]+):/;

interface Named {
  emojis?: Map<string, Emoji>;
}

function emojiTyped(state: StateInline, silent: boolean): boolean {
  if (state.src[state.pos] !== ':') return false;
  const typed = EMOJI_TYPED.exec(state.src.slice(state.pos));
  const emoji = typed?.[1] && (state.env as Named).emojis?.get(typed[1]);
  if (!typed || !emoji) return false;
  if (!silent) state.push('emoji', '', 0).meta = { emoji };
  state.pos += typed[0].length;
  return true;
}

function parser(breaks: boolean, html = false): ReturnType<typeof MarkdownIt> {
  const made = new MarkdownIt('default', {
    html,
    linkify: true,
    breaks,
    highlight: (code, info) => {
      const language = knownLanguage(info.trim().split(/\s+/)[0] ?? '');
      if (!language || code.length > MOST_HIGHLIGHTED) return '';
      return highlightedHtml(code, language);
    },
  });
  made.validateLink = (url) => SAFE_HREF.test(url.trim());
  made.renderer.rules.image = (tokens, at) => {
    const image = tokens[at];
    const source = String(image?.attrGet('src') ?? '');
    const words = made.utils.escapeHtml(image?.content || source);
    if (!SAFE_HREF.test(source)) return words;
    return `<a href="${made.utils.escapeHtml(source)}">${words}</a>`;
  };
  return made;
}

const COMMENTS = parser(true);

COMMENTS.inline.ruler.push('emoji', emojiTyped);

COMMENTS.renderer.rules.emoji = (tokens, at) => {
  const emoji = tokens[at]?.meta?.['emoji'] as Emoji;
  const glyph = glyphOf(emoji);
  if (glyph) return glyph;
  const name = COMMENTS.utils.escapeHtml(`:${emoji.name}:`);
  return `<img src="${COMMENTS.utils.escapeHtml(emoji.picture)}" alt="${name}">`;
};

const NOTES = parser(false);

const SUMMARIES = parser(true, true);

const fence = SUMMARIES.renderer.rules.fence;

SUMMARIES.renderer.rules.fence = (tokens, at, options, env, self) => {
  const block = tokens[at];
  if (block?.info.trim() !== 'mermaid' || !fence)
    return fence?.(tokens, at, options, env, self) ?? '';
  return `<figure><pre><code>${SUMMARIES.utils.escapeHtml(block.content)}</code></pre></figure>`;
};

const SANITISER = DOMPurify(window);

SANITISER.addHook('uponSanitizeAttribute', keepingClasses(true));

SANITISER.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName !== 'A' || !node.hasAttribute('href')) return;
  node.setAttribute('target', '_blank');
  node.setAttribute('rel', 'noopener noreferrer');
});

function copied(
  draw: (text: string) => DocumentFragment,
): (text: string) => DocumentFragment {
  const drawn = remembered(draw);
  return (text) => drawn(text).cloneNode(true) as DocumentFragment;
}

const DRAWN_WITH = new WeakMap<Emoji[], (text: string) => DocumentFragment>();

export function markdownWith(
  emojis: Emoji[],
): (text: string) => DocumentFragment {
  let drawing = DRAWN_WITH.get(emojis);
  if (!drawing) {
    const named = {
      emojis: new Map(emojis.map((emoji) => [emoji.name, emoji])),
    };
    drawing = copied((text) =>
      sanitised(COMMENTS.render(text, named), EMOJI_TAGS, EMOJI_ATTRIBUTES),
    );
    DRAWN_WITH.set(emojis, drawing);
  }
  return drawing;
}

const NOTES_DRAWN = copied((text) => sanitised(NOTES.render(text)));

export function notesOf(text: string): DocumentFragment {
  return NOTES_DRAWN(text);
}

const SUMMARIES_DRAWN = copied((text) =>
  sanitised(SUMMARIES.render(text), SUMMARY_TAGS),
);

export function summaryOf(text: string): DocumentFragment {
  return SUMMARIES_DRAWN(text);
}

function sanitised(
  html: string,
  extraTags: string[] = [],
  extraAttributes: string[] = [],
): DocumentFragment {
  return SANITISER.sanitize(html, {
    ALLOWED_TAGS: [...DRAWN_TAGS, ...extraTags],
    ALLOWED_ATTR: ['href', 'class', 'start', ...extraAttributes],
    ALLOWED_URI_REGEXP: SAFE_HREF,
    RETURN_DOM_FRAGMENT: true,
  });
}
