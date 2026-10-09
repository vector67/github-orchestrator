import DOMPurify from 'dompurify';
import MarkdownIt from 'markdown-it';
import {
  highlightedHtml,
  keepingClasses,
  knownLanguage,
  MOST_HIGHLIGHTED,
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

function parser(breaks: boolean): ReturnType<typeof MarkdownIt> {
  const made = new MarkdownIt('default', {
    html: false,
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

const NOTES = parser(false);

const SANITISER = DOMPurify(window);

SANITISER.addHook('uponSanitizeAttribute', keepingClasses(true));

SANITISER.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName !== 'A' || !node.hasAttribute('href')) return;
  node.setAttribute('target', '_blank');
  node.setAttribute('rel', 'noopener noreferrer');
});

export function markdownOf(text: string): DocumentFragment {
  return sanitised(COMMENTS.render(text));
}

export function notesOf(text: string): DocumentFragment {
  return sanitised(NOTES.render(text));
}

function sanitised(html: string): DocumentFragment {
  return SANITISER.sanitize(html, {
    ALLOWED_TAGS: DRAWN_TAGS,
    ALLOWED_ATTR: ['href', 'class', 'start'],
    ALLOWED_URI_REGEXP: SAFE_HREF,
    RETURN_DOM_FRAGMENT: true,
  });
}
