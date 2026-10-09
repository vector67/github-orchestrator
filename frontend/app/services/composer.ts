import Service from '@ember/service';
import { tracked } from '@glimmer/tracking';

export default class ComposerService extends Service {
  @tracked openFor: string | null = null;
  @tracked words = '';

  isOpen(key: string): boolean {
    return this.openFor === key;
  }

  open(key: string): void {
    if (this.isOpen(key)) return;
    this.openFor = key;
    this.words = '';
  }

  close(): void {
    this.openFor = null;
    this.words = '';
  }
}
