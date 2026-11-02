import Component from '@glimmer/component';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import type StoreService from 'frontend/services/store';

export default class MigrationWait extends Component {
  @service declare store: StoreService;

  get sessions() {
    return this.store.migration?.sessions ?? [];
  }

  closeAndMigrate = (): void => {
    void this.store.closeSessionsAndMigrate();
  };

  <template>
    <div class="wall-empty" data-test-wall-unheld="waiting-to-migrate">
      <p>This version renames each review thread’s worktree folder, and a
        terminal session is still open in these. The watcher waits until they
        close.</p>
      <ul class="migration-sessions">
        {{#each this.sessions key="folder" as |session|}}
          <li data-test-migration-session>
            <span>{{session.repo}}#{{session.number}}</span>
            <span>thread {{session.thread}}</span>
            <span class="mono">{{session.folder}}</span>
          </li>
        {{/each}}
      </ul>
      <button
        type="button"
        class="btn"
        disabled={{this.store.closingSessions}}
        data-test-close-sessions-and-migrate
        {{on "click" this.closeAndMigrate}}
      >Close sessions and migrate</button>
    </div>
  </template>
}
