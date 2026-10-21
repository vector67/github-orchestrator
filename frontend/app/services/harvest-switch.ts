import Service from '@ember/service';
import { tracked } from '@glimmer/tracking';

const REMEMBERED = 'harvest-timer';

function recalled(): boolean {
  try {
    return localStorage.getItem(REMEMBERED) === 'on';
  } catch {
    return false;
  }
}

export default class HarvestSwitchService extends Service {
  @tracked on = recalled();

  toggle(): void {
    this.on = !this.on;
    try {
      localStorage.setItem(REMEMBERED, this.on ? 'on' : 'off');
    } catch {
      return;
    }
  }
}
