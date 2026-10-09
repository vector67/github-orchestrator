import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { visit } from '@ember/test-helpers';
import {
  comment,
  setupFakeBoard,
  thread,
  type FakeBoard,
} from 'frontend/tests/helpers/fake-board';

const KEY = 'PRRT_md';

const DRAWN_TAGS = new Set([
  'P',
  'BR',
  'STRONG',
  'EM',
  'CODE',
  'PRE',
  'BLOCKQUOTE',
  'UL',
  'OL',
  'LI',
  'H1',
  'H2',
  'H3',
  'H4',
  'H5',
  'H6',
  'S',
  'DEL',
  'HR',
  'A',
  'TABLE',
  'THEAD',
  'TBODY',
  'TR',
  'TH',
  'TD',
  'SPAN',
]);

const DRAWN_ATTRIBUTES = new Set(['href', 'class', 'rel', 'target', 'start']);

const SAFE_HREF = /^https?:\/\//i;

const DRAWN_CLASS = /^(hljs(-[\w-]+)?|[a-z]+_+|language-[\w-]+)$/;

const TOKEN_CLASS = /^(hljs-[\w-]+|[a-z]+_+)$/;

const HOSTILE: [string, string][] = [
  ['a script tag', '<script>window.__pwned = "script"</script>'],
  ['an event attribute', '<img src=x onerror="window.__pwned = \'img\'">'],
  [
    'an event attribute on an allowed tag',
    '<a href="https://example.com" onclick="window.__pwned = 1">x</a>',
  ],
  ['a javascript link', '[click](javascript:window.__pwned=1)'],
  ['a javascript link in capitals', '[click](JAVASCRIPT:window.__pwned=1)'],
  ['a javascript link split by a tab', '[click](java\tscript:alert(1))'],
  [
    'a javascript link split by an entity',
    '[click](java&#x09;script:alert(1))',
  ],
  ['an entity-encoded javascript link', '[click](&#106;avascript:alert(1))'],
  ['a vbscript link', '[click](vbscript:msgbox(1))'],
  [
    'a data link',
    '[click](data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==)',
  ],
  ['a javascript autolink', '<javascript:alert(1)>'],
  ['a javascript reference link', '[click][x]\n\n[x]: javascript:alert(1)'],
  ['a javascript image', '![x](javascript:alert(1))'],
  ['a data image', '![x](data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=)'],
  ['an svg payload', '<svg><script>window.__pwned = "svg"</script></svg>'],
  ['an svg onload', '<svg onload="window.__pwned = \'svg\'"></svg>'],
  [
    'mXSS through svg and style',
    '<svg><p><style><img src=x onerror="window.__pwned = \'mxss\'"></style></p></svg>',
  ],
  [
    'mXSS through math and mglyph',
    '<math><mtext><table><mglyph><style><img src=x onerror="window.__pwned = \'mglyph\'">',
  ],
  [
    'mXSS through noscript',
    '<noscript><p title="</noscript><img src=x onerror=window.__pwned=1>">',
  ],
  ['an iframe', '<iframe src="javascript:window.__pwned=1"></iframe>'],
  [
    'an iframe srcdoc',
    '<iframe srcdoc="<script>window.__pwned=1</script>"></iframe>',
  ],
  ['an object', '<object data="javascript:window.__pwned=1"></object>'],
  ['a form', '<form action="https://evil.example"><input name=x></form>'],
  [
    'a meta refresh',
    '<meta http-equiv="refresh" content="0;url=https://evil.example">',
  ],
  ['a style tag', '<style>body { display: none }</style>'],
  [
    'a details toggle',
    '<details open ontoggle="window.__pwned = \'details\'"><summary>x</summary></details>',
  ],
  [
    'html inside a markdown link',
    '[<img src=x onerror=window.__pwned=1>](https://example.com)',
  ],
  [
    'a link title carrying markup',
    '[x](https://example.com "\\"><img src=x onerror=window.__pwned=1>")',
  ],
  [
    'a fence whose language carries an attribute',
    '```" onmouseover="window.__pwned=1\ncode\n```',
  ],
  [
    'a fence whose language tries a class of the board',
    '```decide approve\ncode\n```',
  ],
  ['a base tag', '<base href="https://evil.example/">'],
  ['a link tag', '<link rel="stylesheet" href="https://evil.example/x.css">'],
  [
    'an id and a name clobbering the page',
    '<a id="panel-body" name="getElementById" href="https://example.com">x</a>',
  ],
  ['a name clobbering the document', '<img name="body"><img name="cookie">'],
  [
    'a form clobbering its own fields',
    '<form id="forms" name="forms"><input name="action"></form>',
  ],
  ['a protocol-relative link', '[x](//evil.example/x)'],
  ['a protocol-relative raw link', '<a href="//evil.example/x">x</a>'],
  ['a scheme with no slashes', '[x](http:evil.example)'],
  [
    'a quote breaking out of a link',
    '[x](https://a.example/"onmouseover="window.__pwned=1)',
  ],
  [
    'a quote breaking out of a raw href',
    '<a href=\'https://a.example/" onmouseover="window.__pwned=1\'>x</a>',
  ],
  [
    'an animation that would fire a handler',
    '<p style="animation: spin 1s" onanimationstart="window.__pwned=1">x</p>',
  ],
  [
    'a focus handler',
    '<a href="https://x.example" onfocus="window.__pwned=1" autofocus>x</a>',
  ],
];

