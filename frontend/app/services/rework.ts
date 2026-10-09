import Service from '@ember/service';
import { tracked } from '@glimmer/tracking';
import type { Brief } from 'frontend/data/decisions';

export interface Pointed {
  file: string;
  line: number;
  text: string;
}

export default class ReworkService extends Service {
  @tracked openFor: string | null = null;
  @tracked note = '';
  @tracked pointed: Pointed[] = [];
  @tracked included: string[] = [];
  @tracked visible = false;

  isOpen(key: string): boolean {
    return this.openFor === key;
  }

  open(key: string): void {
    this.openFor = key;
    this.note = '';
    this.pointed = [];
    this.included = [];
    this.visible = false;
  }

  cancel(): void {
    this.openFor = null;
    this.note = '';
    this.pointed = [];
    this.included = [];
    this.visible = false;
  }

  idOf(one: Pointed): string {
    return `${one.file}:${one.line}:${one.text}`;
  }

  toggle(one: Pointed): void {
    const id = this.idOf(one);
    const kept = this.pointed.filter((other) => this.idOf(other) !== id);
    this.pointed = kept.length === this.pointed.length ? [...kept, one] : kept;
  }

  remove(id: string): void {
    this.pointed = this.pointed.filter((one) => this.idOf(one) !== id);
  }

  isPointed(id: string): boolean {
    return this.pointed.some((one) => this.idOf(one) === id);
  }

  toggleReviewer(author: string): void {
    this.included = this.included.includes(author)
      ? this.included.filter((one) => one !== author)
      : [...this.included, author];
  }

  isIncluded(author: string): boolean {
    return this.included.includes(author);
  }

  get count(): number {
    return this.pointed.length;
  }

  get empty(): boolean {
    return !this.note.trim() && this.pointed.length === 0;
  }

  get brief(): Brief {
    return {
      note: this.note.trim(),
      pointed: this.pointed,
      include: this.included,
    };
  }
}
