import { tracked } from '@glimmer/tracking';

export default class FileViews {
  @tracked private toggled: Record<string, boolean> = {};
  @tracked private loaded: string[] = [];

  folded(path: string): boolean {
    return this.toggled[path] ?? false;
  }

  fold(path: string): void {
    this.toggled = { ...this.toggled, [path]: !this.folded(path) };
  }

  isLoaded(path: string): boolean {
    return this.loaded.includes(path);
  }

  load(path: string): void {
    this.loaded = [...this.loaded, path];
  }
}
