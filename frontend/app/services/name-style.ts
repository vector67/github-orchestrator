import Service from '@ember/service';
import { tracked } from '@glimmer/tracking';
import { keep, recall } from 'frontend/data/site-data';
import { NAME_STYLES, type NameStyle } from 'frontend/data/names';

const KEPT = 'name-style';

function recalled(): NameStyle {
  const kept = recall(KEPT);
  return NAME_STYLES.find((one) => one === kept) ?? 'full';
}

export default class NameStyleService extends Service {
  @tracked chosen: NameStyle = recalled();

  choose(chosen: NameStyle): void {
    this.chosen = chosen;
    keep(KEPT, chosen);
  }
}
