import Component from '@glimmer/component';
import { on } from '@ember/modifier';
import { service } from '@ember/service';
import type RouterService from '@ember/routing/router-service';

interface LoadTroubleSignature {
  Args: { trouble: unknown };
}

function wordsOf(trouble: unknown): string {
  const why = trouble instanceof Error ? trouble.message : String(trouble);
  return `The board could not load: ${why}`;
}

function anythingSaved(): boolean {
  try {
    return localStorage.length > 0;
  } catch {
    return false;
  }
}

export default class LoadTrouble extends Component<LoadTroubleSignature> {
  @service declare router: RouterService;

  saved = anythingSaved();

  forgetSaved = (): void => {
    try {
      localStorage.clear();
    } catch {
      return;
    }
    const { location } = this.router;
    const asked = typeof location === 'string' ? '/' : location.getURL();
    void this.router.transitionTo(asked);
  };

  <template>
    <section id="load-trouble" class="work-placeholder">
      <p data-test-load-trouble>{{wordsOf @trouble}}</p>
      {{#if this.saved}}
        <p>
          This browser holds what the board saved here earlier. An earlier
          version may have saved it in a shape this one cannot read.
        </p>
        <button
          type="button"
          data-test-forget-saved
          {{on "click" this.forgetSaved}}
        >Delete what this browser saved and try again</button>
      {{/if}}
    </section>
  </template>
}
