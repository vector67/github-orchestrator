import Service from '@ember/service';
import { tracked } from '@glimmer/tracking';
import { after, durationOf, flip } from 'frontend/motion';

const TOAST_MS = 3000;

const UNDO_MS = 8000;

export interface ToastUndo {
  label: string;
  run: () => void;
}

interface Toast {
  id: number;
  text: string;
  square: string;
  undo: ToastUndo | null;
  leaving: boolean;
}

export default class ToastsService extends Service {
  @tracked bars: Toast[] = [];

  private next = 0;

  say(text: string, square: string, undo: ToastUndo | null = null): void {
    const bar = { id: (this.next += 1), text, square, undo, leaving: false };
    this.bars = [...this.bars, bar];
    void after(undo ? UNDO_MS : TOAST_MS).then(() => this.drop(bar.id));
  }

  undo = (id: number): void => {
    const bar = this.bars.find((one) => one.id === id && !one.leaving);
    if (!bar?.undo) return;
    this.drop(id);
    bar.undo.run();
  };

  drop = (id: number): void => {
    if (!this.bars.some((bar) => bar.id === id && !bar.leaving)) return;
    void this.dropped(id);
  };

  private async dropped(id: number): Promise<void> {
    this.bars = this.bars.map((bar) =>
      bar.id === id ? { ...bar, leaving: true } : bar,
    );
    await after(durationOf('out'));
    await flip(() => {
      this.bars = this.bars.filter((bar) => bar.id !== id);
    });
  }
}
