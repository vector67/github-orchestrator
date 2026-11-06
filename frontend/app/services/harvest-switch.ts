import Service from '@ember/service';
import { tracked } from '@glimmer/tracking';
import { keep, recall } from 'frontend/data/site-data';

const REMEMBERED = 'harvest-timer';
const EXTENSION_MARK = 'harvest-messaging';

export default class HarvestSwitchService extends Service {
  @tracked on = recall(REMEMBERED) === 'on';
  @tracked settingUp = false;

  toggle(): void {
    this.on = !this.on;
    this.settingUp = this.on && !document.getElementById(EXTENSION_MARK);
    keep(REMEMBERED, this.on ? 'on' : 'off');
  }

  doneSettingUp(): void {
    this.settingUp = false;
  }
}
