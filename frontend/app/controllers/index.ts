import Controller from '@ember/controller';
import { tracked } from '@glimmer/tracking';

export default class IndexController extends Controller {
  queryParams = ['ready'];

  @tracked ready: string | null = null;
}
