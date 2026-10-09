import Controller from '@ember/controller';
import { tracked } from '@glimmer/tracking';

export default class PrDiffController extends Controller {
  queryParams = ['file', 'line'];

  @tracked file: string | null = null;
  @tracked line: string | null = null;

  show = (path: string) => {
    this.file = path;
    this.line = null;
  };
}
