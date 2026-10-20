import Controller from '@ember/controller';
import { tracked } from '@glimmer/tracking';

export default class DashboardController extends Controller {
  queryParams = ['pane', 'ready'];

  @tracked pane: string | null = null;
  @tracked ready = false;
}
