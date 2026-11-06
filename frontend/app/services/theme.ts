import Service from '@ember/service';
import { tracked } from '@glimmer/tracking';
import { keep, recall } from 'frontend/data/site-data';

const REMEMBERED = 'board-theme';

export default class ThemeService extends Service {
  @tracked chosen: string | null = null;

  restore(): void {
    const asked = new URLSearchParams(window.location.search).get('theme');
    this.apply(asked ?? recall(REMEMBERED));
  }

  apply(theme: string | null): void {
    this.chosen = theme;
    const root = document.documentElement;
    if (theme) root.setAttribute('data-theme', theme);
    else root.removeAttribute('data-theme');
  }

  get dark(): boolean {
    if (this.chosen) return this.chosen === 'dark';
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  }

  toggle(): void {
    const next = this.dark ? 'light' : 'dark';
    this.apply(next);
    keep(REMEMBERED, next);
  }
}
