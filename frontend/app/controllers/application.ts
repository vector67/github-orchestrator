import Controller from '@ember/controller';
import { tracked } from '@glimmer/tracking';

export default class ApplicationController extends Controller {
  queryParams = ['repos', 'tour'];

  @tracked repos: string | null = null;
  @tracked tour: string | null = null;
}
