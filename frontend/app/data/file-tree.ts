import type { FileChange } from 'frontend/data/api';

export interface TreeRow {
  kind: 'folder' | 'file';
  name: string;
  path: string;
  status: string;
  children: TreeRow[];
}

interface Folder {
  folders: Map<string, Folder>;
  files: FileChange[];
}

function folder(): Folder {
  return { folders: new Map(), files: [] };
}

function planted(files: FileChange[]): Folder {
  const root = folder();
  for (const file of files) {
    const parts = file.path.split('/');
    parts.pop();
    let at = root;
    for (const part of parts) {
      let next = at.folders.get(part);
      if (!next) {
        next = folder();
        at.folders.set(part, next);
      }
      at = next;
    }
    at.files.push(file);
  }
  return root;
}

function byName(one: string, other: string): number {
  return one.localeCompare(other, undefined, { sensitivity: 'base' });
}

function rowsOf(at: Folder, prefix: string): TreeRow[] {
  const folders = [...at.folders.entries()].sort(([one], [other]) =>
    byName(one, other),
  );
  const rows: TreeRow[] = [];
  for (const [first, inside] of folders) {
    let name = first;
    let held = inside;
    while (held.files.length === 0 && held.folders.size === 1) {
      const [[next, deeper]] = [...held.folders.entries()] as [
        [string, Folder],
      ];
      name = `${name}/${next}`;
      held = deeper;
    }
    const path = `${prefix}${name}`;
    rows.push({
      kind: 'folder',
      name,
      path,
      status: '',
      children: rowsOf(held, `${path}/`),
    });
  }
  const files = [...at.files].sort((one, other) =>
    byName(one.path, other.path),
  );
  for (const file of files) {
    rows.push({
      kind: 'file',
      name: file.path.slice(prefix.length),
      path: file.path,
      status: file.status,
      children: [],
    });
  }
  return rows;
}

function filesIn(rows: TreeRow[]): string[] {
  return rows.flatMap((row) =>
    row.kind === 'file' ? [row.path] : filesIn(row.children),
  );
}

export function treeOf(files: FileChange[], filter: string): TreeRow[] {
  const words = filter.trim().toLowerCase();
  const kept = words
    ? files.filter((one) => one.path.toLowerCase().includes(words))
    : files;
  return rowsOf(planted(kept), '');
}

export function inTreeOrder(files: FileChange[]): FileChange[] {
  const order = filesIn(treeOf(files, ''));
  return [...files].sort(
    (one, other) => order.indexOf(one.path) - order.indexOf(other.path),
  );
}
