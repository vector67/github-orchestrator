import Component from '@glimmer/component';
import type Owner from '@ember/owner';
import { tracked } from '@glimmer/tracking';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import { fn } from '@ember/helper';
import { waitForPromise } from '@ember/test-waiters';
import HubBar from 'frontend/components/hub-bar';
import type {
  Setup,
  SetupClone,
  SetupCloneProgress,
  SetupRepoChoice,
} from 'frontend/data/api';
import { Refusal } from 'frontend/data/refusal';
import type HubService from 'frontend/services/hub';
import type StoreService from 'frontend/services/store';

interface Pick {
  repo: string;
  local_path: string;
  new_worktree_command: string;
  edited: boolean;
}

interface Row {
  repo: string;
  can_push: boolean | null;
  has_my_prs: boolean;
  picked: boolean;
}

interface CloneLine {
  pick: Pick;
  index: number;
  said: string;
  alarm: boolean;
  refusedRepo: string | null;
  refusedPath: string | null;
}

const OWNER_NAME = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;

const CLONE_WORDS: Record<SetupCloneProgress['state'], string> = {
  waiting: 'waiting to clone',
  cloning: 'cloning…',
  cloned: 'cloned',
  found: 'clone found',
  failed: 'clone failed',
};

function valueOf(event: Event): string {
  return (event.target as HTMLInputElement).value;
}

function checkedOf(event: Event): boolean {
  return (event.target as HTMLInputElement).checked;
}

function troubleOf(trouble: unknown): string {
  return trouble instanceof Refusal ? trouble.detail : String(trouble);
}

function cloneSaid(pick: Pick, clone: SetupClone | undefined): string {
  if (pick.edited) {
    return `Will clone into ${pick.local_path}, unless a clone of ${pick.repo} is already there`;
  }
  if (!clone) return `Looking for a clone of ${pick.repo}…`;
  if (clone.is_clone) return `Found a clone at ${clone.path}`;
  if (clone.exists) {
    return `${clone.path} holds something that is not a clone of ${pick.repo}; choose another folder`;
  }
  return `Will clone into ${clone.path}`;
}

export default class SetupPage extends Component {
  @service declare store: StoreService;
  @service declare hub: HubService;

  @tracked login: string;
  @tracked checked: string | null = null;
  @tracked checking = false;
  @tracked loginTrouble: string | null = null;
  @tracked filter = '';
  @tracked readOnly = false;
  @tracked picks: Pick[];
  @tracked byName = '';
  @tracked byNameTrouble: string | null = null;
  @tracked model: string;
  @tracked enabled: boolean;
  @tracked threadRuns: number;
  @tracked refused: Record<string, string> = {};
  @tracked trouble: string | null = null;
  @tracked writing = false;
  @tracked moving = false;

  constructor(owner: Owner, args: object) {
    super(owner, args);
    const setup = this.setup;
    this.login = setup?.gh_account ?? setup?.active_account ?? '';
    this.picks = (setup?.repos ?? []).map((one) => ({
      repo: one.repo,
      local_path: one.local_path,
      new_worktree_command: one.new_worktree_command ?? '',
      edited: false,
    }));
    this.model = setup?.options.agent_model ?? '';
    this.enabled = setup?.options.agents_enabled ?? true;
    this.threadRuns = setup?.options.max_thread_runs ?? 4;
    this.picks.forEach((pick) => void this.lookForClone(pick.repo));
    if (this.login && setup?.state !== 'broken') {
      void waitForPromise(this.check());
    }
  }

  get agentName(): string {
    return this.setup?.agent_name ?? 'Agent';
  }

  get setup(): Setup | null {
    return this.store.setup;
  }

  get watching(): boolean {
    return this.setup?.state === 'watching';
  }

  get broken(): boolean {
    return this.setup?.state === 'broken';
  }

  get restarting(): boolean {
    return this.store.setupOperation?.state === 'restarting';
  }

  get progress(): SetupCloneProgress[] {
    return this.store.setupOperation?.clones ?? [];
  }

  get listed(): SetupRepoChoice[] {
    return this.checked ? (this.store.repoChoices[this.checked] ?? []) : [];
  }

