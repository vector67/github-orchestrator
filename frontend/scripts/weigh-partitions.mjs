import { spawnSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';

const run = spawnSync(
  'npx',
  ['testem', 'ci', '-f', 'testem.cjs', '--port', '0'],
  {
    env: { ...process.env, TEST_WEIGH: '1' },
    encoding: 'utf8',
    maxBuffer: 64 * 1024 * 1024,
  },
);
const logged = run.stdout
  .split('\n')
  .map((line) => line.trim())
  .find((line) => line.includes('partition-weights {'));
if (run.status !== 0 || !logged) {
  throw new Error(
    `the weighing run printed no weights:\n${run.stdout}${run.stderr}`,
  );
}
const weights = JSON.parse(
  JSON.parse(logged).text.replace('partition-weights ', ''),
);
const lines = Object.keys(weights)
  .sort()
  .map((key) => `  '${key}': ${weights[key]},`);
writeFileSync(
  'tests/partition-weights.ts',
  `export const WEIGHTS: Record<string, number> = {\n${lines.join('\n')}\n};\n`,
);
