import Controller from '@ember/controller';
import { tracked } from '@glimmer/tracking';

export default class DashboardController extends Controller {
  queryParams = ['pane'];

  @tracked pane: string | null = null;
}
