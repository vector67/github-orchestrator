export interface NamedTheme {
  key: string;
  name: string;
}

export const LIGHT_THEMES: NamedTheme[] = [
  { key: 'default-light', name: 'Default' },
  { key: 'solarized-light', name: 'Solarized Light' },
  { key: 'tokyo-night-day', name: 'Tokyo Night Day' },
  { key: 'one-light', name: 'One Light' },
  { key: 'gruvbox-light', name: 'Gruvbox Light' },
  { key: 'catppuccin-latte', name: 'Catppuccin Latte' },
];

export const DARK_THEMES: NamedTheme[] = [
  { key: 'default-dark', name: 'Default' },
  { key: 'solarized-dark', name: 'Solarized Dark' },
  { key: 'tokyo-night', name: 'Tokyo Night' },
  { key: 'monokai', name: 'Monokai' },
  { key: 'one-dark', name: 'One Dark' },
  { key: 'gruvbox-dark', name: 'Gruvbox Dark' },
  { key: 'catppuccin-mocha', name: 'Catppuccin Mocha' },
  { key: 'dracula', name: 'Dracula' },
  { key: 'nord', name: 'Nord' },
];

const ANSI = [
  'black',
  'red',
  'green',
  'yellow',
  'blue',
  'magenta',
  'cyan',
  'white',
  'brightBlack',
  'brightRed',
  'brightGreen',
  'brightYellow',
  'brightBlue',
  'brightMagenta',
  'brightCyan',
  'brightWhite',
] as const;

export interface Scheme {
  ground: string;
  text: string;
  cursor: string;
  selection: string;
  ansi: Partial<Record<(typeof ANSI)[number], string>>;
}

export function schemeOf(key: string): Scheme {
  const style = getComputedStyle(document.documentElement);
  const read = (slot: string) =>
    style.getPropertyValue(`--tty-${key}-${slot}`).trim();
  const ansi: Scheme['ansi'] = {};
  ANSI.forEach((name, index) => {
    const colour = read(`ansi-${index}`);
    if (colour) ansi[name] = colour;
  });
  return {
    ground: read('ground'),
    text: read('text'),
    cursor: read('cursor'),
    selection: read('selection'),
    ansi,
  };
}
