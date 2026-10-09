import Component from '@glimmer/component';
import { service } from '@ember/service';
import type HereService from 'frontend/services/here';

export default class BoardUnreachable extends Component {
  @service declare here: HereService;

  <template>
    <section class="board-unreachable" data-test-unreachable>
      <h2>Board unreachable</h2>
      <p class="why">PR #{{this.here.pr.number}}’s board is not answering. It
        may still be starting, be frozen on the wrong branch, or its manager may
        be down. This tab fills in on its own once the board answers.</p>
    </section>
  </template>
}
