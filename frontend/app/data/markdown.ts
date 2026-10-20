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

const SUMMARY_TAGS = ['details', 'summary', 'figure'];

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

export function markdownOf(text: string): DocumentFragment {
  return sanitised(COMMENTS.render(text));
}

export function notesOf(text: string): DocumentFragment {
  return sanitised(NOTES.render(text));
}

export function summaryOf(text: string): DocumentFragment {
  return sanitised(SUMMARIES.render(text), SUMMARY_TAGS);
}

function sanitised(html: string, extraTags: string[] = []): DocumentFragment {
  return SANITISER.sanitize(html, {
    ALLOWED_TAGS: [...DRAWN_TAGS, ...extraTags],
    ALLOWED_ATTR: ['href', 'class', 'start'],
    ALLOWED_URI_REGEXP: SAFE_HREF,
    RETURN_DOM_FRAGMENT: true,
  });
}
