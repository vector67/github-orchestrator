import type {
  FieldError,
  Setup,
  SetupClone,
  SetupOperation,
  SetupRepoChoice,
  SetupRequest,
} from 'frontend/data/api';

export interface Answer {
  status: number;
  body: unknown;
  location?: string;
}

export interface SetupWrite {
  ifMatch: string | null;
  body: SetupRequest;
}

export function setupRead(over: Partial<Setup> = {}): Setup {
  return {
    state: 'setup',
    etag: '"setup-1"',
    config_path: '/Users/octocat/.config/github-orchestrator/config.toml',
    problem: 'config.toml: the config file does not exist',
    active_account: 'octocat',
    gh_account: null,
    repos: [],
    options: { agent_model: 'opus', agents_enabled: true, max_thread_runs: 4 },
    hub_port: 8720,
    agent_name: 'Claude',
    requirements: [{ program: 'gh', fix: null }],
    ...over,
  };
}

export function choice(
  repo: string,
  over: Partial<SetupRepoChoice> = {},
): SetupRepoChoice {
  return {
    repo,
    can_push: true,
    has_my_prs: false,
    default_branch: 'main',
    ...over,
  };
}

function refused(status: number, code: string, detail: string): Answer {
  return { status, body: { errors: [{ status, code, detail }] } };
}

const OPERATION = /^\/api\/setup\/operations\/([^/]+)$/;
const ACCOUNT = /^\/api\/setup\/accounts\/([^/]+)$/;
const REPOS = /^\/api\/setup\/accounts\/([^/]+)\/repos$/;
const NAMED = /^\/api\/setup\/repos\/([^/]+\/[^/]+)$/;
const CLONE = /^\/api\/setup\/clones\/([^/]+\/[^/]+)$/;

export class FakeSetup {
  read: Setup = setupRead();
  tokens: Record<string, string[]> = { octocat: ['repo'] };
  choices: SetupRepoChoice[] = [];
  visible: Record<string, SetupRepoChoice> = {};
  cloned: Record<string, string> = {};
  found: Record<string, SetupClone> = {};
  writes: SetupWrite[] = [];
  movedAside = 0;
  refusals: FieldError[] | null = null;
  progress: SetupOperation | null = null;
  asked: string[] = [];

  answer(method: string, where: URL, init?: RequestInit): Answer | null {
    const path = where.pathname;
    if (!path.startsWith('/api/setup')) return null;
    this.asked.push(`${method} ${path}`);
    if (method === 'PUT' && path === '/api/setup') return this.write(init);
    if (method === 'POST' && path === '/api/setup:move-aside') {
      this.movedAside += 1;
      return {
        status: 202,
        body: { moved_to: `${this.read.config_path}.broken-20261009-083005` },
      };
    }
    if (method !== 'GET') return null;
    if (path === '/api/setup') return { status: 200, body: this.read };
    return this.lookUp(path, where);
  }

  private lookUp(path: string, where: URL): Answer | null {
    const repos = REPOS.exec(path);
    if (repos) {
      const login = decodeURIComponent(repos[1]!);
      if (!this.tokens[login]) return this.noToken(login);
      return { status: 200, body: { login, repos: this.choices } };
    }
    const account = ACCOUNT.exec(path);
    if (account) {
      const login = decodeURIComponent(account[1]!);
      const scopes = this.tokens[login];
      if (!scopes) return this.noToken(login);
      return { status: 200, body: { login, scopes } };
    }
    const named = NAMED.exec(path);
    if (named) {
      const found = this.visible[named[1]!];
      if (!found) {
        return refused(
          404,
          'repo-not-visible',
          `${where.searchParams.get('login')} cannot see ${named[1]}`,
        );
      }
      return { status: 200, body: found };
    }
    const clone = CLONE.exec(path);
    if (clone) {
      const repo = clone[1]!;
      const name = repo.split('/')[1]!;
      return {
        status: 200,
        body: this.found[repo] ?? {
          repo,
          path: this.cloned[repo] ?? `~/repositories/${name}`,
          exists: repo in this.cloned,
          is_clone: repo in this.cloned,
        },
      };
    }
    const operation = OPERATION.exec(path);
    if (operation && this.progress?.id === operation[1]) {
      return { status: 200, body: this.progress };
    }
    return null;
  }

  private noToken(login: string): Answer {
    return refused(
      404,
      'no-gh-token',
      `gh auth token --user ${login} failed (exit 1): no oauth token found for github.com account ${login} — run \`gh auth login\` as ${login}`,
    );
  }

  private write(init?: RequestInit): Answer {
    const headers = new Headers(init?.headers);
    const body = JSON.parse(init?.body as string) as SetupRequest;
    this.writes.push({ ifMatch: headers.get('If-Match'), body });
    if (headers.get('If-Match') !== this.read.etag) {
      return refused(412, 'precondition-failed', 'the config has changed');
    }
    if (this.refusals) return { status: 422, body: { errors: this.refusals } };
    this.progress = {
      id: 'setup_1',
      state: 'cloning',
      clones: body.repos.map((one) => ({
        repo: one.repo,
        path: one.local_path.replace('~', '/Users/octocat'),
        state: one.repo in this.cloned ? 'found' : 'waiting',
        error: null,
      })),
      error: null,
      archived: [],
      kept_worktrees: [],
    };
    return {
      status: 202,
      body: this.progress,
      location: '/api/setup/operations/setup_1',
    };
  }
}