  get rows(): Row[] {
    const listed = this.listed;
    const known = new Set(listed.map((one) => one.repo));
    const picked = new Set(this.picks.map((one) => one.repo));
    const extra = this.picks
      .filter((pick) => !known.has(pick.repo))
      .map((pick) => {
        const named = this.store.named[pick.repo];
        return {
          repo: pick.repo,
          can_push: named ? named.can_push : null,
          has_my_prs: named?.has_my_prs ?? false,
          picked: true,
        };
      });
    const wanted = this.filter.trim().toLowerCase();
    return [
      ...extra,
      ...listed.map((one) => ({ ...one, picked: picked.has(one.repo) })),
    ].filter(
      (row) =>
        (row.picked || row.can_push !== false || this.readOnly) &&
        row.repo.toLowerCase().includes(wanted),
    );
  }

  get hiddenReadOnly(): number {
    const picked = new Set(this.picks.map((one) => one.repo));
    return this.listed.filter((one) => !one.can_push && !picked.has(one.repo))
      .length;
  }

  get cloneLines(): CloneLine[] {
    return this.picks.map((pick, index) => {
      const clone = this.store.clones[pick.repo];
      return {
        pick,
        index,
        said: cloneSaid(pick, clone),
        alarm: !pick.edited && !!clone?.exists && !clone.is_clone,
        refusedRepo: this.refused[`repos[${index}].repo`] ?? null,
        refusedPath: this.refused[`repos[${index}].local_path`] ?? null,
      };
    });
  }

  get dropped(): string[] {
    const picked = new Set(this.picks.map((one) => one.repo));
    return (this.setup?.repos ?? [])
      .map((one) => one.repo)
      .filter((repo) => !picked.has(repo));
  }

  get canStart(): boolean {
    return (
      !!this.checked && this.picks.length > 0 && !this.writing && !this.checking
    );
  }

  get startWords(): string {
    return this.watching ? 'Save and restart' : 'Start watching';
  }

  typeLogin = (event: Event) => {
    this.login = valueOf(event).trim();
  };

  submitLogin = (event: Event) => {
    event.preventDefault();
    void waitForPromise(this.check());
  };

  checkAgain = () => void waitForPromise(this.check());

  async check(): Promise<void> {
    const login = this.login;
    if (!login) return;
    this.checking = true;
    this.loginTrouble = null;
    try {
      await this.store.readAccount(login);
      await this.store.readRepoChoices(login);
      this.checked = login;
    } catch (trouble) {
      this.checked = null;
      this.loginTrouble = troubleOf(trouble);
    } finally {
      this.checking = false;
    }
  }

  typeFilter = (event: Event) => {
    this.filter = valueOf(event);
  };

  showReadOnly = (event: Event) => {
    this.readOnly = checkedOf(event);
  };

  toggle = (repo: string) => {
    if (this.picks.some((pick) => pick.repo === repo)) {
      this.picks = this.picks.filter((pick) => pick.repo !== repo);
      return;
    }
    this.pick(repo);
  };

  private pick(repo: string): void {
    this.picks = [
      ...this.picks,
      { repo, local_path: '', new_worktree_command: '', edited: false },
    ];
    void waitForPromise(this.lookForClone(repo));
  }

  private async lookForClone(repo: string): Promise<void> {
    try {
      const clone = await this.store.readClone(repo);
      this.picks = this.picks.map((pick) =>
        pick.repo === repo && !pick.edited
          ? { ...pick, local_path: pick.local_path || clone.path }
          : pick,
      );
    } catch {
      return;
    }
  }

  typeByName = (event: Event) => {
    this.byName = valueOf(event).trim();
    this.byNameTrouble = null;
  };

  addByName = (event: Event) => {
    event.preventDefault();
    void waitForPromise(this.adding());
  };

  private async adding(): Promise<void> {
    const repo = this.byName;
    if (!OWNER_NAME.test(repo)) {
      this.byNameTrouble = `${repo || 'That'} is not owner/name`;
      return;
    }
    if (!this.checked) return;
    try {
      await this.store.readRepoByName(this.checked, repo);
    } catch (trouble) {
      this.byNameTrouble = troubleOf(trouble);
      return;
    }
    this.byName = '';
    if (!this.picks.some((pick) => pick.repo === repo)) this.pick(repo);
  }

  typePath = (repo: string, event: Event) => {
    const path = valueOf(event);
    this.picks = this.picks.map((pick) =>
      pick.repo === repo ? { ...pick, local_path: path, edited: true } : pick,
    );
  };

