import Service, { service } from '@ember/service';
import { waitForPromise } from '@ember/test-waiters';
import type { Commits, Conversation, Diff, Operation } from 'frontend/data/api';
import {
  columnCards,
  countsOf,
  grouped,
  groupsFor,
  READY_GROUP,
  type Count,
  type Group,
  type Role,
} from 'frontend/data/groups';
import type { Context, Details, Fix } from 'frontend/data/panel';
import { unreachable } from 'frontend/data/refusal';
import type { Numbered } from 'frontend/data/wall';
import { rowOf, type Row, type Seen } from 'frontend/data/rows';
import type HereService from 'frontend/services/here';
import type { PrScope } from 'frontend/services/here';
import type PollService from 'frontend/services/poll';
import type ReachabilityService from 'frontend/services/reachability';
import type { Reach } from 'frontend/services/reachability';
import type StoreService from 'frontend/services/store';
import type { Drawing, PrEntity } from 'frontend/services/store';

export interface Section {
  group: Group;
  rows: Row[];
}

export interface Header {
  repo: string;
  number: number;
  title: string | null;
  html_url: string;
  counts: Count[];
}

const PRELOAD_BATCH = 5;

const UNREADABLE_GIST = "this card's record could not be read";

function unreadableRow(key: string): Row {
  return {
    id: key,
    group: READY_GROUP,
    column: READY_GROUP,
    square: 'failed',
    gist: UNREADABLE_GIST,
    reference: null,
    meta: '',
    steps: [],
    steps_text: '',
    steps_hint: '',
    standing: null,
    standing_label: '',
    alert: '',
    provisional: false,
  };
}

class PerPr {
  asking: Record<string, string> = {};
  watching: string | null = null;
  preloading = false;

  readonly panel: Reach;

  constructor(
    reachability: ReachabilityService,
    readonly scope: PrScope,
    readonly at: Numbered,
    loaded: () => boolean,
  ) {
    this.panel = reachability.reach(
      'panel',
      (trouble) => loaded() || !unreachable(trouble),
      scope,
    );
  }
}

export default class ThreadsService extends Service {
  @service declare here: HereService;
  @service('poll') declare loader: PollService;
  @service declare reachability: ReachabilityService;
  @service declare store: StoreService;

  private fresh = (scope: PrScope): PerPr =>
    new PerPr(this.reachability, scope, this.here.at, () => this.loaded);

  private get pr(): PerPr {
    return this.here.scope.of(this.fresh);
  }

  get loaded(): boolean {
    return this.loader.rail.loaded;
  }

  details = (key: string): Details | null => {
    const repo = this.pullRequest?.repo;
    return repo ? this.store.details(repo, this.pr.at.number, key) : null;
  };

  get pullRequest(): PrEntity | null {
    const { repo, number } = this.pr.at;
    return this.store.pr(repo, number) ?? null;
  }

  get conversations(): Conversation[] {
    const repo = this.pullRequest?.repo;
    return repo ? this.store.conversations(repo, this.pr.at.number) : [];
  }

  get unreadable(): string[] {
    return this.pullRequest?.unreadable ?? [];
  }

  get inFlight(): Operation[] {
    const repo = this.pullRequest?.repo;
    return repo ? this.store.inFlight(repo, this.pr.at.number) : [];
  }

  get role(): Role | null {
    const repo = this.pullRequest?.repo;
    if (!repo) return null;
    return this.store.summary(repo, this.pr.at.number)?.role ?? null;
  }

  thread(key: string): Conversation | undefined {
    return this.conversations.find((one) => one.key === key);
  }

  fixOf(key: string): Fix {
    const repo = this.pullRequest?.repo;
    const proposal = repo
      ? this.store.proposal(repo, this.pr.at.number, key)
      : undefined;
    const commits = proposal?.commits;
    return { proposal, files: (commits && this.store.files(commits)) ?? [] };
  }