declare global {
  interface Window {
    __pwned?: unknown;
  }
}

function seed(
  board: FakeBoard,
  bodies: string[],
  code: string[],
  path: string,
) {
  board.conversations = [
    thread({
      key: KEY,
      anchor: { ...thread().anchor, path, line: 1, original_line: 1 },
    }),
  ];
  board.comments[KEY] = bodies.map((body, at) =>
    comment({ id: at + 1, review_state: at ? null : 'COMMENTED', body }),
  );
  board.files = {
    sha: 'c0ffee1',
    path,
    from_line: 1,
    to_line: Math.max(code.length, 1),
    truncated: false,
    lines: code.map((text, at) => ({ number: at + 1, text })),
  };
}

function shown(board: FakeBoard, body: string) {
  seed(board, [body], [], 'src/foo.py');
  return visit(`/pr/o/r/7/conversations/${KEY}`);
}

function body(): Element {
  return document.querySelector('[data-test-entry-body]')!;
}

function wrongsIn(root: Element): string[] {
  const found: string[] = [];
  for (const element of root.querySelectorAll('*')) {
    if (!DRAWN_TAGS.has(element.tagName)) found.push(`<${element.tagName}>`);
    for (const { name, value } of element.attributes) {
      if (!DRAWN_ATTRIBUTES.has(name)) found.push(`${name}="${value}"`);
      if (name === 'href' && !SAFE_HREF.test(value))
        found.push(`href ${value}`);
      if (
        name === 'class' &&
        !value.split(' ').every((one) => DRAWN_CLASS.test(one))
      )
        found.push(`class ${value}`);
    }
  }
  return found;
}

function codeLines(): Element[] {
  return [...document.querySelectorAll('[data-test-context] [data-test-code]')];
}

function notTokens(line: Element): string[] {
  return [...line.querySelectorAll('*')].flatMap((element) => [
    ...(element.tagName === 'SPAN' ? [] : [`<${element.tagName}>`]),
    ...[...element.attributes]
      .filter(
        ({ name, value }) =>
          name !== 'class' ||
          !value.split(' ').every((one) => TOKEN_CLASS.test(one)),
      )
      .map(({ name, value }) => `${name}="${value}"`),
  ]);
}

function stayHere(event: Event): void {
  event.preventDefault();
}

async function everythingLoaded(): Promise<void> {
  const loading = [
    ...document.querySelectorAll(
      '#ember-testing img, #ember-testing iframe, #ember-testing object, #ember-testing embed',
    ),
  ].filter(
    (element) => !(element instanceof HTMLImageElement && element.complete),
  );
  await Promise.all(
    loading.map(
      (element) =>
        new Promise((resolve) => {
          element.addEventListener('load', resolve, { once: true });
          element.addEventListener('error', resolve, { once: true });
        }),
    ),
  );
  await new Promise(requestAnimationFrame);
}