  typeCommand = (repo: string, event: Event) => {
    const command = valueOf(event);
    this.picks = this.picks.map((pick) =>
      pick.repo === repo ? { ...pick, new_worktree_command: command } : pick,
    );
  };

  typeModel = (event: Event) => {
    this.model = valueOf(event);
  };

  flipEnabled = (event: Event) => {
    this.enabled = checkedOf(event);
  };

  typeRuns = (event: Event) => {
    this.threadRuns = Number(valueOf(event));
  };

  start = (event: Event) => {
    event.preventDefault();
    void waitForPromise(this.starting());
  };

  private async starting(): Promise<void> {
    if (!this.canStart || !this.checked) return;
    this.writing = true;
    this.refused = {};
    this.trouble = null;
    try {
      await this.store.writeSetup({
        gh_account: this.checked,
        repos: this.picks.map(({ repo, local_path, new_worktree_command }) => ({
          repo,
          local_path,
          new_worktree_command,
        })),
        options: {
          agent_model: this.model,
          agents_enabled: this.enabled,
          max_thread_runs: this.threadRuns,
        },
      });
    } catch (trouble) {
      this.writing = false;
      await this.refusedBy(trouble);
      return;
    }
    this.hub.followRestart();
  }

  private async refusedBy(trouble: unknown): Promise<void> {
    if (trouble instanceof Refusal && trouble.code === 'precondition-failed') {
      await this.store.readSetup();
      this.trouble =
        'The config changed since this page read it. Check your choices and save again.';
      return;
    }
    if (trouble instanceof Refusal && Object.keys(trouble.fields).length) {
      this.refused = trouble.fields;
      this.trouble = trouble.fields['config'] ?? null;
      return;
    }
    this.trouble = troubleOf(trouble);
  }

  back = () => {
    this.writing = false;
    this.store.dropSetupOperation();
  };

  moveAside = () => void waitForPromise(this.movingAside());

  private async movingAside(): Promise<void> {
    this.moving = true;
    try {
      await this.store.moveAside();
    } catch (trouble) {
      this.moving = false;
      this.trouble = troubleOf(trouble);
      return;
    }
    this.hub.followRestart();
  }

