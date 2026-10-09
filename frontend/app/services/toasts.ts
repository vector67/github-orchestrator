import Service from '@ember/service';
import { tracked } from '@glimmer/tracking';
import { after, durationOf, flip } from 'frontend/motion';

const TOAST_MS = 3000;

interface Toast {
  id: number;
  text: string;
  square: string;
  leaving: boolean;
}

export default class ToastsService extends Service {
  @tracked bars: Toast[] = [];

  private next = 0;

  say(text: string, square: string): void {
    const bar = { id: (this.next += 1), text, square, leaving: false };
    this.bars = [...this.bars, bar];
    void after(TOAST_MS).then(() => this.drop(bar.id));
  }

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