module('Acceptance | comment markdown', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  test('a body is drawn as github-flavoured markdown', async function (assert) {
    await shown(
      board(),
      '# Head\n\n**bold** _em_ ~~gone~~ `code`\n\n- one\n- two\n\n' +
        '> quoted\n\n| a | b |\n| - | - |\n| 1 | 2 |\n\n```\nfenced\n```',
    );

    const tags = new Set(
      [...body().querySelectorAll('*')].map((one) => one.tagName),
    );
    for (const tag of [
      'H1',
      'STRONG',
      'EM',
      'S',
      'CODE',
      'UL',
      'LI',
      'BLOCKQUOTE',
      'TABLE',
      'TD',
      'PRE',
    ]) {
      assert.true(tags.has(tag), `draws ${tag}`);
    }
  });

  test('a line break in a comment is a break, as GitHub draws a comment', async function (assert) {
    await shown(board(), 'one\ntwo');

    assert.dom('[data-test-entry-body] br').exists({ count: 1 });
  });

  test('a bare address becomes a link', async function (assert) {
    await shown(board(), 'see https://example.com/x');

    assert
      .dom('[data-test-entry-body] a')
      .hasAttribute('href', 'https://example.com/x');
  });

  test('a link opens on its own and tells the page it goes to nothing', async function (assert) {
    await shown(board(), '[x](https://example.com)');

    assert
      .dom('[data-test-entry-body] a')
      .hasAttribute('target', '_blank')
      .hasAttribute('rel', 'noopener noreferrer');
  });

  test('a fenced block in a language it knows is highlighted', async function (assert) {
    await shown(board(), '```python\ndef f():\n    return 1\n```');

    assert.dom('[data-test-entry-body] code .hljs-keyword').exists();
    assert.strictEqual(
      body().querySelector('code')?.textContent,
      'def f():\n    return 1\n',
    );
  });

  test('a fence in a language nobody knows carries no class', async function (assert) {
    await shown(board(), '```decide\ncode\n```');

    assert.dom('[data-test-entry-body] code').doesNotHaveAttribute('class');
  });

  test('a fenced block too long to highlight is drawn as plain words', async function (assert) {
    const long = 'x = 1\n'.repeat(12_000);

    await shown(board(), '```python\n' + long + '```');

    assert.dom('[data-test-entry-body] code span').doesNotExist();
    assert.strictEqual(body().querySelector('code')?.textContent, long);
  });

  test('an image is drawn as a link to it, so nothing is fetched', async function (assert) {
    await shown(board(), '![the chart](https://example.com/chart.png)');

    assert.dom('[data-test-entry-body] img').doesNotExist();
    assert
      .dom('[data-test-entry-body] a')
      .hasAttribute('href', 'https://example.com/chart.png')
      .hasText('the chart');
  });

  test('no hostile body or line of code draws anything but allowed tags, attributes and links, or runs anything once it is on the page', async function (assert) {
    window.__pwned = undefined;
    const payloads = HOSTILE.map(([, payload]) => payload);
    seed(board(), payloads, payloads, 'src/foo.py');

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert
      .dom('[data-test-entry-body]')
      .exists({ count: HOSTILE.length }, 'every body is on the page');
    assert.strictEqual(codeLines().length, HOSTILE.length);
    const bodies = [...document.querySelectorAll('[data-test-entry-body]')];
    HOSTILE.forEach(([what], at) => {
      assert.deepEqual(wrongsIn(bodies[at]!), [], `${what}, in a comment`);
      assert.deepEqual(
        notTokens(codeLines()[at]!),
        [],
        `${what}, in a line of code`,
      );
    });
    const drawn = [
      ...document.querySelectorAll('[data-test-entry-body] *'),
      ...document.querySelectorAll('[data-test-context] [data-test-code] *'),
    ];
    document.addEventListener('click', stayHere, true);
    try {
      for (const element of drawn) {
        element.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
        element.dispatchEvent(new FocusEvent('focus'));
        element.dispatchEvent(new AnimationEvent('animationstart'));
        element.dispatchEvent(
          new MouseEvent('click', { bubbles: true, cancelable: true }),
        );
      }
      await everythingLoaded();

      assert.strictEqual(window.__pwned, undefined);
    } finally {
      document.removeEventListener('click', stayHere, true);
    }
  });

  test('a line of code is highlighted in the language its file names', async function (assert) {
    const paths = [
      'src/foo.py',
      'app/x.ts',
      'README',
      'notes.nothing-knows-this',
    ];
    const code = 'def helper(rows): const x = 1;';
    seed(board(), ['see here'], [code], 'src/foo.py');
    board().conversations = paths.map((path, at) =>
      thread({
        key: `PRRT_${at}`,
        anchor: { ...thread().anchor, path, line: 1, original_line: 1 },
      }),
    );

    const drawn: Record<string, boolean> = {};
    for (const [at, path] of paths.entries()) {
      await visit(`/pr/o/r/7/conversations/PRRT_${at}`);
      const line = codeLines()[0]!;
      assert.strictEqual(line.textContent, code, `${path} keeps its words`);
      drawn[path] = line.querySelector('span') !== null;
    }

    assert.deepEqual(drawn, {
      'src/foo.py': true,
      'app/x.ts': true,
      README: false,
      'notes.nothing-knows-this': false,
    });
  });

  test('markup in a line of code is drawn as the words it is', async function (assert) {
    const line = '<img src=x onerror="window.__pwned = 1"><script>1</script>';
    seed(board(), ['see here'], [line], 'src/foo.py');

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.deepEqual(notTokens(codeLines()[0]!), []);
    assert.strictEqual(codeLines()[0]!.textContent, line);
  });

  test('markup in a line of html is drawn as tokens, never as elements', async function (assert) {
    const line = '<img src=x onerror="window.__pwned = 1">';
    seed(board(), ['see here'], [line], 'page.html');

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('[data-test-context] img').doesNotExist();
    assert.dom('[data-test-context] [data-test-code] .hljs-tag').exists();
    assert.strictEqual(codeLines()[0]!.textContent, line);
  });

  test('a docstring over several lines of code is drawn as one string', async function (assert) {
    const lines = ['"""Opens here.', 'not one function, and is', '"""'];
    seed(board(), ['see here'], lines, 'src/foo.py');

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('[data-test-context] .hljs-keyword').doesNotExist();
    assert.deepEqual(
      codeLines().map((one) => one.querySelector('.hljs-string')?.textContent),
      lines,
    );
  });

  test('a line too long to highlight is drawn as plain words', async function (assert) {
    const line = 'def f(): return 1; '.repeat(4_000);
    seed(board(), ['see here'], [line], 'src/foo.py');

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('[data-test-context] [data-test-code] *').doesNotExist();
    assert.strictEqual(codeLines()[0]!.textContent, line);
  });
});
