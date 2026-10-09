import Service from '@ember/service';
import type { Ticket } from 'frontend/data/api';

const KEPT = 'decide-dialog-drafts';
const FORTNIGHT = 14 * 24 * 60 * 60 * 1000;

export interface Held {
  typed: string;
  deleting: boolean;
  resolving: boolean;
  thumbing: boolean;
  wording: string | null;
  wake: string;
  wakePr: string;
  ticket?: Ticket;
}

interface Kept extends Held {
  at: number;
}

type Shelf = Record<string, Record<string, Kept>>;

function fresh(shelf: Shelf, now: number): Shelf {
  return Object.fromEntries(
    Object.entries(shelf)
      .map(([id, verbs]): [string, Record<string, Kept>] => [
        id,
        Object.fromEntries(
          Object.entries(verbs).filter(([, kept]) => now - kept.at < FORTNIGHT),
        ),
      ])
      .filter(([, verbs]) => Object.keys(verbs).length > 0),
  );
}

export default class DialogDraftsService extends Service {
  heldFor(id: string, decision: string): Held | null {
    return this.read()[id]?.[decision] ?? null;
  }

  keep(id: string, decision: string, held: Held | null): void {
    const shelf = this.read();
    const verbs = { ...shelf[id] };
    if (held) verbs[decision] = { ...held, at: Date.now() };
    else delete verbs[decision];
    this.write({ ...shelf, [id]: verbs });
  }

  forget(id: string): void {
    const shelf = this.read();
    delete shelf[id];
    this.write(shelf);
  }

  private read(): Shelf {
    try {
      const raw = localStorage.getItem(KEPT);
      return raw ? fresh(JSON.parse(raw) as Shelf, Date.now()) : {};
    } catch {
      return {};
    }
  }

  private write(shelf: Shelf): void {
    try {
      localStorage.setItem(KEPT, JSON.stringify(shelf));
    } catch {
      return;
    }
  }
}
