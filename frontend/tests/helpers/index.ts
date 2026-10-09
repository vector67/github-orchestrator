import {
  setupApplicationTest as upstreamSetupApplicationTest,
  type SetupTestOptions,
} from 'ember-qunit';
import { _backburner } from '@ember/runloop';

const DIALOG_DRAFTS = 'decide-dialog-drafts';
const KEPT_PULL_REQUESTS = 'hub-pull-requests';
const CHOSEN_REPOS = 'hub-repos';

function forgetDialogDrafts(hooks: NestedHooks) {
  hooks.beforeEach(function () {
    localStorage.removeItem(DIALOG_DRAFTS);
    localStorage.removeItem(KEPT_PULL_REQUESTS);
    localStorage.removeItem(CHOSEN_REPOS);
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
