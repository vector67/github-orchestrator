import {
  setupApplicationTest as upstreamSetupApplicationTest,
  type SetupTestOptions,
} from 'ember-qunit';
import { _backburner } from '@ember/runloop';

const DIALOG_DRAFTS = 'decide-dialog-drafts';
const KEPT_PULL_REQUESTS = 'hub-pull-requests';
const CHOSEN_REPOS = 'hub-repos';
const SECTIONS_ENTERED = 'hub-sections-entered';
const PARKED_FOLDED = 'wall-parked-folded';
const HARVEST_TIMER = 'harvest-timer';
const COMMIT_SIZING = 'commit-box-sizing';
const COMMIT_NOTES = 'commit-notes-dismissed';
const SKIP_MERGES = 'commit-skip-merges';
const TERMINAL_THEME = 'terminal-theme';
const TERMINAL_LIGHT_THEME = 'terminal-light-theme';
const TERMINAL_DARK_THEME = 'terminal-dark-theme';

function forgetDialogDrafts(hooks: NestedHooks) {
  hooks.beforeEach(function () {
    localStorage.removeItem(DIALOG_DRAFTS);
    localStorage.removeItem(KEPT_PULL_REQUESTS);
    localStorage.removeItem(CHOSEN_REPOS);
    localStorage.removeItem(SECTIONS_ENTERED);
    localStorage.removeItem(PARKED_FOLDED);
    localStorage.removeItem(HARVEST_TIMER);
    localStorage.removeItem(COMMIT_SIZING);
    localStorage.removeItem(COMMIT_NOTES);
    localStorage.removeItem(SKIP_MERGES);
    localStorage.removeItem(TERMINAL_THEME);
    localStorage.removeItem(TERMINAL_LIGHT_THEME);
    localStorage.removeItem(TERMINAL_DARK_THEME);
  });
}

function scheduleWithoutStackTraces(hooks: NestedHooks) {
  hooks.beforeEach(function () {
    _backburner.DEBUG = false;
  });
}

// This file exists to provide wrappers around ember-qunit's
// test setup functions. This way, you can easily extend the setup that is
// needed per test type.

function setupApplicationTest(hooks: NestedHooks, options?: SetupTestOptions) {
  upstreamSetupApplicationTest(hooks, options);
  forgetDialogDrafts(hooks);
  scheduleWithoutStackTraces(hooks);

  // Additional setup for application tests can be done here.
  //
  // For example, if you need an authenticated session for each
  // application test, you could do:
  //
  // hooks.beforeEach(async function () {
  //   await authenticateSession(); // ember-simple-auth
  // });
  //
  // This is also a good place to call test setup functions coming
  // from other addons:
  //
  // setupIntl(hooks, 'en-us'); // ember-intl
  // setupMirage(hooks); // ember-cli-mirage
}

export { setupApplicationTest };
