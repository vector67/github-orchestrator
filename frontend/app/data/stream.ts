import { tracked } from '@glimmer/tracking';
import { buildWaiter } from '@ember/test-waiters';
import { reportError } from 'frontend/data/report';

export type StreamState = 'opening' | 'open' | 'down';

const opening = buildWaiter('frontend:stream-opening');

function eventOf(block: string): { id: string | null; data: string | null } {
  let id: string | null = null;
  let data: string | null = null;
  for (const line of block.split('\n')) {
    if (line.startsWith(':')) continue;
    const colon = line.indexOf(':');
    const name = colon < 0 ? line : line.slice(0, colon);
    const value = colon < 0 ? '' : line.slice(colon + 1).replace(/^ /, '');
    if (name === 'id') id = value;
    if (name === 'data') data = data === null ? value : `${data}\n${value}`;
  }
  return { id, data };
}

class EventStream {
  @tracked state: StreamState = 'opening';
  readonly opened: Promise<void>;
  private last: string | null = null;
  private readonly stopper = new AbortController();
  private firstAnswer: () => void = () => {};

  constructor(
    private readonly url: string,
    private readonly heard: (data: unknown) => void,
    private readonly became: (state: StreamState) => void = () => {},
  ) {
    this.opened = new Promise((resolve) => (this.firstAnswer = resolve));
    void this.open();
  }

  private become(state: StreamState): void {
    this.state = state;
    this.became(state);
  }

  reopen(): void {
    if (this.state === 'down') void this.open();
  }

  close(): void {
    this.stopper.abort();
  }

  private async open(): Promise<void> {
    this.become('opening');
    const token = opening.beginAsync();
    let waited = false;
    const answered = () => {
      if (waited) return;
      waited = true;
      opening.endAsync(token);
      this.firstAnswer();
    };
    try {
      await this.follow(answered);
    } catch (trouble) {
      if (!this.stopper.signal.aborted) {
        void reportError(`stream ${this.url}`, trouble);
      }
    } finally {
      answered();
      if (!this.stopper.signal.aborted) this.become('down');
    }
  }

  private async follow(answered: () => void): Promise<void> {
    const headers: Record<string, string> = { Accept: 'text/event-stream' };
    if (this.last !== null) headers['Last-Event-ID'] = this.last;
    const answer = await fetch(this.url, {
      headers,
      signal: this.stopper.signal,
    });
    if (!answer.ok || !answer.body) {
      throw new Error(`${this.url} answered ${answer.status}`);
    }
    this.become('open');
    const reader = answer.body.getReader();
    this.stopper.signal.addEventListener('abort', () => {
      reader.cancel().catch(() => undefined);
    });
    const decoder = new TextDecoder();
    let buffered = '';
    for (;;) {
      const { done, value } = await reader.read();
      if (done) return;
      const blocks = (buffered + decoder.decode(value, { stream: true })).split(
        '\n\n',
      );
      buffered = blocks.pop() ?? '';
      blocks.forEach((block) => this.take(block));
      answered();
    }
  }

  private take(block: string): void {
    const { id, data } = eventOf(block);
    if (data === null) return;
    if (id !== null) this.last = id;
    this.heard(JSON.parse(data));
  }
}

const SHARED = 'board-streams';

type Said =
  | { kind: 'want'; tab: string; paths: string[] }
  | { kind: 'gone'; tab: string }
  | { kind: 'ask' }
  | { kind: 'heard'; path: string; data: unknown }
  | { kind: 'refused'; path: string }
  | { kind: 'state'; state: StreamState }
  | { kind: 'reopen' };

interface Relayed {
  path: string;
  data?: unknown;
  status?: number;
}

interface Leading {
  wants: Map<string, string[]>;
  last: Map<string, unknown>;
  following: string;
  stream: EventStream | null;
  release: () => void;
}

class Followed {
  @tracked state: StreamState = 'opening';
  readonly opened: Promise<void>;
  private refused = false;
  private waiting: (() => void) | null;

  constructor(
    readonly path: string,
    private readonly heard: (data: unknown) => void,
    private readonly shared: SharedStreams,
  ) {
    const token = opening.beginAsync();
    let firstAnswer = () => {};
    this.opened = new Promise((resolve) => (firstAnswer = resolve));
    this.waiting = () => {
      opening.endAsync(token);
      firstAnswer();
    };
  }

  get answered(): boolean {
    return this.waiting === null;
  }

  answer(): void {
    this.waiting?.();
    this.waiting = null;
  }

  hear(data: unknown): void {
    this.answer();
    this.heard(data);
  }

  refuse(): void {
    this.refused = true;
    this.become('down');
  }

  become(state: StreamState): void {
    this.state = this.refused ? 'down' : state;
    if (this.state === 'down') this.answer();
  }

  reopen(): void {
    this.shared.reopen();
  }

  close(): void {
    this.answer();
    this.shared.unfollow(this);
  }
}

