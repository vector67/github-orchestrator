import type { Emoji } from 'frontend/data/api';

const OFFERED = 5;

const UNICODE = /\/unicode\/([0-9a-f-]+)\.png/;

const KEYCAP = '⃣';

const EMOJI_FORM = '️';

const DRAWN_AS_EMOJI = /^\p{Emoji_Presentation}$/u;

export function glyphOf(emoji: Emoji): string | null {
  const code = UNICODE.exec(emoji.picture)?.[1];
  if (!code) return null;
  const glyph = String.fromCodePoint(
    ...code.split('-').map((point) => parseInt(point, 16)),
  );
  if (glyph.endsWith(KEYCAP) && !glyph.includes(EMOJI_FORM)) {
    return `${glyph.slice(0, -1)}${EMOJI_FORM}${KEYCAP}`;
  }
  if ([...glyph].length === 1 && !DRAWN_AS_EMOJI.test(glyph)) {
    return `${glyph}${EMOJI_FORM}`;
  }
  return glyph;
}

export function typedAs(emoji: Emoji): string {
  return glyphOf(emoji) ?? `:${emoji.name}:`;
}

export function emojiNamed(emojis: Emoji[], typed: string): Emoji[] {
  const query = typed.toLowerCase();
  const starting = emojis.filter((one) => one.name.startsWith(query));
  const containing = emojis.filter(
    (one) => !one.name.startsWith(query) && one.name.includes(query),
  );
  return [...starting, ...containing].slice(0, OFFERED);
}
