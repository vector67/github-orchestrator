import Component from '@glimmer/component';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import type StoreService from 'frontend/services/store';

export default class MigrationWait extends Component {
  @service declare store: StoreService;

  get sessions() {
    return this.store.migration?.sessions ?? [];
  }

  get branches() {
    return this.store.migration?.branches ?? [];
  }

  closeAndMigrate = (): void => {
    void this.store.closeSessionsAndMigrate();
  };

  <template>
    <div class="wall-empty" data-test-wall-unheld="waiting-to-migrate">
      {{#if this.sessions.length}}
        <p data-test-migration-sessions-note>This version renames each review
          thread’s worktree folder, and a terminal session is still open in
          these. The watcher waits until they close.</p>
        <ul class="migration-sessions">
          {{#each this.sessions key="folder" as |session|}}
            <li data-test-migration-session>
              <span>{{session.repo}}#{{session.number}}</span>
              <span>thread {{session.thread}}</span>
              <span class="mono">{{session.folder}}</span>
            </li>
          {{/each}}
        </ul>
      {{/if}}
      {{#if this.branches.length}}
        <p data-test-migration-branches-note>This version renames each review
          thread’s branch, and git would not rename these. No pull request’s
          board opens until they are. Fix what git says, or rename the branch
          yourself with the command shown, then press Close sessions and migrate
          to try again.</p>
        <ul class="migration-sessions">
          {{#each this.branches key="branch" as |branch|}}
            <li data-test-migration-branch>
              <span>{{branch.repo}}#{{branch.number}}</span>
              <span>thread {{branch.thread}}</span>
              <span><span class="mono">{{branch.branch}}</span>
                would not become
                <span class="mono">{{branch.new_branch}}</span></span>
              <span class="mono">{{branch.error}}</span>
              <code>git -C
                {{branch.clone}}
                branch -m
                {{branch.branch}}
                {{branch.new_branch}}</code>
            </li>
          {{/each}}
        </ul>
      {{/if}}
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
