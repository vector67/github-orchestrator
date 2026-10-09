import Component from '@glimmer/component';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import { fn } from '@ember/helper';
import type RouterService from '@ember/routing/router-service';
import { keyOf, pageOf } from 'frontend/data/wall';
import type { OldLink } from 'frontend/routes/old-link';
import type { PrEntity } from 'frontend/services/store';

export interface OldLinkSignature {
  Args: { link: OldLink };
}

export default class OldLinkChooser extends Component<OldLinkSignature> {
  @service declare router: RouterService;

  hrefOf = (pr: PrEntity): string => pageOf(pr, this.args.link.under);

  open = (pr: PrEntity, event: MouseEvent): void => {
    event.preventDefault();
    void this.router.transitionTo(this.hrefOf(pr));
  };

  <template>
    <section id="old-link" data-test-old-link>
      {{#if @link.prs.length}}
        <h1>Which #{{@link.number}}?</h1>
        <p>This link names #{{@link.number}}
          but no repo, and #{{@link.number}}
          is held in more than one repo. Pick one:</p>
        <ul>
          {{#each @link.prs key="repo" as |pr|}}
            <li><a
                class="linkish"
                href={{this.hrefOf pr}}
                data-test-old-link-choice={{keyOf pr}}
                {{on "click" (fn this.open pr)}}
              >{{pr.repo}}#{{pr.number}} {{pr.title}}</a></li>
          {{/each}}
        </ul>
      {{else}}
        <h1>No #{{@link.number}} here</h1>
        <p>This link names #{{@link.number}}
          but no repo, and the hub holds no #{{@link.number}}
          now.
          <a class="linkish" href="/">Back to the wall</a>.</p>
      {{/if}}
    </section>
  </template>
}
