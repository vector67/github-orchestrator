import Controller from '@ember/controller';
import { tracked } from '@glimmer/tracking';

export default class TerminalController extends Controller {
  queryParams = ['session'];

  @tracked session: string | null = null;
}
