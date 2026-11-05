import Route from '@ember/routing/route';
import { service } from '@ember/service';
import type ThemeService from 'frontend/services/theme';

export default class NotFoundRoute extends Route {
  @service declare theme: ThemeService;

  model(): void {
    this.theme.restore();
  }
}
