import EmberRouter from '@embroider/router';
import config from 'frontend/config/environment';

export default class Router extends EmberRouter {
  location = config.locationType;
  rootURL = config.rootURL;
}

Router.map(function () {
  this.route('runs');
  this.route('setup');
  this.route('pr', { path: '/pr/:owner/:name/:number' }, function () {
    this.route('conversations', { resetNamespace: true }, function () {
      this.route('new-draft');
      this.route('detail', { path: '/:conversation_id' });
    });
    this.route('board', { resetNamespace: true });
    this.route('dashboard', { resetNamespace: true });
    this.route('terminal', { resetNamespace: true });
    this.route('diff');
  });
  this.route('old-link', { path: '/pr/:number' }, function () {
    this.route('under', { path: '/*under' });
  });
  this.route('not-found', { path: '/*path' });
});
