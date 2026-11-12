import Service from '@ember/service';
import { tracked } from '@glimmer/tracking';
import { keep, recall } from 'frontend/data/site-data';

const REMEMBERED = 'harvest-timer';
const EXTENSION_MARK = 'harvest-messaging';

export default class HarvestSwitchService extends Service {
  @tracked on = recall(REMEMBERED) === 'on';
  @tracked settingUp = false;

  get missing(): boolean {
    return !document.getElementById(EXTENSION_MARK);
  }

  toggle(): void {
    this.on = !this.on;
    keep(REMEMBERED, this.on ? 'on' : 'off');
  }

  setUp(): void {
    this.settingUp = true;
  }

  doneSettingUp(): void {
    this.settingUp = false;
  }
}
