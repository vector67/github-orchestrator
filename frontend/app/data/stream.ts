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

export class EventStream {
  @tracked state: StreamState = 'opening';
  readonly opened: Promise<void>;
  private last: string | null = null;
  private readonly stopper = new AbortController();
  private firstAnswer: () => void = () => {};

  constructor(
    private readonly url: string,
    private readonly heard: (data: unknown) => void,
  ) {
    this.opened = new Promise((resolve) => (this.firstAnswer = resolve));
    void this.open();
  }

  reopen(): void {
    if (this.state === 'down') void this.open();
  }

  close(): void {
    this.stopper.abort();
  }

  private async open(): Promise<void> {
    this.state = 'opening';
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
      if (!this.stopper.signal.aborted) this.state = 'down';
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
    this.state = 'open';
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
