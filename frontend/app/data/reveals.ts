import { tracked } from '@glimmer/tracking';
import { waitForPromise } from '@ember/test-waiters';
import type { Expand, Revealed } from 'frontend/data/diff-rows';
import type StoreService from 'frontend/services/store';

export default class Reveals {
  @tracked private asked: Record<string, string[]> = {};

  constructor(private readonly store: StoreService) {}

  of(head: string, path: string): Revealed {
    const revealed: Revealed = {};
    for (const query of this.asked[`${head}:${path}`] ?? []) {
      for (const line of this.store.fileLines(query)?.lines ?? []) {
        revealed[line.number] = line.text;
      }
    }
    return revealed;
  }

  reveal(head: string, path: string, expand: Expand): void {
    void waitForPromise(this.fetchLines(head, path, expand));
  }

  private async fetchLines(
    head: string,
    path: string,
    expand: Expand,
  ): Promise<void> {
    const query = new URLSearchParams({
      sha: head,
      path,
      from_line: String(expand.from),
      to_line: String(expand.to),
    }).toString();
    if ((await this.store.readLines(query)) === 'failed') return;
    const key = `${head}:${path}`;
    this.asked = { ...this.asked, [key]: [...(this.asked[key] ?? []), query] };
  }
}
