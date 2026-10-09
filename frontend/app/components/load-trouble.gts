import type { TOC } from '@ember/component/template-only';

interface LoadTroubleSignature {
  Args: { trouble: unknown };
}

function wordsOf(trouble: unknown): string {
  const why = trouble instanceof Error ? trouble.message : String(trouble);
  return `The board could not load: ${why}`;
}

const LoadTrouble: TOC<LoadTroubleSignature> = <template>
  <section id="load-trouble" class="work-placeholder">
    <p data-test-load-trouble>{{wordsOf @trouble}}</p>
  </section>
</template>;

export default LoadTrouble;
