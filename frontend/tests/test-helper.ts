import Application from 'frontend/app';
import config from 'frontend/config/environment';
import * as QUnit from 'qunit';
import { setApplication } from '@ember/test-helpers';
import { setup } from 'qunit-dom';
import { setupEmberOnerrorValidation } from 'ember-qunit';
import {
  start as startEmberExam,
  type EmberExamStartOptions,
} from 'ember-exam/addon-test-support';
import { WEIGHTS } from 'frontend/tests/partition-weights';

type Modules = Record<string, () => Promise<unknown>>;

export async function start(
  options: EmberExamStartOptions & { availableModules: Modules },
) {
  document.documentElement.dataset['still'] = '';
  setApplication(Application.create(config.APP));

  setup(QUnit.assert);
  setupEmberOnerrorValidation();

  const params = new URLSearchParams(location.search);
  const modules = options.availableModules;
  if (params.has('weigh')) await weigh(modules);
  await startEmberExam({
    ...options,
    availableModules: balanced(modules, Number(params.get('split') ?? 1)),
  });
}

function balanced(modules: Modules, split: number): Modules {
  const keys = Object.keys(modules);
  if (split <= 1) return modules;
  const known = Object.values(WEIGHTS).sort((a, b) => a - b);
  const median = known[Math.floor(known.length / 2)] ?? 1;
  const weightOf = (key: string) => WEIGHTS[key] ?? median;
  const groups = Array.from({ length: split }, (_, index) => ({
    keys: [] as string[],
    total: 0,
    room: Math.ceil((keys.length - index) / split),
  }));
  for (const key of [...keys].sort((a, b) => weightOf(b) - weightOf(a))) {
    const lightest = groups
      .filter((group) => group.keys.length < group.room)
      .reduce((a, b) => (b.total < a.total ? b : a));
    lightest.keys.push(key);
    lightest.total += weightOf(key);
  }
  const roundRobin = keys.map(
    (_, at) => groups[at % split]!.keys[Math.floor(at / split)]!,
  );
  return Object.fromEntries(roundRobin.map((key) => [key, modules[key]!]));
}

function registered(): { name: string }[] {
  return (QUnit.config as typeof QUnit.config & { modules: { name: string }[] })
    .modules;
}

async function weigh(modules: Modules): Promise<void> {
  const fileOf = new Map<string, string>();
  for (const [key, load] of Object.entries(modules)) {
    const before = registered().length;
    await load();
    for (const one of registered().slice(before)) {
      fileOf.set(one.name, key);
    }
  }
  const weights: Record<string, number> = {};
  QUnit.moduleDone(({ name, runtime }) => {
    const key = fileOf.get(name);
    if (key) weights[key] = (weights[key] ?? 0) + runtime;
  });
  QUnit.module('partition weights', function () {
    QUnit.test(
      'are printed for scripts/weigh-partitions.mjs',
      function (assert) {
        const rounded = Object.fromEntries(
          Object.entries(weights).map(([key, ms]) => [key, Math.round(ms)]),
        );
        console.log(`partition-weights ${JSON.stringify(rounded)}`);
        assert.ok(Object.keys(rounded).length > 0);
      },
    );
  });
}
