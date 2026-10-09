import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import type { TOC } from '@ember/component/template-only';
import { fn } from '@ember/helper';
import { on } from '@ember/modifier';
import type { TreeRow } from 'frontend/data/file-tree';

export interface FileTreeSignature {
  Args: {
    rows: TreeRow[];
    current: string | null;
    choose: (path: string) => void;
    count?: (row: TreeRow) => number;
  };
}

interface TreeLevelSignature {
  Args: {
    rows: TreeRow[];
    current: (row: TreeRow) => boolean;
    choose: (path: string) => void;
    count: (row: TreeRow) => number;
    folded: (row: TreeRow) => boolean;
    fold: (row: TreeRow) => void;
  };
}

function isFile(row: TreeRow): boolean {
  return row.kind === 'file';
}

function uncounted(): number {
  return 0;
}

const TreeLevel: TOC<TreeLevelSignature> = <template>
  <ul class="tree-list">
    {{#each @rows key="path" as |row|}}
      {{#if (isFile row)}}
        <li class="tree-item">
          <button
            type="button"
            class="tree-row file"
            data-test-tree-row="file"
            data-path={{row.path}}
            data-status={{row.status}}
            aria-current={{if (@current row) "true"}}
            title="{{row.status}} · {{row.path}}"
            {{on "click" (fn @choose row.path)}}
          ><span class="tree-status {{row.status}}"></span><span
              class="tree-name"
            >{{row.name}}</span>{{#if (@count row)}}<span
                class="tree-count"
                data-test-tree-count
              >{{@count row}}</span>{{/if}}</button>
        </li>
      {{else}}
        <li class="tree-item" data-test-tree-folder={{row.path}}>
          <button
            type="button"
            class="tree-row folder"
            data-test-tree-row="folder"
            aria-expanded={{if (@folded row) "false" "true"}}
            {{on "click" (fn @fold row)}}
          ><span class="tree-chevron" aria-hidden="true"></span><span
              class="tree-name"
            >{{row.name}}</span></button>
          {{#unless (@folded row)}}
            <TreeLevel
              @rows={{row.children}}
              @current={{@current}}
              @choose={{@choose}}
              @count={{@count}}
              @folded={{@folded}}
              @fold={{@fold}}
            />
          {{/unless}}
        </li>
      {{/if}}
    {{/each}}
  </ul>
</template>;

export default class FileTree extends Component<FileTreeSignature> {
  @tracked private shut: string[] = [];

  current = (row: TreeRow): boolean => row.path === this.args.current;

  get count(): (row: TreeRow) => number {
    return this.args.count ?? uncounted;
  }

  folded = (row: TreeRow): boolean => this.shut.includes(row.path);

  fold = (row: TreeRow) => {
    this.shut = this.folded(row)
      ? this.shut.filter((one) => one !== row.path)
      : [...this.shut, row.path];
  };

  <template>
    <nav class="file-tree" aria-label="the changed files">
      <TreeLevel
        @rows={{@rows}}
        @current={{this.current}}
        @choose={{@choose}}
        @count={{this.count}}
        @folded={{this.folded}}
        @fold={{this.fold}}
      />
    </nav>
  </template>
}