  diff(commits: Commits): Diff | undefined {
    return this.store.diff(commits);
  }

  loadDiff(commits: Commits): Promise<Drawing> {
    return this.store.readDiff(commits);
  }

  inFlightFor(key: string): Operation | undefined {
    return this.inFlight.findLast((one) => one.conversation === key);
  }

  private seenFor(key: string, role: Role): Seen {
    return {
      role,
      viewer: this.store.viewer ?? '',
      names: this.store.names,
      inFlight: this.inFlightFor(key),
    };
  }

  contextFor(key: string, role: Role): Context {
    return {
      ...this.seenFor(key, role),
      pullRequest: this.pullRequest,
      ready: this.readyKeys,
      now: Date.now(),
    };
  }

  get readyKeys(): string[] {
    const first = this.sections[0];
    if (first?.group.key !== READY_GROUP) return [];
    return first.rows.map((row) => row.id);
  }

  get railOrder(): string[] {
    return this.sections.flatMap((one) => one.rows.map((row) => row.id));
  }

  get sections(): Section[] {
    const role = this.role;
    if (!role) return [];
    const sections = grouped(this.conversations, role).map(
      ({ group, threads }) => ({
        group,
        rows: threads.map((one) => rowOf(one, this.seenFor(one.key, role))),
      }),
    );
    if (!this.unreadable.length) return sections;
    const lost = this.unreadable.map(unreadableRow);
    const ready = sections.find((one) => one.group.key === READY_GROUP);
    if (ready) {
      ready.rows = [...ready.rows, ...lost];
      return sections;
    }
    const group = groupsFor(role).find((one) => one.key === READY_GROUP)!;
    return [{ group, rows: lost }, ...sections];
  }

  get columns(): { column: Group; rows: Row[] }[] {
    const role = this.role;
    if (!role) return [];
    return columnCards(this.conversations, role).map(({ column, threads }) => ({
      column,
      rows: threads.map((one) => rowOf(one, this.seenFor(one.key, role))),
    }));
  }

  get header(): Header | null {
    const pull = this.pullRequest;
    if (!pull) return null;
    const summaries = this.store.summary(pull.repo, this.pr.at.number);
    return {
      repo: pull.repo,
      number: pull.number,
      title: pull.title,
      html_url: pull.url ?? '',
      counts: summaries?.role ? countsOf(summaries.groups, summaries.role) : [],
    };
  }

  async reread(): Promise<void> {
    const pr = this.pr;
    if (pr.watching) await this.loadWatched(pr.watching);
  }

  watch(key: string | null): void {
    const pr = this.pr;
    pr.watching = key;
    if (key)
      void waitForPromise(this.loadWatched(key).then(() => this.preload(pr)));
  }

  private async preload(pr: PerPr): Promise<void> {
    if (pr.scope.left || pr.preloading) return;
    pr.preloading = true;
    const waiting = this.railOrder.filter((key) => !this.details(key));
    for (let at = 0; at < waiting.length; at += PRELOAD_BATCH) {
      if (pr.scope.left) return;
      await Promise.all(
        waiting
          .slice(at, at + PRELOAD_BATCH)
          .map((key) => this.loadDetails(key)),
      );
    }
  }

  async loadDetails(key: string): Promise<void> {
    const pr = this.pr;
    const conversation = this.thread(key);
    if (!conversation) return;
    const version = `${conversation.etag} ${conversation.updated_at ?? ''}`;
    if (this.details(key)?.version === version || pr.asking[key] === version)
      return;
    pr.asking[key] = version;
    await pr.panel
      .attempt(() => this.store.readThread(pr.at, key))
      .catch(() => null);
    if (pr.asking[key] === version) delete pr.asking[key];
  }

  private async loadWatched(key: string): Promise<void> {
    await this.loadDetails(key);
    const commits = this.fixOf(key).proposal?.commits;
    if (commits) await this.loadDiff(commits);
  }
}
