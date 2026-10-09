export type Where = 'here' | 'shown' | 'terminal';

export interface GitCommand {
  keys: string;
  display: string;
  where: Where;
  takesNumber: boolean;
}

function command(
  keys: string,
  display: string,
  where: Where,
  takesNumber = false,
): GitCommand {
  return { keys, display, where, takesNumber };
}

export const REBASE_ON_MAIN = command(
  'r',
  'rebase-on-main in an agent session',
  'terminal',
);

export const GIT_COMMANDS: GitCommand[] = [
  command('f', 'git push --force-with-lease', 'here'),
  command('p', 'git push', 'here'),
  command('pra', 'git pull --rebase --autostash', 'here'),
  command('s', 'git status', 'here'),
  command('l', 'git log', 'shown'),
  command('d', 'git diff HEAD', 'shown'),
  command('a', 'git add -p', 'terminal'),
  command('c', 'git commit', 'terminal'),
  command('i', 'git rebase -i HEAD~<N>', 'terminal', true),
  REBASE_ON_MAIN,
];

export const WHERE_WORDS: Record<Where, string> = {
  here: 'runs here',
  shown: 'shown',
  terminal: 'Terminal tab',
};

export const FORCE_PUSH = 'f';

const DIGITS = /^\d+$/;

function numberPart(one: GitCommand, buffer: string): string | null {
  if (!one.takesNumber || !buffer.startsWith(one.keys)) return null;
  const digits = buffer.slice(one.keys.length);
  return DIGITS.test(digits) ? digits : null;
}

export function resolve(buffer: string): GitCommand | null {
  return (
    GIT_COMMANDS.find((one) =>
      one.takesNumber ? numberPart(one, buffer) !== null : buffer === one.keys,
    ) ?? null
  );
}

export function isValidPrefix(buffer: string): boolean {
  return GIT_COMMANDS.some(
    (one) => one.keys.startsWith(buffer) || numberPart(one, buffer) !== null,
  );
}

export function reachable(one: GitCommand, buffer: string): boolean {
  return one.keys.startsWith(buffer) || resolve(buffer) === one;
}

export function lineOf(one: GitCommand, buffer: string): string {
  const digits = numberPart(one, buffer);
  return digits === null ? one.display : one.display.replace('<N>', digits);
}

export function keysLabel(one: GitCommand): string {
  return one.takesNumber ? `${one.keys}<N>` : one.keys;
}
