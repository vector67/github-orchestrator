import Service from '@ember/service';
import { tracked } from '@glimmer/tracking';

const REMEMBERED = 'harvest-timer';
const EXTENSION_MARK = 'harvest-messaging';

function recalled(): boolean {
  try {
    return localStorage.getItem(REMEMBERED) === 'on';
  } catch {
    return false;
  }
}

export default class HarvestSwitchService extends Service {
  @tracked on = recalled();
  @tracked settingUp = false;

  toggle(): void {
    this.on = !this.on;
    this.settingUp = this.on && !document.getElementById(EXTENSION_MARK);
    try {
      localStorage.setItem(REMEMBERED, this.on ? 'on' : 'off');
    } catch {
      return;
    }
  }

  doneSettingUp(): void {
    this.settingUp = false;
  }
}
