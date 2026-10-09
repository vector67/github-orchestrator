import { settled } from '@ember/test-helpers';

interface Timer {
  id: number;
  every: number;
  due: number;
  run: () => void;
}

const FIRST_ID = 1_000_000_000;

export class FakeClock {
  now = Date.now();
  private timers: Timer[] = [];
  private nextId = FIRST_ID;

  setInterval = (run: () => void, every = 0): number => {
    const id = (this.nextId += 1);
    this.timers.push({ id, every, due: this.now + every, run });
    return id;
  };

  clearInterval = (id?: number): void => {
    this.timers = this.timers.filter((one) => one.id !== id);
  };

  async tick(ms: number): Promise<void> {
    this.now += ms;
    const due = this.timers
      .filter((one) => one.due <= this.now)
      .sort((one, other) => one.due - other.due);
    for (const timer of due) {
      timer.due = this.now + timer.every;
      timer.run();
    }
    await settled();
  }
}

export function setupFakeClock(hooks: NestedHooks): () => FakeClock {
  let clock = new FakeClock();
  const real = {
    setInterval: globalThis.setInterval,
    clearInterval: globalThis.clearInterval,
    now: Date.now,
  };

  hooks.beforeEach(function () {
    clock = new FakeClock();
    globalThis.setInterval = clock.setInterval as typeof setInterval;
    globalThis.clearInterval = clock.clearInterval;
    Date.now = () => clock.now;
  });

  hooks.afterEach(function () {
    globalThis.setInterval = real.setInterval;
    globalThis.clearInterval = real.clearInterval;
    Date.now = real.now;
  });

  return () => clock;
}
