import Component from '@glimmer/component';
import { service } from '@ember/service';
import HubBar from 'frontend/components/hub-bar';
import Waiting from 'frontend/components/waiting';
import type HubService from 'frontend/services/hub';

interface HubLoadingSignature {
  Args: { on: 'wall' | 'runs' };
}

export default class HubLoading extends Component<HubLoadingSignature> {
  @service declare hub: HubService;

  <template>
    {{#if this.hub.onHub}}
      <HubBar @on={{@on}} />
    {{/if}}
    <div class="page-loading">
      <p class="work-placeholder" data-test-loading={{@on}}>
        Loading the
        {{@on}}…
      </p>
      <Waiting />
    </div>
  </template>
}
