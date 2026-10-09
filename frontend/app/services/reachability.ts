import Service, { service } from '@ember/service';
import { tracked } from '@glimmer/tracking';
import { waitForPromise } from '@ember/test-waiters';
import { Abandoned } from 'frontend/data/refusal';
import { reportError } from 'frontend/data/report';
import { flip } from 'frontend/motion';
import { registerDestructor } from '@ember/destroyable';
import type HereService from 'frontend/services/here';
import type { PrScope } from 'frontend/services/here';
import type StoreService from 'frontend/services/store';
import type { Asked } from 'frontend/services/store';

export const DOWN = 'the board server is not answering';
const HEAVY = 'the system is under heavy load';

const MISSES_BEFORE_DOWN = 2;

type Counts = (trouble: unknown) => boolean;

const everyTrouble: Counts = () => true;

export class Reach {
  @tracked protected misses = 0;

  constructor(
    private readonly where: string,
    private readonly counts: Counts,
    private readonly heard: (down: boolean) => void,
  ) {}

  get missed(): boolean {
    return this.misses > 0;
  }

  get down(): boolean {
    return this.misses >= MISSES_BEFORE_DOWN;
  }

  async attempt<T>(ask: () => Promise<T>): Promise<T> {
    try {
      const answer = await ask();
      this.missesAre(0);
      return answer;
    } catch (trouble) {
      this.miss(trouble);
      throw trouble;
    }
  }

  private miss(trouble: unknown): void {
    if (trouble instanceof Abandoned) return;
    void reportError(this.where, trouble);
    if (!this.counts(trouble)) return;
    this.missesAre(this.misses + 1);
  }

  protected missesAre(misses: number): void {
    if (misses === this.misses) return;
    this.misses = misses;
    this.heard(this.down);
  }
}

export class Polled extends Reach {
  mark = '';
  private tag: string | null = null;
  private unanswered = 0;

  constructor(
    where: string,
    counts: Counts,
    heard: (down: boolean) => void,
    private readonly ask: (tag: string | null) => Promise<Asked>,
    private readonly flipped: boolean,
    private readonly overdue: boolean,
  ) {
    super(where, counts, heard);
  }

  async poll(): Promise<boolean> {
    if (this.overdue && this.unanswered > 0) this.missesAre(this.misses + 1);
    this.unanswered += 1;
    try {
      return await this.read();
    } finally {
      this.unanswered -= 1;
    }
  }

  private async read(): Promise<boolean> {
    const answer = await this.attempt(() => this.ask(this.tag));
    if (!answer.changed) return false;
    let took = false;
    const change = () => {
      took = answer.take();
    };
    if (this.flipped) {
      await flip(change);
    } else {
      change();
    }
    this.tag = took ? answer.tag : null;
    if (took) this.mark = answer.mark;
    return took;
  }

  forget(): void {
    this.tag = null;
  }
}

interface Polling {
  counts?: Counts;
  flipped?: boolean;
  overdue?: boolean;
  scope?: PrScope;
}

export default class ReachabilityService extends Service {
  @service declare here: HereService;
  @service declare store: StoreService;

  @tracked private healthAnswers = false;
  @tracked private revision = 0;

  private reaches: Reach[] = [];

  reach(where: string, counts: Counts, scope: PrScope): Reach {
    return this.kept(new Reach(where, counts, this.heard), scope);
  }

  polled(
    where: string,
    ask: (tag: string | null) => Promise<Asked>,
    {
      counts = everyTrouble,
      flipped = false,
      overdue = false,
      scope,
    }: Polling = {},
  ): Polled {
    return this.kept(
      new Polled(where, counts, this.heard, ask, flipped, overdue),
      scope,
    );
  }

  get outage(): string {
    return this.healthAnswers ? HEAVY : DOWN;
  }

  get banner(): string | null {
    void this.revision;
    return this.reaches.some((one) => one.down) ? this.outage : null;
  }

  private kept<R extends Reach>(one: R, scope?: PrScope): R {
    this.reaches.push(one);
    if (scope)
      registerDestructor(scope, () => {
        this.reaches = this.reaches.filter((kept) => kept !== one);
        this.revision += 1;
      });
    return one;
  }

  private heard = (down: boolean): void => {
    this.revision += 1;
    if (down) void waitForPromise(this.askHealth());
  };

  private async askHealth(): Promise<void> {
    this.healthAnswers = await this.store.answers(this.here.api('/api/health'));
  }
}
