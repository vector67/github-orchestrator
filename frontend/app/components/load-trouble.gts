import Component from '@glimmer/component';
import type Owner from '@ember/owner';

const MARK = 'data-board-trouble';

interface LoadTroubleSignature {
  Args: { trouble: unknown };
}

function wordsOf(trouble: unknown): string {
  const why = trouble instanceof Error ? trouble.message : String(trouble);
  return `The board could not load: ${why}`;
}

export default class LoadTrouble extends Component<LoadTroubleSignature> {
  constructor(owner: Owner, args: LoadTroubleSignature['Args']) {
    super(owner, args);
    document.documentElement.setAttribute(MARK, wordsOf(args.trouble));
  }

  willDestroy(): void {
    super.willDestroy();
    document.documentElement.removeAttribute(MARK);
  }

  <template>
    <section id="load-trouble" class="work-placeholder">
      <p data-test-load-trouble>{{wordsOf @trouble}}</p>
    </section>
  </template>
}
