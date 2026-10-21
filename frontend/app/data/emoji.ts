import { gemoji } from 'gemoji';

export interface Emoji {
  glyph: string;
  name: string;
}

const OFFERED = 5;

const NAMED: Emoji[] = gemoji.flatMap((one) =>
  one.names.map((name) => ({ glyph: one.emoji, name })),
);

export function emojiNamed(typed: string): Emoji[] {
  const query = typed.toLowerCase();
  const starting = NAMED.filter((one) => one.name.startsWith(query));
  const containing = NAMED.filter(
    (one) => !one.name.startsWith(query) && one.name.includes(query),
  );
  return [...starting, ...containing].slice(0, OFFERED);
}
