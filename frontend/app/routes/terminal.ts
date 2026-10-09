import Route from '@ember/routing/route';
import { service } from '@ember/service';
import type TerminalService from 'frontend/services/terminal';
import type ThemeService from 'frontend/services/theme';

export default class TerminalRoute extends Route {
  @service declare terminal: TerminalService;
  @service declare theme: ThemeService;

  async model() {
    this.theme.restore();
    await this.terminal.refresh();
    return this.terminal;
  }
}
