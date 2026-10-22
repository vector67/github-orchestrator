import Component from '@glimmer/component';
import { on } from '@ember/modifier';
import type { MergeNote as Note } from 'frontend/services/store';

export interface MergeNoteSignature {
  Args: {
    note: Note;
    base: string;
    skipping: boolean;
    skip: (skip: boolean) => void;
  };
}

function files(count: number): string {
  return `${count} ${count === 1 ? 'file' : 'files'}`;
}

export default class MergeNote extends Component<MergeNoteSignature> {
  get came(): string {
    const { came } = this.args.note;
    if (came === null) return `What came in from ${this.args.base}`;
    return `${files(came)} came in from ${this.args.base}`;
  }

  get hidden(): string {
    const { came } = this.args.note;
    if (came === null) return 'is hidden.';
    return came === 1 ? 'and is hidden.' : 'and are hidden.';
  }

  get own(): string {
    const { own } = this.args.note;
    if (!own.length) return 'This merge changed nothing on its own.';
    return `This merge changed ${files(own.length)} on its own: ${own.join(', ')}`;
  }

  ticked = (event: Event) => {
    this.args.skip((event.target as HTMLInputElement).checked);
  };

  <template>
    <p class="merge-note" data-test-merge-note>
      <span><b>{{this.came}}</b> {{this.hidden}} {{this.own}}</span>
      <label class="merge-note-skip">
        <input
          type="checkbox"
          checked={{@skipping}}
          data-test-skip-merges
          {{on "change" this.ticked}}
        />
        Skip merges when stepping
      </label>
    </p>
  </template>
}
