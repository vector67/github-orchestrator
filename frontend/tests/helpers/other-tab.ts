const SHARED = 'board-streams';

export type Said =
  | { kind: 'want'; tab: string; paths: string[] }
  | { kind: 'gone'; tab: string }
  | { kind: 'ask' }
  | { kind: 'heard'; path: string; data: unknown }
  | { kind: 'refused'; path: string }
  | { kind: 'state'; state: 'opening' | 'open' | 'down' }
  | { kind: 'reopen' };

export class OtherTab {
  readonly said: Said[] = [];
  private readonly channel = new BroadcastChannel(SHARED);
  private answer: ((path: string) => unknown) | null = null;
  private release: (() => void) | null = null;

  constructor() {
    this.channel.onmessage = ({ data }: MessageEvent<Said>) => {
      this.said.push(data);
      const answer = this.answer;
      if (data.kind !== 'want' || !answer) return;
      this.tell({ kind: 'state', state: 'open' });
      data.paths.forEach((path) =>
        this.tell({ kind: 'heard', path, data: answer(path) }),
      );
    };
  }

  tell(said: Said): void {
    this.channel.postMessage(said);
  }

  heard(path: string): unknown[] {
    return this.said.flatMap((one) =>
      one.kind === 'heard' && one.path === path ? [one.data] : [],
    );
  }

  forget(): void {
    this.said.length = 0;
  }

  lead(answer: (path: string) => unknown): Promise<void> {
    this.answer = answer;
    return new Promise((held) => {
      void navigator.locks.request(SHARED, () => {
        held();
        return new Promise<void>((release) => (this.release = release));
      });
    });
  }

  stepDown(): void {
    this.answer = null;
    this.release?.();
    this.release = null;
  }

  close(): void {
    this.stepDown();
    this.channel.close();
  }
}

export function setupOtherTab(hooks: NestedHooks): () => OtherTab {
  let tab = new OtherTab();
  tab.close();

  hooks.beforeEach(function () {
    tab = new OtherTab();
  });

  hooks.afterEach(function () {
    tab.close();
  });

  return () => tab;
}
