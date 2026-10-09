import Component from '@glimmer/component';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import { copyDirectory } from 'frontend/data/address';
import type ToastsService from 'frontend/services/toasts';

export interface CopyDirectorySignature {
  Args: { directory: string };
}

export default class CopyDirectory extends Component<CopyDirectorySignature> {
  @service declare toasts: ToastsService;

  copy = async (): Promise<void> => {
    this.toasts.say(await copyDirectory(this.args.directory), 'done');
  };

  <template>
    <button
      type="button"
      class="copy-directory"
      title={{@directory}}
      data-test-copy-directory
      {{on "click" this.copy}}
    >copy directory</button>
  </template>
}