export class SharedStreams {
  private readonly tab = crypto.randomUUID();
  private readonly channel = new BroadcastChannel(SHARED);
  private readonly quitting = new AbortController();
  private readonly followed = new Set<Followed>();
  private leading: Leading | null = null;
  private state: StreamState = 'opening';
  private settling = false;
  private left = false;

  constructor(private readonly url: string) {
    this.channel.onmessage = ({ data }: MessageEvent<Said>) => this.hear(data);
    navigator.locks
      .request(SHARED, { signal: this.quitting.signal }, () => this.lead())
      .catch(() => undefined);
    window.addEventListener('pagehide', this.leave);
  }

  follow(path: string, heard: (data: unknown) => void): Followed {
    const one = new Followed(path, heard, this);
    this.followed.add(one);
    this.settleSoon();
    return one;
  }

  unfollow(one: Followed): void {
    this.followed.delete(one);
    this.settleSoon();
  }

  reopen(): void {
    if (this.state !== 'down') return;
    if (this.leading) this.leading.stream?.reopen();
    else this.say({ kind: 'reopen' });
  }

  close(): void {
    this.leave();
    window.removeEventListener('pagehide', this.leave);
  }

  private readonly leave = (): void => {
    if (this.left) return;
    this.say({ kind: 'gone', tab: this.tab });
    this.left = true;
    this.quitting.abort();
    this.channel.close();
    this.followed.forEach((one) => one.answer());
    this.followed.clear();
    const leading = this.leading;
    this.leading = null;
    leading?.stream?.close();
    leading?.release();
  };

  private get paths(): string[] {
    return [...new Set([...this.followed].map((one) => one.path))].sort();
  }

  private lead(): Promise<void> {
    return new Promise((release) => {
      if (this.left) return release();
      this.leading = {
        wants: new Map(),
        last: new Map(),
        following: '',
        stream: null,
        release,
      };
      this.say({ kind: 'ask' });
      this.settle();
    });
  }

  private settleSoon(): void {
    if (this.settling) return;
    this.settling = true;
    queueMicrotask(() => {
      this.settling = false;
      this.settle();
    });
  }

  private settle(): void {
    if (this.left) return;
    const leading = this.leading;
    if (!leading) {
      this.say({ kind: 'want', tab: this.tab, paths: this.paths });
      return;
    }
    leading.wants.set(this.tab, this.paths);
    this.followed.forEach((one) => {
      one.become(this.state);
      if (!one.answered && leading.last.has(one.path)) {
        one.hear(leading.last.get(one.path));
      }
    });
    this.connect(leading);
  }

  private hear(said: Said): void {
    const leading = this.leading;
    if (leading) {
      this.serve(leading, said);
      return;
    }
    if (said.kind === 'ask') this.settleSoon();
    if (said.kind === 'heard') this.deliver(said.path, said.data);
    if (said.kind === 'refused') this.refuse(said.path);
    if (said.kind === 'state') this.become(said.state);
  }

  private serve(leading: Leading, said: Said): void {
    if (said.kind === 'want') {
      leading.wants.set(said.tab, said.paths);
      this.say({ kind: 'state', state: this.state });
      said.paths
        .filter((path) => leading.last.has(path))
        .forEach((path) =>
          this.say({ kind: 'heard', path, data: leading.last.get(path) }),
        );
      this.connect(leading);
    }
    if (said.kind === 'gone') {
      leading.wants.delete(said.tab);
      this.connect(leading);
    }
    if (said.kind === 'reopen') leading.stream?.reopen();
  }

  private connect(leading: Leading): void {
    const paths = [...new Set([...leading.wants.values()].flat())].sort();
    const following =
      paths.length === 0
        ? ''
        : `${this.url}?${new URLSearchParams(paths.map((path) => ['follow', path])).toString()}`;
    if (following === leading.following) return;
    leading.stream?.close();
    leading.following = following;
    leading.last.clear();
    leading.stream =
      following === ''
        ? null
        : new EventStream(
            following,
            (data) => this.relay(leading, data as Relayed),
            (state) => this.spread(state),
          );
  }

  private relay(leading: Leading, { path, data, status }: Relayed): void {
    if (status !== undefined) {
      this.say({ kind: 'refused', path });
      this.refuse(path);
      return;
    }
    leading.last.set(path, data);
    this.say({ kind: 'heard', path, data });
    this.deliver(path, data);
  }

  private spread(state: StreamState): void {
    this.say({ kind: 'state', state });
    this.become(state);
  }

  private become(state: StreamState): void {
    this.state = state;
    this.followed.forEach((one) => one.become(state));
  }

  private deliver(path: string, data: unknown): void {
    this.followed.forEach((one) => {
      if (one.path === path) one.hear(data);
    });
  }

  private refuse(path: string): void {
    this.followed.forEach((one) => {
      if (one.path === path) one.refuse();
    });
  }

  private say(said: Said): void {
    if (!this.left) this.channel.postMessage(said);
  }
}
