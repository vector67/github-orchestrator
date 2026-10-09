import DOMPurify from 'dompurify';
import hljs from 'highlight.js/lib/common';

const TOKENS = DOMPurify(window);

const TOKEN = /^hljs(-[\w-]+)?$/;

const SCOPE = /^[a-z]+_+$/;

const LANGUAGE = /^language-(.+)$/;

export const MOST_HIGHLIGHTED = 64 * 1024;

function spoken(one: string): boolean {
  const named = LANGUAGE.exec(one)?.[1];
  return named !== undefined && knownLanguage(named) !== null;
}

export function classesKept(
  element: Element,
  value: string,
  languages: boolean,
): string[] {
  const named = value.split(/\s+/).filter(Boolean);
  if (element.tagName === 'SPAN') {
    if (!named.some((one) => TOKEN.test(one))) return [];
    return named.filter((one) => TOKEN.test(one) || SCOPE.test(one));
  }
  if (element.tagName === 'CODE' && languages) return named.filter(spoken);
  return [];
}

export function keepingClasses(languages: boolean) {
  return (
    element: Element,
    data: { attrName: string; attrValue: string; keepAttr: boolean },
  ): void => {
    if (data.attrName !== 'class') return;
    const kept = classesKept(element, data.attrValue, languages);
    data.attrValue = kept.join(' ');
    data.keepAttr = kept.length > 0;
  };
}

TOKENS.addHook('uponSanitizeAttribute', keepingClasses(false));

function tokensOf(html: string): DocumentFragment {
  return TOKENS.sanitize(html, {
    ALLOWED_TAGS: ['span'],
    ALLOWED_ATTR: ['class'],
    RETURN_DOM_FRAGMENT: true,
  });
}

export function languageOf(path: string): string | null {
  const name = path.split('/').at(-1) ?? '';
  const dot = name.lastIndexOf('.');
  if (dot <= 0) return null;
  return knownLanguage(name.slice(dot + 1).toLowerCase());
}

export function knownLanguage(name: string): string | null {
  return name && hljs.getLanguage(name) ? name : null;
}

export function highlightedHtml(code: string, language: string): string {
  return hljs.highlight(code, { language, ignoreIllegals: true }).value;
}

function highlighted(code: string, language: string | null): DocumentFragment {
  if (!language || !knownLanguage(language) || code.length > MOST_HIGHLIGHTED) {
    const plain = document.createDocumentFragment();
    plain.append(code);
    return plain;
  }
  return tokensOf(highlightedHtml(code, language));
}

export type Highlighter = (code: string) => DocumentFragment;

function splitIntoLines(drawn: DocumentFragment): DocumentFragment[] {
  const lines: DocumentFragment[] = [];
  const open: Element[] = [];
  let into: Node = document.createDocumentFragment();
  const startLine = () => {
    const line = document.createDocumentFragment();
    lines.push(line);
    into = open.reduce<Node>(
      (parent, element) => parent.appendChild(element.cloneNode(false)),
      line,
    );
  };
  const walk = (node: Node) => {
    if (node.nodeType === Node.TEXT_NODE) {
      (node.textContent ?? '').split('\n').forEach((part, at) => {
        if (at > 0) startLine();
        if (part) into.appendChild(document.createTextNode(part));
      });
      return;
    }
    if (!(node instanceof Element)) return;
    into = into.appendChild(node.cloneNode(false));
    open.push(node);
    node.childNodes.forEach(walk);
    open.pop();
    into = into.parentNode!;
  };
  startLine();
  drawn.childNodes.forEach(walk);
  return lines;
}

export function highlightedLines(
  lines: string[],
  language: string | null,
): Highlighter[] {
  return splitIntoLines(highlighted(lines.join('\n'), language)).map(
    (drawn) => () => drawn.cloneNode(true) as DocumentFragment,
  );
}

const HIGHLIGHTERS = new Map<string | null, Highlighter>();

export function highlighterOf(language?: string | null): Highlighter {
  const named = language ?? null;
  let found = HIGHLIGHTERS.get(named);
  if (!found) {
    found = (code) => highlighted(code, named);
    HIGHLIGHTERS.set(named, found);
  }
  return found;
}
