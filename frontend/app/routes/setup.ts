import Route from '@ember/routing/route';
import { service } from '@ember/service';
import type StoreService from 'frontend/services/store';
import type ThemeService from 'frontend/services/theme';

export default class SetupRoute extends Route {
  @service declare store: StoreService;
  @service declare theme: ThemeService;

  async model(): Promise<void> {
    this.theme.restore();
    await this.store.readSetup();
  }
}