  <template>
    <main id="setup" data-test-setup>
      {{#if this.watching}}
        <HubBar @on="setup" />
      {{else}}
        <header class="wall-bar">
          <span class="wall-name">Orchestrator</span>
          <span class="setup-crumb">Setup</span>
        </header>
      {{/if}}
      <div class="setup-body">
        {{#if this.broken}}
          <section class="setup-step" data-test-setup-broken>
            <h2>The config does not read</h2>
            <p
              class="setup-alarm"
              data-test-setup-problem
            >{{this.setup.problem}}</p>
            <p>It is at
              <code>{{this.setup.config_path}}</code>. Fix it there and restart,
              or move it aside and start again from this page.</p>
            {{#if this.store.movedTo}}
              <p data-test-setup-moved>Moved to
                <code>{{this.store.movedTo}}</code>. Restarting the watcher…</p>
            {{else}}
              <button
                type="button"
                class="btn fill"
                disabled={{this.moving}}
                data-test-setup-move-aside
                {{on "click" this.moveAside}}
              >Move it aside and start again</button>
            {{/if}}
            {{#if this.trouble}}
              <p
                class="setup-alarm"
                data-test-setup-trouble
              >{{this.trouble}}</p>
            {{/if}}
          </section>
        {{else if this.writing}}
          <section class="setup-step" data-test-setup-progress>
            <h2>{{if this.restarting "Restarting the watcher" "Cloning"}}</h2>
            {{#unless this.store.setupOperation}}
              <p class="setup-said" data-test-setup-checking>Checking each repo
                and clone with GitHub before anything is written…</p>
            {{/unless}}
            <ul class="setup-clones">
              {{#each this.progress key="repo" as |clone|}}
                <li
                  data-test-clone-progress={{clone.repo}}
                  data-test-clone-state={{clone.state}}
                >
                  <i
                    class="sq
                      {{if (isFailed clone.state) 'alarm'}}
                      {{if (isDone clone.state) 'done'}}"
                  ></i>
                  <span class="setup-repo">{{clone.repo}}</span>
                  <span class="setup-said">{{cloneWords clone.state}}
                    <code>{{clone.path}}</code></span>
                  {{#if clone.error}}
                    <span class="setup-alarm">{{clone.error}}</span>
                  {{/if}}
                </li>
              {{/each}}
            </ul>
            {{#if this.restarting}}
              <p data-test-setup-restarting>The config is written. The watcher
                is restarting; the wall opens when it is back.</p>
              {{#each
                this.store.setupOperation.archived key="@identity"
                as |path|
              }}
                <p class="setup-said" data-test-setup-archived>Archived
                  <code>{{path}}</code></p>
              {{/each}}
              {{#each
                this.store.setupOperation.kept_worktrees key="@identity"
                as |path|
              }}
                <p class="setup-said" data-test-setup-kept>Left the worktree
                  <code>{{path}}</code>
                  where it is</p>
              {{/each}}
            {{/if}}
            {{#if this.store.setupOperation.error}}
              <p class="setup-alarm" data-test-setup-failed>
                {{this.store.setupOperation.error}}</p>
              <button
                type="button"
                class="btn"
                data-test-setup-back
                {{on "click" this.back}}
              >Back to setup</button>
            {{/if}}
          </section>
        {{else}}
          <form
            class="setup-step"
            data-test-setup-account
            aria-label="your GitHub username"
            {{on "submit" this.submitLogin}}
          >
            <h2><span class="setup-num">1</span>Your GitHub username</h2>
            <div class="setup-line">
              <input
                type="text"
                class="setup-input"
                aria-label="GitHub username"
                value={{this.login}}
                autocomplete="username"
                data-test-setup-login
                {{on "input" this.typeLogin}}
              />
              <button
                type="submit"
                class="btn"
                disabled={{this.checking}}
                data-test-setup-check
              >{{if this.checking "Checking…" "Check"}}</button>
            </div>
            {{#if this.loginTrouble}}
              <div class="setup-alarm" data-test-setup-login-trouble>
                <p>{{this.loginTrouble}}</p>
                <p>Run
                  <code>gh auth login</code>
                  in a terminal, then check again.</p>
                <button
                  type="button"
                  class="btn"
                  data-test-setup-check-again
                  {{on "click" this.checkAgain}}
                >Check again</button>
              </div>
            {{/if}}
            {{#if this.refused.gh_account}}
              <p class="setup-alarm" data-test-refused="gh_account">
                {{this.refused.gh_account}}</p>
            {{/if}}
          </form>

          {{#if this.checked}}
            <section class="setup-step" data-test-setup-repos>
              <h2><span class="setup-num">2</span>Your repositories</h2>
              <div class="setup-line">
                <input
                  type="search"
                  class="setup-input"
                  placeholder="Filter"
                  aria-label="filter the repositories"
                  value={{this.filter}}
                  data-test-setup-filter
                  {{on "input" this.typeFilter}}
                />
                <label class="setup-toggle">
                  <input
                    type="checkbox"
                    class="checkbox"
                    checked={{this.readOnly}}
                    data-test-setup-read-only
                    {{on "change" this.showReadOnly}}
                  />
                  Show read-only
                  {{#if this.hiddenReadOnly}}({{this.hiddenReadOnly}}){{/if}}
                </label>
              </div>
              <ul class="setup-list">
                {{#each this.rows key="repo" as |row|}}
                  <li
                    class="setup-row {{if row.picked 'picked'}}"
                    data-test-setup-repo={{row.repo}}
                    data-test-picked={{if row.picked "true" "false"}}
                  >
                    <label>
                      <input
                        type="checkbox"
                        class="checkbox"
                        checked={{row.picked}}
                        {{on "change" (fn this.toggle row.repo)}}
                      />
                      <span class="setup-repo">{{row.repo}}</span>
                    </label>
                    {{#if row.has_my_prs}}
                      <span class="setup-tag" data-test-has-my-prs>your PRs</span>
                    {{/if}}
                    {{#if (isReadOnly row.can_push)}}
                      <span
                        class="setup-tag muted"
                        data-test-read-only
                      >read-only</span>
                    {{/if}}
                  </li>
                {{else}}
                  <li class="setup-said" data-test-setup-no-repos>No repository
                    matches.</li>
                {{/each}}
              </ul>
              <form
                class="setup-line"
                data-test-setup-by-name
                aria-label="add a repo by name"
                {{on "submit" this.addByName}}
              >
                <input
                  type="text"
                  class="setup-input"
                  placeholder="owner/name"
                  aria-label="add a repo by name"
                  value={{this.byName}}
                  data-test-setup-by-name-input
                  {{on "input" this.typeByName}}
                />
                <button type="submit" class="btn" data-test-setup-add>Add a repo
                  by name</button>
              </form>
              {{#if this.byNameTrouble}}
                <p class="setup-alarm" data-test-setup-by-name-trouble>
                  {{this.byNameTrouble}}</p>
              {{/if}}
            </section>

            <section class="setup-step" data-test-setup-clones>
              <h2><span class="setup-num">3</span>Clones</h2>
              {{#each this.cloneLines key="pick.repo" as |line|}}
                <div class="setup-clone" data-test-clone={{line.pick.repo}}>
                  <span class="setup-repo">{{line.pick.repo}}</span>
                  <input
                    type="text"
                    class="setup-input"
                    aria-label="clone of {{line.pick.repo}}"
                    value={{line.pick.local_path}}
                    data-test-clone-path
                    {{on "input" (fn this.typePath line.pick.repo)}}
                  />
                  <span
                    class="setup-said {{if line.alarm 'setup-alarm'}}"
                    data-test-clone-said
                  >{{line.said}}</span>
                  {{#if line.refusedRepo}}
                    <span
                      class="setup-alarm"
                      data-test-refused="repo"
                    >{{line.refusedRepo}}</span>
                  {{/if}}
                  {{#if line.refusedPath}}
                    <span
                      class="setup-alarm"
                      data-test-refused="local_path"
                    >{{line.refusedPath}}</span>
                  {{/if}}
                </div>
              {{else}}
                <p class="setup-said" data-test-setup-no-picks>Pick at least one
                  repository to watch.</p>
              {{/each}}
              {{#each this.dropped key="@identity" as |repo|}}
                <p class="setup-said" data-test-setup-dropped={{repo}}>Stops
                  watching
                  {{repo}}. Its state, queues and holds are archived; its
                  worktrees and its clone stay where they are.</p>
              {{/each}}
            </section>

            <form
              class="setup-step"
              data-test-setup-options
              aria-label="other options"
              {{on "submit" this.start}}
            >
              <h2><span class="setup-num">4</span>Other options</h2>
              <label class="setup-option">
                <span data-test-setup-model-label>{{this.agentName}}
                  model</span>
                <input
                  type="text"
                  class="setup-input"
                  value={{this.model}}
                  data-test-setup-model
                  {{on "input" this.typeModel}}
                />
              </label>
              <label class="setup-option">
                <span>Start agents on their own</span>
                <input
                  type="checkbox"
                  class="checkbox"
                  checked={{this.enabled}}
                  data-test-setup-enabled
                  {{on "change" this.flipEnabled}}
                />
              </label>
              <label class="setup-option">
                <span>Thread agents at once</span>
                <input
                  type="number"
                  min="1"
                  max="64"
                  class="setup-input setup-narrow"
                  value={{this.threadRuns}}
                  data-test-setup-runs
                  {{on "input" this.typeRuns}}
                />
              </label>
              {{#each this.picks key="repo" as |pick|}}
                <label class="setup-option">
                  <span>Command in each new worktree of {{pick.repo}}</span>
                  <input
                    type="text"
                    class="setup-input"
                    placeholder="nothing"
                    value={{pick.new_worktree_command}}
                    data-test-setup-command={{pick.repo}}
                    {{on "input" (fn this.typeCommand pick.repo)}}
                  />
                </label>
              {{/each}}
              {{#if this.trouble}}
                <p
                  class="setup-alarm"
                  data-test-setup-trouble
                >{{this.trouble}}</p>
              {{/if}}
              <div class="setup-line">
                <button
                  type="submit"
                  class="btn fill"
                  disabled={{if this.canStart false true}}
                  data-test-setup-start
                >{{this.startWords}}</button>
              </div>
            </form>
          {{/if}}
        {{/if}}
      </div>
    </main>
  </template>
}

function isReadOnly(canPush: boolean | null): boolean {
  return canPush === false;
}

function isFailed(state: SetupCloneProgress['state']): boolean {
  return state === 'failed';
}

function isDone(state: SetupCloneProgress['state']): boolean {
  return state === 'cloned' || state === 'found';
}

function cloneWords(state: SetupCloneProgress['state']): string {
  return CLONE_WORDS[state];
}
